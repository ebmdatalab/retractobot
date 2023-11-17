import argparse
import datetime
import logging

from django.core.management.base import BaseCommand
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q

import retractions.pubmed as pubmed
from common import fetch_utils, setup
from retractions.models import Author, AuthorAlias, CitingPaper


def pos_int(val):
    ival = int(val)
    if ival <= 0:
        raise argparse.ArgumentTypeError("Batch must be a positive int")
    return ival


def valid_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = f"not a valid date: {s!r}"
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    args = ""
    help = """Updates papers that cite retracted papers using metadata from
    scopus and pubmed. Only those papers missing data expected to be
    found in the respective sources will be scraped and updated."""  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument(
            "--scopus-only",
            action="store_true",
            help="Only update papers with data missing from Scopus",
        )
        parser.add_argument(
            "--pubmed-only",
            action="store_true",
            help="Only update papers with data missing from Pubmed",
        )
        parser.add_argument(
            "--batch",
            type=pos_int,
            help="Update database after batch size papers",
        )
        parser.add_argument(
            "--created-after",
            type=valid_date,
            required=False,
            help="Only download for papers created after this date",
        )
        parser.add_argument(
            "--skip-errors",
            action="store_true",
            help="Skip papers that previously had an error",
        )

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        both = not options["scopus_only"] and not options["pubmed_only"]
        batch = options.get("batch")
        created_after = options.get("created_after", None)
        skip_errors = options.get("skip_errors")
        if options["scopus_only"] or both:
            self.update_citing_papers_scopus(
                batch=batch,
                created_after=created_after,
                skip_errors=skip_errors,
            )
        if options["pubmed_only"] or both:
            self.update_citing_papers_pubmed(
                batch=batch,
                created_after=created_after,
                skip_errors=skip_errors,
            )

    def update_citing_papers_scopus(
        self, batch=None, created_after=None, skip_errors=False
    ):
        """Scopus provides things like DOI, Pubmed ID, title, some dates, and
        authors.

        """
        papers_to_get = CitingPaper.objects.filter(
            title__isnull=True, journalname__isnull=True
        )
        if created_after:
            papers_to_get = papers_to_get.filter(created_at__gte=created_after)
        if skip_errors:
            papers_to_get = papers_to_get.exclude(errors="Scopus returned None")
        self._paginate(papers_to_get, batch, self._set_scopus_details_parallel)

    def update_citing_papers_pubmed(
        self, batch=None, created_after=None, skip_errors=False
    ):
        """Pubmed provides journal date, journal title, and publication types
        In order for a pubmed query to be successful, one of doi or pubmed id
        must be available
        """
        papers_to_get = CitingPaper.objects.filter(
            journaldate__isnull=True,
            pub_types__len=0,
            journaltitle__isnull=True,
        ).filter(Q(doi__isnull=False) | Q(pmid__isnull=False))
        if created_after:
            papers_to_get = papers_to_get.filter(created_at__gte=created_after)
        if skip_errors:
            papers_to_get = papers_to_get.exclude(
                Q(errors="phrasesnotfound")
                | Q(errors="Found no results searching for DOI")
                | Q(errors="Pubmed returned no data")
            )
        self._paginate(papers_to_get, batch, self._set_pubmed_details_parallel)

    def _paginate(self, papers_to_get, batch, paginated_function):
        # NOTE: paginate a list (rather than a queryset) of objects because
        # parallelisation dynamically changes the queryset in the background
        # resulting in some objects being skipped
        papers_to_get = list(
            papers_to_get.order_by("-scopus_id").values_list("scopus_id", flat=True)
        )
        total = len(papers_to_get)
        if total == 0:
            logging.info("No papers to get")
            return

        logging.info(f"Getting details of {total} citing papers in parallel")

        if not batch:
            batch = total
        paginator = Paginator(papers_to_get, batch)
        for i in paginator.page_range:
            page = paginator.page(i)
            ids = page.object_list
            objects = CitingPaper.objects.filter(scopus_id__in=ids)
            logging.info(f"({i}/{paginator.num_pages}) {len(ids)} {objects.count()}")
            paginated_function(objects)

        logging.info(f"Got details of {total} citing papers in parallel")

    def _set_scopus_details_parallel(self, citing_papers):
        urls = [c.scopus_paper_url() for c in citing_papers]
        rs = fetch_utils.fetch_urls_parallel(urls, is_scopus=True)
        datas = [
            self._process_scopus_json(r.json(), citing_paper)
            if r is not None
            else {
                "errors": "Scopus returned None",
                "scopus_id": citing_paper.scopus_id,
            }
            for r, citing_paper in zip(rs, citing_papers)
        ]
        for citing_paper_data in datas:
            try:
                scopus_id = citing_paper_data["eid"].replace("2-s2.0-", "")
            except KeyError:
                scopus_id = citing_paper_data["scopus_id"]
            logging.info(f"Updating citing paper {scopus_id} from scopus")
            self._update_citing_paper(scopus_id, citing_paper_data)

    def _set_pubmed_details_parallel(self, citing_papers):
        logging.info("Getting PMID for citing papers in parallel via DOI")

        def use_doi(paper):
            return paper.doi

        pmids_via_doi = pubmed.get_pmid_via_dois_parallel(
            [use_doi(paper) for paper in citing_papers]
        )
        logging.info("Got PMIDS via DOI %s", str(pmids_via_doi))
        data = []
        for paper, pmid_tuple in zip(citing_papers, pmids_via_doi):
            if not pmid_tuple:
                pmid_via_doi = None
                errors = None
            else:
                pmid_via_doi, errors = pmid_tuple
            if paper.pmid and pmid_via_doi and paper.pmid != pmid_via_doi:
                logging.error(
                    f"stored pmid: {paper.pmid} does not match pmid via doi: {pmid_via_doi}, using {pmid_via_doi}"
                )
            datum = {}
            # Merge together our two sources of PMID.
            # Prefer pubmed as scopus can be wrong
            datum["pubmed-id"] = pmid_via_doi or paper.pmid
            datum["scopus_id"] = paper.scopus_id
            if errors:
                datum["errors"] = errors
            data.append(datum)
        combined_pmids = [x["pubmed-id"] for x in data]
        logging.info("Combined PMIDS %s", str(combined_pmids))
        logging.info("Getting pubmed details for citing papers in parallel via PMID")
        pmid_xmls = pubmed.get_paper_xml_parallel(combined_pmids)
        datas = [
            self._add_pmid_info(data, pmid_xml)
            for data, pmid_xml in zip(data, pmid_xmls)
        ]
        for citing_paper_data in datas:
            logging.info(
                "Updating citing paper %s from pubmed",
                citing_paper_data["pubmed-id"],
            )
            self._update_citing_paper(citing_paper_data["scopus_id"], citing_paper_data)

    def _add_pmid_info(self, data, pmid_xml):
        if pmid_xml:
            pubmed_info = pubmed.get_paper_info_from_pubmed_xml(pmid_xml)

            logging.info(
                "   Citing paper PMID info %s %s dates %s %s %s",
                data["pubmed-id"],
                data["scopus_id"],
                pubmed_info["journaldate"],
                pubmed_info["artdate"],
                pubmed_info["pub_types"],
            )

            data["pubmed_journaldate"] = pubmed_info["journaldate"]
            data["pubmed_journaldate_granularity"] = pubmed_info[
                "journaldate_granularity"
            ]
            data["pubmed_journaltitle"] = pubmed_info["journaltitle"]
            data["pubmed_artdate"] = pubmed_info["artdate"]
            data["pubmed_pub_types"] = pubmed_info["pub_types"]
            if pubmed_info.get("errors"):
                data["errors"] = pubmed_info["errors"]
        return data

    def _process_scopus_json(self, res, citing_paper):
        data = {}
        fields = [
            "eid",
            "pubmed-id",
            "prism:doi",
            "prism:issn",
            "dc:title",
            "prism:publicationName",
            "prism:coverDate",
        ]
        for f in fields:
            data[f] = None
        data["authors"] = []

        if "abstracts-retrieval-response" not in res:
            raise Exception("No abstracts-retrieval-response")
        arr = res["abstracts-retrieval-response"]

        d = arr["coredata"]
        for f in fields:
            if f in d:
                data[f] = d[f]
        item = arr["item"]
        if (
            "bibrecord" in item
            and "head" in item["bibrecord"]
            and "author-group" in item["bibrecord"]["head"]
        ):
            author_group = item["bibrecord"]["head"]["author-group"]
            if isinstance(author_group, dict):
                if "author" in author_group:
                    if isinstance(author_group["author"], dict):
                        data["authors"] += [author_group["author"]]
                    else:
                        data["authors"] += author_group["author"]
            else:
                for a in author_group:
                    if "author" in a:
                        if isinstance(a["author"], dict):
                            data["authors"] += [a["author"]]
                        else:
                            data["authors"] += a["author"]

        # For debugging write out dates separately
        info = {
            "doi": data["prism:doi"],
            "dc:title": data["dc:title"],
            "prism:publicationName": data["prism:publicationName"],
            "prism:coverDate": data["prism:coverDate"],
        }
        # Pubmed pmid is more reliable, so do not overwrite existing pmid
        if not citing_paper.pmid:
            info["pubmed-id"] = data["pubmed-id"]

        def _scopus_json_date(d):
            if d is None:
                return None
            if "@year" in d:
                assert d["@year"].isdigit()
                assert d["@month"].isdigit()
                assert d["@day"].isdigit()
                return datetime.date(int(d["@year"]), int(d["@month"]), int(d["@day"]))
            assert d["year"].isdigit()
            y = int(d["year"])
            if "month" in d:
                assert d["month"].isdigit()
                m = int(d["month"])
            else:
                m = 1
            if "day" in d:
                assert d["day"].isdigit()
                d = int(d["day"])
            else:
                d = 1
            return datetime.date(y, m, d)

        def _scopus_text_date(d):
            if d is None:
                return None
            if "date-text" not in d:
                return None
            if isinstance(d["date-text"], str):
                t = d["date-text"]
            else:
                t = d["date-text"]["$"]
            try:
                return datetime.datetime.strptime(t, "%d %B %Y").date()
            except ValueError:
                try:
                    return datetime.datetime.strptime(t, "%B %Y").date()
                except ValueError:
                    try:
                        return datetime.datetime.strptime(t, "%Y").date()
                    except ValueError:
                        try:
                            return datetime.datetime.strptime(t, "%B %d, %Y").date()
                        except ValueError:
                            try:
                                return datetime.datetime.strptime(t, "%b-%Y").date()
                            except ValueError:
                                return None

        def _safeget(dct, *keys):
            for key in keys:
                try:
                    dct = dct[key]
                except KeyError:
                    return None
            return dct

        info["ait:date-sort"] = _scopus_json_date(
            _safeget(arr, "item", "ait:process-info", "ait:date-sort")
        )
        info["ait:date-delivered"] = _scopus_json_date(
            _safeget(arr, "item", "ait:process-info", "ait:date-delivered")
        )
        info["bibrecord:date-created"] = _scopus_json_date(
            _safeget(
                arr,
                "item",
                "bibrecord",
                "item-info",
                "history",
                "date-created",
            )
        )
        info["bibrecord:publicationdate:numeric"] = _scopus_json_date(
            _safeget(arr, "item", "bibrecord", "head", "source", "publicationdate")
        )
        info["bibrecord:publicationdate:text"] = _scopus_text_date(
            _safeget(arr, "item", "bibrecord", "head", "source", "publicationdate")
        )
        info["bibrecord:confdate:startdate"] = _scopus_json_date(
            _safeget(
                arr,
                "item",
                "bibrecord",
                "head",
                "source",
                "additional-srcinfo",
                "conferenceinfo",
                "confevent",
                "confdate",
                "startdate",
            )
        )
        info["bibrecord:confdate:enddate"] = _scopus_json_date(
            _safeget(
                arr,
                "item",
                "bibrecord",
                "head",
                "source",
                "additional-srcinfo",
                "conferenceinfo",
                "confevent",
                "confdate",
                "enddate",
            )
        )

        data.update(info)
        return data

    def _update_citing_paper(self, scopus_id, data):
        with transaction.atomic():
            logging.info("  Updating citing paper Scopus ID %s", scopus_id)
            citingpaper = CitingPaper.objects.get(scopus_id=scopus_id)
            if "errors" in data:
                citingpaper.errors = data["errors"]
            if "dc:title" in data:
                citingpaper.title = data["dc:title"]
            if "pubmed-id" in data:
                citingpaper.pmid = data["pubmed-id"]
            if "prism:doi" in data:
                citingpaper.doi = data["prism:doi"]
            if "prism:issn" in data:
                citingpaper.issn = data["prism:issn"]
            if "prism:publicationName" in data:
                citingpaper.journalname = data["prism:publicationName"]
            if "prism:coverDate" in data:
                citingpaper.prismcoverdate = data["prism:coverDate"]
            if "pubmed_journaldate" in data:
                citingpaper.journaldate = data["pubmed_journaldate"]
                citingpaper.journaldate_granularity = data[
                    "pubmed_journaldate_granularity"
                ]
            if "pubmed_journaltitle" in data:
                citingpaper.journaltitle = data["pubmed_journaltitle"]
            if "pubmed_artdate" in data:
                citingpaper.artdate = data["pubmed_artdate"]
            if "pubmed_pub_types" in data:
                citingpaper.pub_types = data["pubmed_pub_types"]
            citingpaper.save()

            if "authors" in data and data["authors"]:
                authors = data["authors"]
                for i, a in enumerate(authors):
                    given_name = None
                    surname = None
                    auid = None
                    if "@auid" in a:
                        auid = a["@auid"]
                    if "preferred-name" in a:
                        p = a["preferred-name"]
                        surname = p["ce:surname"]
                        if "ce:given-name" in p:
                            given_name = p["ce:given-name"]
                        elif "ce:initials" in p:
                            given_name = p["ce:initials"]
                    else:
                        if "ce:surname" in a:
                            surname = a["ce:surname"]
                        if "ce:given-name" in a:
                            given_name = a["ce:given-name"]
                        elif "ce:initials" in a:
                            given_name = a["ce:initials"]
                    email_address = None
                    if "ce:e-address" in a:
                        email_address = a["ce:e-address"]["$"]

                    author, created = Author.objects.get_or_create(auid=auid)
                    author.save()
                    author.citing_papers.add(citingpaper)

                    author_alias, created = AuthorAlias.objects.get_or_create(
                        author=author,
                        email_address__iexact=email_address,
                        defaults={
                            "email_address": email_address,
                            "surname": surname,
                            "given_name": given_name,
                        },
                    )
                    author_alias.save()
