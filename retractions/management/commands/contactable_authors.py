import logging

import anymail.exceptions
import anymail.utils
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import MultipleObjectsReturned
from django.core.management import BaseCommand, call_command
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q

from common import fetch_utils, setup
from retractions.models import (
    Author,
    AuthorAlias,
    CitationRetractionPair,
    RetractedPaper,
)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--batch", type=int, help="Update database after batch size papers"
        )
        parser.add_argument(
            "--get-retracted-authors",
            action="store_true",
            help="Query scopus for retracted authors",
        )

    def _set_scopus_details_parallel(self, retracted_papers):
        logging.info(
            "Getting details of %d retracted papers in parallel",
            retracted_papers.count(),
        )
        urls = [r.scopus_paper_url() for r in retracted_papers]
        rs = fetch_utils.fetch_urls_parallel(urls, is_scopus=True)
        datas = [
            self._process_scopus_json(r.json(), retracted_paper)
            for r, retracted_paper in zip(rs, retracted_papers)
            if r is not None
        ]
        for retracted_paper_data in datas:
            logging.info(
                "Updating retracted paper %s from scopus",
                retracted_paper_data["eid"],
            )
            scopus_id = retracted_paper_data["eid"].replace("2-s2.0-", "")
            self._update_retracted_paper(scopus_id, retracted_paper_data)

    def _process_scopus_json(self, res, retracted_paper):
        data = {}
        fields = ["eid"]
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
        return data

    def _update_retracted_paper(self, scopus_id, data):
        with transaction.atomic():
            # There are (rare cases) of scopus ids with more than one pubmed id
            # In the cases we have seen, one of the pubmed entries had no doi
            try:
                retracted_paper = RetractedPaper.objects.get(scopus_id=scopus_id)
            except MultipleObjectsReturned:
                logging.info(f"Multiple objects returning for {scopus_id}, using first")
                retracted_paper = (
                    RetractedPaper.objects.filter(scopus_id=scopus_id)
                    .order_by("-comparisondate")
                    .first()
                )
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
                    author.retracted_papers.add(retracted_paper)

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

    def _update_contactable_authors(self):
        """
        Filter contactable authors to those with at least one email address
        For every pair, remove retracted authors from citing authors
        (self-citing)
        """
        corrupted = []
        for alias in AuthorAlias.objects.exclude(email_address__isnull=True):
            try:
                anymail.utils.parse_single_address(alias.email_address)
            except anymail.exceptions.AnymailInvalidAddress:
                corrupted.append(alias.id)

        # Exclude citation by notice
        pairs = CitationRetractionPair.objects.exclude(
            Q(retractedpaper__notices__pmid=F("citingpaper__pmid"))
            | Q(citingpaper__pub_types__contains=["Retraction of Publication"])
        ).exclude(citingpaper__comparisondate__isnull=True)
        # Exclude if the citing paper had no date (likely no authors anyway)
        pairs = pairs.annotate(
            retracted_authors=ArrayAgg(
                "retractedpaper__authors__auid",
                distinct=True,
                filter=~Q(retractedpaper__authors__author_aliases__email_address=None),
                default=[],
            )
        ).annotate(
            citing_authors=ArrayAgg(
                "citingpaper__authors__auid",
                distinct=True,
                filter=~(
                    Q(citingpaper__authors__author_aliases__email_address=None)
                    | Q(citingpaper__authors__author_aliases__in=corrupted)
                ),
                default=[],
            )
        )

        # TODO: make this more efficient, we should not run db query in loop
        # But "add" already calls a bulk update save
        # Would need to find a better way to do the set difference query
        with transaction.atomic():
            for pair in pairs:
                authors = Author.objects.filter(
                    auid__in=list(
                        set(pair.citing_authors) - set(pair.retracted_authors)
                    )
                )
                pair.contactable_authors.clear()
                pair.contactable_authors.add(*authors)

    def handle(self, *args, **kwargs):
        setup.setup_logger(kwargs["verbosity"])
        batch = kwargs.get("batch")
        get_retracted_authors = kwargs.get("get_retracted_authors")
        if get_retracted_authors:
            papers_to_update = (
                RetractedPaper.objects.filter(scopus_id__isnull=False)
                .annotate(count=Count("authors"))
                .filter(count=0)
                .order_by("pmid")
            )

            logging.info("Querying scopus for retracted paper authors")
            if not batch:
                batch = papers_to_update.count()
            if batch == 0:
                return
            paginator = Paginator(papers_to_update, batch)
            for i in range(paginator.num_pages):
                self._set_scopus_details_parallel(paginator.get_page(i).object_list)
        logging.info("Ensuring comparison date is populated")
        call_command("update_comparison_date")
        logging.info("Starting update of contactable authors")
        self._update_contactable_authors()
        logging.info("Finished update of contactable authors")
