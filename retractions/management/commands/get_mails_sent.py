import csv
import pathlib

from django.core.management import BaseCommand

from common import setup
from retractions.models import MailSent


def get_mails_sent(options):
    output_dir = options["output_dir"]
    mails_sent = MailSent.objects.all().select_related("author")

    titles = [
        "scopus_auid",
        "message_id",
        "citing_paper_ids",
        "recentest_citing_paper_id",
        "accepted",
        "delivered",
        "opened",
        "unsubscribed",
        "clicked_didntknowany",
        "clicked_alreadyknewall",
        "clicked_alreadyknewsome",
        "clicked_other",
    ]

    with open(output_dir / "mails_sent.tsv", "w") as tsv_file:
        writer = csv.writer(tsv_file, dialect=csv.excel_tab)
        writer.writerow(titles)
        for ms in mails_sent:
            fields = [
                ms.author.auid,
                ms.message_id,
                " ".join(
                    [
                        f"{pmid}:{scopus}"
                        for pmid, scopus in ms.pairs.values_list(
                            "retractedpaper__pmid", "citingpaper__scopus_id"
                        )
                    ]
                ),
                ms.recentest_citing_paper_id,
                ms.accepted,
                ms.delivered,
                ms.opened,
                ms.unsubscribed,
                ms.clicked_didntknowany,
                ms.clicked_alreadyknewall,
                ms.clicked_alreadyknewsome,
                ms.clicked_other,
            ]
            writer.writerow(fields)


class Command(BaseCommand):
    help = """Download a tsv with info about sent mails"""  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=pathlib.Path,
            required=True,
            help="Directory to write the file to",
        )

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        get_mails_sent(options)
