import logging
from collections import Counter

import schemdraw
from django.core.management import BaseCommand
from schemdraw import flow

from common import setup
from retractions.models import RetractedPaper, RetractionNotice


def flowchart():
    """
    Create inclusion/exclusion flowchart
    """
    notices = RetractionNotice.objects.count()
    total = RetractedPaper.objects.count()
    reason_counts = Counter(
        RetractedPaper.objects.values_list("exclusion_reason", flat=True)
    )
    logging.info(f"Reason counts {reason_counts}")
    intervention = RetractedPaper.objects.filter(rct_group="i").count()
    control = RetractedPaper.objects.filter(rct_group="c").count()
    with schemdraw.Drawing(file="flowchart.svg") as d:
        d.config(fontsize=10)
        d += flow.Start(w=6, h=2).label(
            f"Retraction notices\nindexed in pubmed\nn={notices}"
        )
        d += flow.Arrow().down(d.unit / 2)
        d += flow.Box(w=6, h=2).label(
            f"Retracted papers\nlinked in those notices\nn={total}"
        )
        d += flow.Arrow().down(d.unit / 2)
        d += (step2 := flow.Box(w=0, h=0))
        d += flow.Arrow().down(d.unit / 2)
        d += (step3 := flow.Box(w=0, h=0))
        d += flow.Arrow().down(d.unit / 2)
        d += (step4 := flow.Box(w=0, h=0))
        d += flow.Arrow().down(d.unit / 2)
        d += (step5 := flow.Box(w=0, h=0))
        d += flow.Arrow().down(d.unit / 2)
        d += (step6 := flow.Box(w=0, h=0))
        d += flow.Arrow().down(d.unit / 2)
        d += (
            rand := flow.Box(w=6, h=2).label(f"Randomised\nn={intervention + control}")
        )
        d += flow.Arrow().theta(-45)
        d += flow.Box(w=6, h=2).label(f"Email\nn={intervention}")
        d.move_from(rand.S)
        d += flow.Arrow().theta(-135)
        d += flow.Box(w=6, h=2).label(f"No email\nn={control}")

        # Exclusions
        d.config(fontsize=8)
        d += flow.Arrow().right(d.unit / 4).at(step2.E)
        d += (
            flow.Box(w=6, h=1)
            .anchor("W")
            .label(f"Excluded pilot n={reason_counts['Pilot']}")
        )

        d += flow.Arrow().right(d.unit / 4).at(step3.E)
        d += (
            flow.Box(w=6, h=1)
            .anchor("W")
            .label(
                "Excluded no date for retraction notice"
                f" n={reason_counts['No date for retraction notice']}"
            )
        )
        d += flow.Arrow().right(d.unit / 4).at(step4.E)
        d += (
            flow.Box(w=6, h=1)
            .anchor("W")
            .label(
                "Excluded no date for retracted paper"
                f" n={reason_counts['No date for retracted paper']}"
            )
        )
        d += flow.Arrow().right(d.unit / 4).at(step5.E)
        d += (
            flow.Box(w=6, h=1)
            .anchor("W")
            .label(
                "Excluded published before 2000"
                f" n={reason_counts['Published before 2000']}"
            )
        )
        d += flow.Arrow().right(d.unit / 4).at(step6.E)
        d += (
            flow.Box(w=6, h=1)
            .anchor("W")
            .label(
                "Excluded no contactable authors"
                f" n={reason_counts['No contactable authors']}"
            )
        )


class Command(BaseCommand):
    help = """Generate dataset for power calculations and analysis
    """  # noqa: A003

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        flowchart()
