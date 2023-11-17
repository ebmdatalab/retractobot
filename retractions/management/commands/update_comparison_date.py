import logging

from django.core.management import BaseCommand
from django.db.models import Case, When

from retractions.models import CitingPaper, RetractedPaper, RetractionNotice


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        logging.info(
            f"Updating comparison date for {RetractedPaper.objects.count()} "
            "retracted papers"
        )
        RetractedPaper.objects.update(
            comparisondate=Case(
                When(
                    artdate__isnull=False,
                    then="artdate",
                ),
                When(
                    journaldate__isnull=False,
                    then="journaldate",
                ),
            )
        )
        logging.info("Done")

        logging.info(
            f"Updating comparison date for {RetractionNotice.objects.count()} "
            "retraction notices"
        )
        RetractionNotice.objects.update(
            comparisondate=Case(
                When(
                    artdate__isnull=False,
                    then="artdate",
                ),
                When(
                    journaldate__isnull=False,
                    then="journaldate",
                ),
            )
        )
        logging.info("Done")

        logging.info(
            f"Updating comparison date for {CitingPaper.objects.count()} "
            "citing papers"
        )
        CitingPaper.objects.update(
            comparisondate=Case(
                When(
                    artdate__isnull=False,
                    then="artdate",
                ),
                When(
                    journaldate__isnull=False,
                    then="journaldate",
                ),
                When(
                    prismcoverdate__isnull=False,
                    then="prismcoverdate",
                ),
            )
        )
        logging.info("Done")
