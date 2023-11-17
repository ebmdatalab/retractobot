import argparse
import datetime
import logging
import pathlib
import random
from collections import Counter
from datetime import timedelta
from functools import partial
from multiprocessing import Pool

import numpy
import pandas
from django.core.exceptions import EmptyResultSet
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.db.models import Case, Count, Max, Min, Q, Value, When
from tableone import TableOne

from common import setup
from retractions.models import CitationRetractionPair, CitingPaper, RetractedPaper


pilot = [
    "160560",
    "221532",
    "307018",
    "360062",
    "370596",
    "396398",
    "423962",
    "778343",
    "1281519",
    "1302352",
    "1324627",
    "1339389",
    "1343090",
    "1348070",
    "1359211",
]

manual_cuts = {
    0: 0,
    10: 1,
    20: 2,
    50: 3,
    100: 4,
    500: 5,
    1000: 6,
    1500: 7,
    5000: 8,
}


def valid_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        msg = f"Not a valid date: {s!r}"
        raise argparse.ArgumentTypeError(msg)


def update_exclusions(reset=True):
    if reset:
        RetractedPaper.objects.update(rct_group=None, exclusion_reason=None)
        call_command("update_comparison_date")
        call_command("contactable_authors")

    # At the retracted paper level

    # Skip if pilot paper
    count = (
        RetractedPaper.objects.filter(rct_group__isnull=True)
        .filter(pmid__in=pilot)
        .update(rct_group="x", exclusion_reason="Pilot")
    )
    logging.info(f"Excluded {count} in pilot")
    # Skip if no date
    count = (
        RetractedPaper.objects.filter(rct_group__isnull=True)
        .filter(comparisondate__isnull=True)
        .update(rct_group="x", exclusion_reason="No date for retracted paper")
    )
    logging.info(f"Excluded {count} with no retracted date ")
    # Skip if before 2000
    count = (
        RetractedPaper.objects.filter(rct_group__isnull=True)
        .filter(comparisondate__year__lt=2000)
        .update(rct_group="x", exclusion_reason="Published before 2000")
    )
    logging.info(f"Excluded {count} published before 2000")
    # Skip if no notice date
    count = (
        RetractedPaper.objects.annotate(latest_notice=Max("notices__comparisondate"))
        .filter(rct_group__isnull=True)
        .filter(latest_notice__isnull=True)
        .update(rct_group="x", exclusion_reason="No date for retraction notice")
    )
    logging.info(f"Excluded {count} with no retraction date")
    contactable = CitationRetractionPair.objects.exclude(
        contactable_authors__isnull=True
    )
    pmids = set(contactable.values_list("retractedpaper__pmid", flat=True))
    count = (
        RetractedPaper.objects.filter(rct_group__isnull=True)
        .exclude(pmid__in=pmids)
        .update(rct_group="x", exclusion_reason="No contactable authors")
    )
    logging.info(f"Excluded {count} with no contactable citing authors")

    reason_counts = Counter(
        RetractedPaper.objects.values_list("exclusion_reason", flat=True)
    )
    logging.info(f"Exclusion summary: {reason_counts}")


def gen_simulation(options):
    randomisation_year = options["simulated_randomisation_year"]
    simulation_file = options["simulation_file"]
    num_simulations = options["num_simulations"]
    # Exclude x in case there is a stored randomisation in the db
    papers = (
        RetractedPaper.objects.annotate(
            earliest_notice=Min("notices__comparisondate__year")
        )
        .exclude(rct_group="x")
        .filter(comparisondate__year__lte=randomisation_year)
        .filter(earliest_notice__lte=randomisation_year)
    )
    papers = _annotate_count_unique(papers, randomisation_year)
    papers = papers.exclude(count_unique=0)
    decile_cuts = numpy.quantile(
        list(papers.values_list("count_unique", flat=True)),
        numpy.arange(0.1, 1.1, 0.1),
    )
    decile_dict = {round(cut): index for index, cut in enumerate(decile_cuts, start=1)}
    decile_dict[0] = 0
    papers = _annotate_strata(papers, "groups", manual_cuts, update=False)
    papers = _annotate_strata(papers, "deciles", decile_dict, update=False)

    res_groups = _randomise_parallel_or_update(
        papers, "groups", update=False, count=num_simulations
    )
    res_deciles = _randomise_parallel_or_update(
        papers, "deciles", update=False, count=num_simulations
    )
    randomisations = pandas.concat([res_groups, res_deciles], axis=1)
    randomisations.index.name = "pmid"

    # Count the papers that cited in the year after randomisation
    # Ignore the wash out period in simulation, as there's no intervention
    papers = papers.annotate(
        citation_count=Count(
            "citationretractionpair",
            filter=Q(
                citationretractionpair__citingpaper__comparisondate__year=randomisation_year
                + 1
            ),
            distinct=True,
        )
    )
    papers = papers.annotate(earliest_notice=Min("notices__comparisondate__year"))
    df = pandas.DataFrame(
        papers.values(
            "pmid",
            "count_unique",
            "citation_count",
            "groups",
            "deciles",
            "comparisondate__year",
            "earliest_notice",
        )
    )
    df = df.set_index("pmid")
    df = pandas.merge(df, randomisations, on="pmid")
    df["years_since_retraction"] = randomisation_year - df["earliest_notice"]
    df["years_since_publication"] = randomisation_year - df["comparisondate__year"]
    df["years_since_retraction_q4"] = pandas.qcut(
        df.years_since_retraction, q=4, labels=[0, 1, 2, 3]
    )
    df["years_since_publication_q4"] = pandas.qcut(
        df.years_since_publication, q=4, labels=[0, 1, 2, 3]
    )
    df.to_csv(simulation_file)


def set_randomisation(options):
    if (
        CitationRetractionPair.objects.filter(contactable_authors__isnull=False).count()
        == 0
    ):
        raise EmptyResultSet(
            "No contactable authors, did you run 'contactable_authors'?"
        )

    # Set all citing papers as cited_in_rct
    # Pre-rct citing paper authors are used in stratification
    CitingPaper.objects.update(cited_in_rct=True)

    randomisation_year = datetime.datetime.now().date().year
    just_check = options["just_check"]
    if just_check:
        print(check_randomisation(randomisation_year).tabulate(tablefmt="fancy_grid"))
        return
    if (
        not RetractedPaper.objects.filter(Q(rct_group="c") | Q(rct_group="i")).count()
        == 0
    ):
        raise AssertionError("Should not randomise twice")
    papers = RetractedPaper.objects.filter(rct_group__isnull=True)
    if papers.count() == 0:
        return
    papers = _annotate_count_unique(papers)
    papers = _annotate_strata(papers, "groups", manual_cuts, update=True)
    _randomise_parallel_or_update(papers, "stratifying_group", update=True)
    table1 = check_randomisation(randomisation_year)
    logging.info(table1.tabulate(tablefmt="fancy_grid"))


def check_randomisation(randomisation_year):
    papers = RetractedPaper.objects.filter(Q(rct_group="c") | Q(rct_group="i"))
    papers = _annotate_count_unique(papers)
    papers = papers.annotate(earliest_notice=Min("notices__comparisondate__year"))
    df = pandas.DataFrame(
        papers.values(
            "pmid",
            "rct_group",
            "stratifying_group",
            "count_unique",
            "comparisondate__year",
            "earliest_notice",
        )
    )
    df["years_since_retraction"] = randomisation_year - df["earliest_notice"]
    df["years_since_publication"] = randomisation_year - df["comparisondate__year"]

    df = df.set_index("pmid")
    try:
        table1 = TableOne(
            df,
            categorical=["stratifying_group"],
            groupby=["rct_group"],
            nonnormal=[
                "count_unique",
                "years_since_retraction",
                "years_since_publication",
            ],
            pval=True,
        )
    except ValueError:
        table1 = TableOne(
            df,
            categorical=["stratifying_group"],
            groupby=["rct_group"],
            nonnormal=[
                "count_unique",
                "years_since_retraction",
                "years_since_publication",
            ],
            pval=False,
        )
    return table1


def _annotate_strata(papers, stratifying_name, stratifying_dict, update=True):
    whens = [
        When(count_unique__gte=k, then=Value(v))
        for k, v in sorted(stratifying_dict.items(), reverse=True)
    ]
    annotation = {f"{stratifying_name}": Case(*whens)}
    papers = papers.annotate(**annotation)
    if update:
        with transaction.atomic():
            for paper in papers:
                paper.stratifying_group = getattr(paper, stratifying_name)
                paper.save(update_fields=["stratifying_group"])
    return papers


def _annotate_count_unique(papers, randomisation_year=None):
    # When running a simulation, we want to use the date not the rct field
    if randomisation_year:
        papers = papers.annotate(
            count_unique=Count(
                "citationretractionpair__contactable_authors",
                filter=Q(
                    citationretractionpair__citingpaper__comparisondate__year__lte=randomisation_year
                ),
                distinct=True,
            )
        )
    else:
        papers = papers.annotate(
            count_unique=Count(
                "citationretractionpair__contactable_authors",
                filter=Q(citationretractionpair__citingpaper__cited_in_rct=True),
                distinct=True,
            )
        )
    return papers


def _randomise(df, stratifying_name="groups"):
    groups = df.groupby(stratifying_name)
    intervention = []
    control = []
    for group_name, group_data in groups:
        logging.info(f"Randomising {stratifying_name:} {group_name}")
        group_data["random"] = numpy.random.random(len(group_data))
        group_data = group_data.sort_values(by="random")
        pmids = list(group_data.pmid)
        total = len(pmids)
        intervention += pmids[0 : total // 2]
        control += pmids[-(total // -2) :]
        # Randomly assign middle value if there are an odd number of values
        middle = pmids[(total // 2) : -(total // -2)]
        if random.randint(0, 1):
            intervention += middle
        else:
            control += middle
    # Difference should be bounded by the number of strata
    assert len(set(control)) + len(set(intervention)) == len(df)
    assert abs(len(set(control)) - len(set(intervention))) <= len(groups)
    return pandas.concat(
        [
            pandas.Series("i", index=intervention),
            pandas.Series("c", index=control),
        ]
    )


def _randomise_parallel_or_update(papers, stratifying_name, update=True, count=1):
    df = pandas.DataFrame(papers.values("pmid", stratifying_name))
    df.sort_values(by="pmid", inplace=True)
    with Pool(2) as pool:
        res = pool.map(
            partial(_randomise, stratifying_name=stratifying_name),
            count * [df],
        )
    if count == 1 and update:
        logging.info("Updating database with randomisation")
        s = res[0]
        intervention = list(s[s == "i"].index)
        control = list(s[s == "c"].index)
        RetractedPaper.objects.filter(pmid__in=intervention).update(rct_group="i")
        RetractedPaper.objects.filter(pmid__in=control).update(rct_group="c")
    elif update:
        logging.error(
            f"Update was specified, but {count} randomisations were requested"
        )
        return

    randomisations = pandas.concat(
        res,
        axis=1,
        keys=[f"trt_{stratifying_name}_{index}" for index in range(count)],
    )
    return randomisations


def _compute_contamination():
    """
    Get pmids of any papers that had a contactable author in both groups at
    time of randomisation
    """
    intervention_authors = (
        CitationRetractionPair.objects.filter(citingpaper__cited_in_rct=True)
        .filter(retractedpaper__rct_group="i")
        .values_list("contactable_authors", flat=True)
    )
    logging.info("Got intervention authors")
    control_authors = (
        CitationRetractionPair.objects.filter(citingpaper__cited_in_rct=True)
        .filter(retractedpaper__rct_group="c")
        .values_list("contactable_authors", flat=True)
    )
    logging.info("Got control authors")
    contaminated_authors = set(intervention_authors).intersection(set(control_authors))
    return set(
        CitationRetractionPair.objects.filter(citingpaper__cited_in_rct=True)
        .filter(Q(retractedpaper__rct_group="i") | Q(retractedpaper__rct_group="c"))
        .filter(contactable_authors__in=contaminated_authors)
        .values_list("retractedpaper__pmid", flat=True)
    )


def gen_dataset(options):
    follow_up_date = options["follow_up_date"]
    output_file = options["output_file"]
    papers = RetractedPaper.objects.filter(
        Q(rct_group="i") | Q(rct_group="c")
    ).annotate(
        citation_count=Count(
            "citationretractionpair",
            filter=Q(citationretractionpair__citingpaper__cited_in_rct=False)
            & Q(citationretractionpair__citingpaper__comparisondate__gte=follow_up_date)
            & Q(
                citationretractionpair__citingpaper__comparisondate__lte=(
                    follow_up_date + timedelta(days=365)
                )
            ),
            distinct=True,
        )
    )
    if not papers:
        raise EmptyResultSet("No randomised retracted papers found")
    papers = _annotate_count_unique(papers)
    papers = _annotate_strata(papers, "groups", manual_cuts, update=True)
    papers = papers.annotate(earliest_notice=Min("notices__comparisondate__year"))
    logging.info("Annoted notice date")
    logging.info("Getting dataframe")
    # TODO: translate c/i to 0/1
    df = pandas.DataFrame(
        papers.values(
            "pmid",
            "rct_group",
            "stratifying_group",
            "citation_count",
            "count_unique",
            "comparisondate__year",
            "earliest_notice",
        )
    )
    logging.info("Got dataframe")
    df["years_since_retraction"] = follow_up_date.year - df["earliest_notice"]
    df["years_since_publication"] = follow_up_date.year - df["comparisondate__year"]
    pmids = _compute_contamination()
    df = df.set_index("pmid")
    df["contaminated"] = df.index.isin(pmids)
    df.to_csv(output_file)


class Command(BaseCommand):
    help = """Set up the RCT and generate datasets in csv format for analysis"""  # noqa: A003

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers()
        inclusion_parser = subparsers.add_parser(
            "update_exclusions",
            help="Update database with inclusion/exclusion criteria",
        )
        inclusion_parser.set_defaults(func=update_exclusions)
        randomisation_parser = subparsers.add_parser(
            "set_randomisation",
            help=(
                "Run actual randomisation. Log level 2 outputs table1 to"
                " spot check randomisation"
            ),
        )
        randomisation_parser.set_defaults(func=set_randomisation)
        randomisation_parser.add_argument(
            "--just-check",
            action="store_true",
            help="Print table1 to spot check randomisation",
        )
        simulation_parser = subparsers.add_parser("simulate", help="Run simulation")
        simulation_parser.set_defaults(func=gen_simulation)
        simulation_parser.add_argument(
            "--simulated-randomisation-year",
            type=int,
            help="Simulated randomisation year",
        )
        simulation_parser.add_argument(
            "--simulation-file",
            type=pathlib.Path,
            required=True,
            help="Randomisation dataset filename",
        )
        simulation_parser.add_argument(
            "--num-simulations",
            type=int,
            required=False,
            default=500,
            help="Number of randomisations",
        )
        dataset_parser = subparsers.add_parser(
            "gen_dataset", help="Generate analysis dataset"
        )
        dataset_parser.set_defaults(func=gen_dataset)
        dataset_parser.add_argument(
            "--follow-up-date",
            type=valid_date,
            default=datetime.datetime.now(),
            help="Citations after or equal to this date will be counted - YYYY-MM-DD format",
        )
        dataset_parser.add_argument(
            "--output-file",
            type=pathlib.Path,
            required=True,
            help="Analysis dataset filename",
        )

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        options["func"](options)
