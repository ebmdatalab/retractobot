import random
import re
from collections import Counter

import pandas
from django.core import mail
from django.core.exceptions import EmptyResultSet
from django.core.files.temp import NamedTemporaryFile
from django.core.management import call_command
from django.test import TransactionTestCase
from django.test.utils import override_settings

from retractions.models import (
    Author,
    AuthorAlias,
    CitingPaper,
    MailSent,
    RetractedPaper,
    RetractionNotice,
)


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class ExclusionRulesTestCase(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    reset_sequences = True

    def test_in_rct_no_date(self):
        """A paper in the RCT with no date should be excluded for
        that reason."""

        # set to have no date
        retracted_paper = RetractedPaper.objects.all()[0]
        retracted_paper.journaldate = None
        retracted_paper.save()

        call_command("randomise", "update_exclusions")

        # check the paper in the database is now set in the RCT cohort as
        # excluded
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 1)
        self.assertEqual(retracted_papers[0].rct_group, "x")
        self.assertEqual(
            retracted_papers[0].exclusion_reason, "No date for retracted paper"
        )

    def test_in_rct_before_2000(self):
        """A paper in the RCT with no date should be excluded for
        that reason."""

        # set to have no date
        retracted_paper = RetractedPaper.objects.all()[0]
        retracted_paper.journaldate = "1999-01-01"
        retracted_paper.save()

        call_command("randomise", "update_exclusions")

        # check the paper in the database is now set in the RCT cohort as
        # excluded
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 1)
        # self.assertTrue(retracted_papers[0].in_rct_cohort)
        self.assertEqual(retracted_papers[0].rct_group, "x")
        self.assertEqual(retracted_papers[0].exclusion_reason, "Published before 2000")

    def test_in_rct_no_notice_date(self):
        """A paper in the RCT with no date for its retraction notice should be
        excluded for that reason, and no emails sent."""

        # set to have no date on the notice
        notice = RetractedPaper.objects.all()[0].get_notice()
        notice.journaldate = None
        notice.save()

        call_command("randomise", "update_exclusions")

        # check the paper in the database is now set in the RCT cohort as
        #  excluded
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 1)
        # TODO: look into how rct_cohort is set; could use a papers available
        # at time of random self.assertTrue(retracted_papers[0].in_rct_cohort)
        self.assertEqual(retracted_papers[0].rct_group, "x")
        self.assertEqual(
            retracted_papers[0].exclusion_reason,
            "No date for retraction notice",
        )

    def test_no_contactable(self):
        """If there are no contactable authors in the database, raise an error
        to make sure the contactable authors have been populated."""

        # set all pairs for the author to have no email addresses
        author_alias = AuthorAlias.objects.all()[0]
        author_alias.email_address = None
        author_alias.save()

        call_command("randomise", "update_exclusions")
        with self.assertRaises(EmptyResultSet):
            call_command("randomise", "set_randomisation")

    def test_error_ignore_invalid_email_address(self):
        author_alias = AuthorAlias.objects.all()[0]
        author_alias.email_address = "notavalidemail"
        author_alias.save()

        call_command("randomise", "update_exclusions")
        with self.assertRaises(EmptyResultSet):
            call_command("randomise", "set_randomisation")


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class NoContactableTestCase(TransactionTestCase):
    fixtures = ["contamination.json"]
    reset_sequences = True

    def test_in_rct_no_emails(self):
        """A paper in the RCT with no email address for its citing paper
        authors should be excluded for that reason, and no emails sent."""

        # set all pairs for the author to have no email addresses
        author_alias = AuthorAlias.objects.get(author__auid=1000)
        author_alias.email_address = None
        author_alias.save()

        call_command("randomise", "update_exclusions")

        # check the paper in the database is now set in the RCT cohort as
        # excluded
        self.assertEqual(RetractedPaper.objects.count(), 3)
        paper_no_contactable = RetractedPaper.objects.get(pmid=2000009)
        self.assertEqual(paper_no_contactable.rct_group, "x")
        self.assertEqual(
            paper_no_contactable.exclusion_reason, "No contactable authors"
        )
        # Hard code the randomisation for deterministic number of mails sent
        RetractedPaper.objects.filter(rct_group=None).update(rct_group="i")
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(
            len(
                set(
                    MailSent.objects.all().values_list(
                        "pairs__retractedpaper__pmid", flat=True
                    )
                )
            ),
            2,
        )


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class PilotTestCase(TransactionTestCase):
    fixtures = ["email_pilot_paper.json"]
    reset_sequences = True

    def test_put_in_rct_cohort_pilot(self):
        """A pilot paper should go into pilot group when put
        in the RCT and then have no emails sent for it"""

        call_command("randomise", "update_exclusions")

        # check the paper in the database is now set in the RCT cohort as pilot
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 1)
        self.assertEqual(retracted_papers[0].rct_group, "x")
        self.assertEqual(retracted_papers[0].exclusion_reason, "Pilot")

        # check no emails sent
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class RCTRandomisationTestCase(TransactionTestCase):
    fixtures = []
    reset_sequences = True

    def setUp(self):
        """Make 100 papers for testing the randomisation part of the RCT"""
        t = "1"
        # Create 100 citing authors
        for i in range(0, 100):
            t = str(i)
            a = Author(
                id=i + 1000,
                auid=t,
            )
            a.save()
            aa = AuthorAlias(
                author=a,
                email_address="e" + t + "@example.com",
                surname="Surname" + t,
                given_name="Given" + t,
            )
            aa.save()
        # Create 100 retracted papers
        for i in range(0, 100):
            t = str(i)
            rp = RetractedPaper(
                doi="doi" + t,
                issn="issn" + t,
                scopus_id="scopus" + t,
                title="Title " + t,
                journaldate="2018-01-01",
                journaldate_granularity="y",
                journaltitle="Journal of " + t,
                journal_iso="J. " + t,
                pmid=t,
            )
            rp.save()
            rn = RetractionNotice(
                doi="ndoi" + t,
                issn="nissn" + t,
                title="Retraction of " + t,
                journaldate="2018-01-01",
                journaldate_granularity="y",
                journaltitle="Journal of " + t,
                pmid="9" + t,
            )
            rn.save()
            rn.papers.add(rp)
            cp = CitingPaper(
                doi="cdoi" + t,
                issn="cissn" + t,
                scopus_id="cscopus" + t,
                title="Citation of " + t,
                prismcoverdate="2018-01-01",
                journalname="Journal of " + t,
            )
            cp.save()
            cp.paper.add(rp)
            # Add a random number of authors
            num_authors = random.randint(1000, 1100)
            authors = Author.objects.filter(id__lte=num_authors)
            cp.authors.add(*authors)

    def test_rct_randomisation(self):
        """Roughly half of papers should go into intervention and half
        into control out of 100 papers. The correct number of mails
        should then be sent. The PMIDs in those emails should match
        the intervention group."""

        call_command("randomise", "update_exclusions")
        call_command("randomise", "set_randomisation")

        # check the papers in the database is now set in the RCT cohort
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 100)
        i, c = 0, 0
        intervention_pmids = []
        for p in retracted_papers:
            self.assertIn(p.rct_group, ["i", "c"])
            self.assertIsNone(p.exclusion_reason)

            if p.rct_group == "i":
                i = i + 1
                intervention_pmids.append(p.get_notice().pmid)
            elif p.rct_group == "c":
                c = c + 1
            else:
                self.assertTrue(False)

        self.assertEqual(i + c, 100)
        self.assertTrue(30 < i < 70, i)
        self.assertTrue(30 < c < 70, c)

        strata = RetractedPaper.objects.values_list(
            "stratifying_group", flat=True
        ).distinct()
        self.assertTrue(strata)
        for level in strata:
            counter = Counter(
                RetractedPaper.objects.filter(stratifying_group=level).values_list(
                    "rct_group", flat=True
                )
            )
            self.assertTrue(abs(counter["i"] - counter["c"]) <= 1)

        call_command("send_retraction_emails", "--live-run")

        # find the notice pmids in the emails
        mail_pmids = []
        for email in mail.outbox:
            html = email.alternatives[0][0]
            pmids = re.findall(
                r"https://www.ncbi.nlm.nih.gov/pubmed/\?term=(\d+)", html
            )
            self.assertTrue(pmids)
            mail_pmids += pmids

        # check notice intervention group pmids and mail pmids are the same
        intervention_pmids = set(intervention_pmids)
        mail_pmids = set(mail_pmids)
        self.assertEqual(intervention_pmids, mail_pmids)
        self.assertTrue(len(mail_pmids) > 30)

        with self.assertRaises(AssertionError):
            call_command("randomise", "set_randomisation")


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class GenDatasetTestCase(TransactionTestCase):
    fixtures = ["contamination.json"]
    reset_sequences = True

    def test_count_unique(self):
        """
        Test if an author has a paper in the intervention and control groups
        """
        res = NamedTemporaryFile(delete=True)
        call_command(
            "randomise",
            "gen_dataset",
            "--output-file",
            res.name,
        )
        df = pandas.read_csv(res.name)
        df = df.set_index("pmid")
        self.assertTrue(df.loc[2000007].count_unique, 4)
        self.assertTrue(df.loc[2000008].count_unique, 3)
        self.assertTrue(df.loc[2000009].count_unique, 1)

    def test_contamination(self):
        """
        Test if an author has a paper in the intervention and control groups
        """
        res = NamedTemporaryFile(delete=True)
        call_command(
            "randomise",
            "gen_dataset",
            "--output-file",
            res.name,
        )
        df = pandas.read_csv(res.name)
        self.assertTrue(df.contaminated[0])
        self.assertTrue(df.contaminated[1])
        self.assertFalse(df.contaminated[2])


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class WashoutTestCase(TransactionTestCase):
    fixtures = ["contamination.json"]
    reset_sequences = True

    def test_washout(self):
        """A citing paper in the washout should not count as citing."""

        # Set the 2022-12-20 citing paper as not citing in the rct
        follow_up_date = "2022-08-01"
        CitingPaper.objects.filter(comparisondate__gte=follow_up_date).update(
            cited_in_rct=False
        )

        res1 = NamedTemporaryFile(delete=True)
        call_command(
            "randomise",
            "gen_dataset",
            "--output-file",
            res1.name,
            "--follow-up-date",
            "2022-08-01",
        )

        df1 = pandas.read_csv(res1)
        self.assertTrue((df1.citation_count == pandas.Series([1, 1, 0])).all())

        res2 = NamedTemporaryFile(delete=True)
        call_command(
            "randomise",
            "gen_dataset",
            "--output-file",
            res2.name,
            "--follow-up-date",
            "2023-01-01",
        )

        # If we change the follow-up date, that citation is excluded
        df2 = pandas.read_csv(res2)
        self.assertTrue((df2.citation_count == pandas.Series([0, 0, 0])).all())

        # But the count used in stratification stays the same
        self.assertTrue((df1.count_unique == df2.count_unique).all())


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class RemoveCiting(TransactionTestCase):
    fixtures = ["contamination.json"]
    reset_sequences = True

    def test_count_unique_remove_citing(self):
        # Set the 2022-12-20 citing paper as not citing in the rct
        follow_up_date = "2022-08-01"
        CitingPaper.objects.filter(comparisondate__gte=follow_up_date).update(
            cited_in_rct=False
        )
        res = NamedTemporaryFile(delete=True)
        call_command(
            "randomise",
            "gen_dataset",
            "--output-file",
            res.name,
        )
        df = pandas.read_csv(res.name)
        df = df.set_index("pmid")
        self.assertTrue(df.loc[2000007].count_unique, 2)
        self.assertTrue(df.loc[2000008].count_unique, 3)
        self.assertTrue(df.loc[2000009].count_unique, 1)
