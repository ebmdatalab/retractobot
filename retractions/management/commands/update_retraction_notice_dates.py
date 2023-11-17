import lxml.etree
from django.core.management import BaseCommand

from retractions import pubmed
from retractions.models import RetractionNotice


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        notices = RetractionNotice.objects.filter(journaldate__isnull=True)

        print("Updating", len(notices), "notices")

        for notice in notices:
            xml = pubmed.get_paper_xml(notice.pmid)
            tree = lxml.etree.fromstring(xml)
            journal = tree.find(".//Article/Journal")
            journaldate = journal.find("JournalIssue/PubDate")
            jdate = pubmed.get_pubmed_date_from_node(journaldate)
            if jdate["date"]:
                notice.journaldate = jdate["date"]
                notice.journaldate_granularity = jdate["granularity"]
                print(
                    "Updating:",
                    notice.pmid,
                    notice.journaldate,
                    notice.journaldate_granularity,
                )
                notice.save()
            else:
                print("Not updating:", notice.pmid)
