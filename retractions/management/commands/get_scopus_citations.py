import logging
import time

import django.db.transaction
import requests_cache
from django.conf import settings
from django.core.management.base import BaseCommand

from common import fetch_utils, setup
from retractions.models import CitingPaper, RetractedPaper


class Command(BaseCommand):
    """
    Regular task.
    """

    args = ""
    help = """Gets citations of retracted papers from Scopus.
    Use Scopus API to find papers citing retracted papers.
    Add any previously-unknown citing papers to our database."""  # noqa: A003

    API_URL = "https://api.elsevier.com/content/search/scopus?"
    PARAMS = {"httpAccept": "application/json"}

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        if settings.CACHE_API_CALLS:
            logging.info("Using local cache for Scopus API calls")
            requests_cache.install_cache("cache/get_scopus_citations_cache")

        retracted_papers = RetractedPaper.objects.order_by("pmid")
        total_papers = retracted_papers.count()
        logging.info("Total papers to ensure have citations for: %d", total_papers)

        count = 1
        for retracted_paper in retracted_papers:
            with django.db.transaction.atomic():
                logging.info(
                    "---- Updating citations for PMID %s, paper %s of %s ",
                    retracted_paper.pmid,
                    count,
                    total_papers,
                )
                count += 1

                # Try to get the Scopus ID, if available.
                if not retracted_paper.scopus_id:
                    logging.info(
                        "Looking up scopus ID for PMID %s",
                        retracted_paper.pmid,
                    )
                    retracted_paper.scopus_id = self._get_scopus_id(retracted_paper)
                    retracted_paper.save()
                    if not retracted_paper.scopus_id:
                        logging.info("No Scopus ID for PMID %s", retracted_paper.pmid)
                        continue

                # Create corresponding citing papers
                logging.info(
                    "Has Scopus ID %s, updating citations",
                    retracted_paper.scopus_id,
                )
                citing_papers = self._get_citations_from_scopus(
                    retracted_paper.scopus_id
                )
                for c in citing_papers:
                    logging.debug("eid %s", c["eid"])
                    c_scopus_id = c["eid"].replace("2-s2.0-", "")
                    paper, created = CitingPaper.objects.get_or_create(
                        scopus_id=c_scopus_id,
                    )
                    paper.paper.add(retracted_paper)
                    if created:
                        logging.info("created citing paper %s", c_scopus_id)
                    else:
                        logging.debug(
                            "citing paper already exists, skipping: %s",
                            c_scopus_id,
                        )

    def _get_scopus_id(self, paper):
        """
        Given a PubMed ID, return the related Scopus ID,
        so we can query the Scopus citation API.
        Try DOI if PMID does not work.
        """
        url = self._get_scopus_id_lookup_url(paper.pmid, None)
        logging.info("Looking up Scopus ID... %s", url)
        res = self._get_json_and_retry_if_empty(url)
        scopus_id = self._get_scopus_id_from_json(res)
        if (not scopus_id) and paper.doi:
            url = self._get_scopus_id_lookup_url(None, paper.doi)
            res = self._get_json_and_retry_if_empty(url)
            scopus_id = self._get_scopus_id_from_json(res)
        if scopus_id:
            logging.info("Final Scopus ID: %s", scopus_id)
        else:
            logging.warning("Paper PMID %s not found in Scopus", paper.pmid)
        return scopus_id

    def _get_scopus_id_from_json(self, data):
        scopus_id = None
        if "search-results" in data:
            entry = data["search-results"]["entry"][0]
            if "dc:identifier" in entry:
                scopus_id = entry["dc:identifier"]
        return scopus_id

    def _get_citations_from_scopus(self, scopus_id):
        """
        Given a Scopus ID for a paper, retrieve all citing papers.
        """
        url = self._get_url_for_citations(scopus_id)
        logging.info("Getting all citations: %s", url)
        citations = self._get_citations_recursively(url, [])
        logging.info("Citations found: %d", len(citations))
        return citations

    def _get_url_for_citations(self, scopus_id):
        params = dict(self.PARAMS)
        params["field"] = "title,eid"
        params["start"] = 0
        params["count"] = 200
        params["query"] = "REFEID(2-s2.0-%s)" % scopus_id
        return self.API_URL + fetch_utils.sorted_urlencode(params)

    def _get_citations_recursively(self, url, citations):
        r = fetch_utils.fetch_url(url, is_scopus=True)
        try:
            res = r.json()
        except AttributeError:
            logging.warning("Skipping %s", url)
            return []
        citations = self._get_citations_from_json(res)
        if "search-results" in res and res["search-results"]["link"]:
            logging.info(
                "totalResults %s",
                res["search-results"]["opensearch:totalResults"],
            )
            for link in res["search-results"]["link"]:
                if isinstance(link, dict) and link["@ref"] == "next":
                    logging.info("Next link found: %s", link["@href"])
                    next_link = link["@href"].replace(":80/", "/")
                    citations += self._get_citations_recursively(next_link, citations)
                    logging.info(
                        "Done with this iteration, returning %d citations",
                        len(citations),
                    )
        return citations

    def _get_citations_from_json(self, res):
        citations = []
        if "search-results" in res:
            results = res["search-results"]
            citations += [e for e in results["entry"] if "eid" in e]
        return citations

    def _get_json_and_retry_if_empty(self, url, retry=True):
        """
        The Scopus API occasionally returns invalid JSON.
        If that happens, just wait and retry.
        """
        r = fetch_utils.fetch_url(url, is_scopus=True)
        try:
            res = r.json()
        except ValueError:
            if retry:
                time.sleep(10)
                res = self._get_json_and_retry_if_empty(url, retry=False)
            else:
                raise Exception("Bad JSON returned from Scoups API")
        return res

    def _get_scopus_id_lookup_url(self, pmid, doi):
        params = dict(self.PARAMS)
        if pmid:
            params["query"] = "PMID(%s)" % pmid
        else:
            params["query"] = 'DOI("%s")' % doi
        url = self.API_URL + fetch_utils.sorted_urlencode(params)
        return url
