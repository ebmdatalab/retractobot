import argparse
import datetime
import logging

import django.db.transaction
import requests_cache
from django.conf import settings
from django.core.management.base import BaseCommand

import retractions.pubmed as pubmed
from common import fetch_utils, setup
from retractions.models import RetractedPaper, RetractionNotice


def valid_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = f"Not a valid date: {s!r}"
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    """
    Regular task.
    """

    args = ""
    help = """Use PubMed API to get lists of retracted papers and retraction
    notices, and add any new papers to our database."""  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Limit retraction download count")
        parser.add_argument(
            "--reverse",
            action="store_true",
            help="Get the oldest retractions first",
        )
        parser.add_argument(
            "--mindate",
            type=valid_date,
            help="The minimum date - format YYYY-MM-DD",
        )
        parser.add_argument(
            "--maxdate",
            type=valid_date,
            help="The max date - format YYYY-MM-DD",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip notice already in db",
        )

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        if settings.CACHE_API_CALLS:
            logging.info("Using local cache for PubMed API calls")
            requests_cache.install_cache("cache/get_pubmed_retractions_cache")

        mindate = options.get("mindate", None)
        maxdate = options.get("maxdate", None)
        if mindate and maxdate and maxdate > mindate:
            self._get_retraction_ids(
                skip_existing=options.get("skip_existing"),
                limit=options.get("limit", None),
                reverse=options.get("reverse", True),
                mindate=mindate,
                maxdate=maxdate,
            )

        else:
            # We start with searching for retraction notices, and get all
            # papers from them.
            # The pubmed database has a max query size of 10,000
            # So we search by year
            for year in range(1960, datetime.date.today().year + 1):
                self._get_retraction_ids(
                    skip_existing=options.get("skip_existing"),
                    limit=options.get("limit", None),
                    reverse=options.get("reverse", True),
                    mindate=f"{year}-01-01",
                    maxdate=f"{year}-12-31",
                )

    def _get_retraction_ids(
        self,
        skip_existing,
        limit=None,
        reverse=True,
        mindate=None,
        maxdate=None,
    ):
        PM_SEARCH = (
            "http://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
            "esearch.fcgi?db=pubmed&retmode=json&retmax=9999&"
        )
        url = PM_SEARCH + "term=retraction%20of%20publication[Publication%20Type]"
        if mindate and maxdate:
            logging.warning(f"Using date range {mindate} to {maxdate}")
            url += f"&mindate={mindate}&maxdate={maxdate}"

        resp = fetch_utils.fetch_url(url=url, is_scopus=False).json()
        count = resp["esearchresult"]["count"]
        retmax = resp["esearchresult"]["retmax"]
        if count > retmax:
            raise Exception(
                f"There are {count} items, but only {retmax} returned. Try using min and max date to narrow the query"
            )

        pmids = self._get_pubmed_ids_from_results(resp)
        logging.info("PMIDs found: %d", len(pmids))

        if skip_existing:
            pmids = set(pmids) - set(
                RetractionNotice.objects.values_list("pmid", flat=True)
            )
            logging.info("Skipping existing, new PMIDs found: %d", len(pmids))

        if reverse:
            pmids.reverse()

        if limit:
            pmids = pmids[:limit]
            logging.info("Only downloading: %d", limit)
        self._process_notice_pmids(pmids)

    def _process_notice_pmids(self, pmids):
        """
        Takes a list of PMIDs of retraction notices. For each one, if it isn't
        in the database looks it up and adds it and the retracted papers it
        points to.
        Optionally reverse the list to start with the oldest retractions first
        """
        for i, pmid in enumerate(pmids):
            # if there are exceptions, don't save any updates about a paper
            with django.db.transaction.atomic():
                logging.info(
                    "---------- PMID: %s Progress: %d / %d ----------",
                    pmid,
                    i,
                    len(pmids),
                )
                try:
                    RetractionNotice.objects.get(pmid=pmid)
                    logging.info("Already exists! PMID %s", pmid)
                except RetractionNotice.DoesNotExist:
                    logging.info("Creating new retraction notice: PMID %s", pmid)
                    self._get_and_update(pmid, is_notice=True)

    def _get_and_update(self, pmid, is_notice):
        """
        For a given PMID, extract information and create or update the entry.
        For retraction notices, look for an associated paper with a PMID.
        """

        resp_xml = pubmed.get_paper_xml(pmid)

        info = pubmed.get_paper_info_from_pubmed_xml(resp_xml)
        info["pmid"] = pmid
        info["is_notice"] = is_notice
        info["papers"] = []

        if not is_notice:
            paper = self._create_or_update_item(info, pmid, is_notice)
            return paper

        paper_pmids = pubmed.get_related_pmid_from_notice_xml(resp_xml)
        if len(paper_pmids) <= 0:
            logging.warning(
                "Only creating notice for PMID %s. "
                "No retracted papers found in retraction notice.",
                pmid,
            )
            info["paper"] = None
        for paper_pmid in paper_pmids:
            try:
                paper = RetractedPaper.objects.get(pmid=paper_pmid)
            except RetractedPaper.DoesNotExist:
                paper = self._get_and_update(paper_pmid, is_notice=False)
            info["papers"].append(paper)

        paper = self._create_or_update_item(info, pmid, is_notice=True)
        return paper

    def _get_pubmed_ids_from_results(self, data):
        retraction_ids = data["esearchresult"]["idlist"]
        return retraction_ids

    def _create_or_update_item(self, info, pmid, is_notice=False):
        """
        Given a PMID + data, create or update the associated paper or
        retraction notice.
        """
        if is_notice:
            item, created = RetractionNotice.objects.get_or_create(pmid=pmid)
            item.papers.add(*info["papers"])
        else:
            item, created = RetractedPaper.objects.get_or_create(pmid=pmid)
        item.title = info["title"]
        if info["doi"] is None:
            item.doi = None
        else:
            # 10.2119/2006–00039.Gu PMID 17380192 has this unicode hyphen in it
            item.doi = info["doi"].replace("–", "-")
        item.issn = info["issn"]
        item.journaltitle = info["journaltitle"]
        item.journal_iso = info["journal_iso"]
        item.artdate = info["artdate"]
        item.journaldate = info["journaldate"]
        item.journaldate_granularity = info["journaldate_granularity"]
        item.pub_types = info["pub_types"]
        item.save()
        return item
