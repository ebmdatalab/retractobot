import unittest.mock

import anymail.backends.test
import anymail.exceptions
import django.db
from django.core import mail
from django.core.management import call_command
from django.test import TransactionTestCase
from django.test.utils import override_settings

from retractions.models import (
    Author,
    AuthorAlias,
    CitationRetractionPair,
    CitingPaper,
    MailSent,
    RetractedPaper,
)


# NOTE: unlike analysis tests, these test files should have comparisondate
# and rct_group set


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class CitedAfterTestCase(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    reset_sequences = True

    def test_dry_run_email(self):
        "There should be no emails sent without the live-run switch"
        call_command("send_retraction_emails")
        self.assertEqual(len(mail.outbox), 0)

    def test_live_run_email_with_standard_citation(self):
        "There should be an email sent with the live-run switch"
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['"Victor S. Tofu" <tofu@beans.com>'])
        self.assertEqual(email.track_clicks, True)
        self.assertEqual(
            email.from_email,
            '"The RetractoBot Team, University of Oxford" <ben@retracted.net>',
        )
        self.assertEqual(email.recentest_citing_paper_id, "500000")
        html = email.alternatives[0][0]
        # Check copy is as in Protocol Appendix 2
        self.assertIn(
            '"Empagliflozin limits Tofu eating" (Frontiers in Tofu, 2017)',
            html,
        )
        self.assertIn("response/alreadyknewall", html)
        self.assertNotIn("response/alreadyknewsome", html)
        self.assertIn(
            'which <a href="https://www.ncbi.nlm.nih.gov/pubmed/?term=4000">'
            "was retracted in 2001</a>",
            html,
        )


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class CitedTwoAliases(TransactionTestCase):
    fixtures = ["email_two_aliases.json"]
    reset_sequences = True

    def test_live_run_email_with_standard_citation(self):
        """Copy of an email about two citing papers from the same author"""

        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(
            email.to,
            [
                '"Victor S. Tofu" <tofu@beans.com>',
                "Victor Tofu <tofu@prior.edu>",
            ],
        )


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class TwoRetractedPapersTestCase(TransactionTestCase):
    fixtures = ["email_two_retracted_papers.json"]
    reset_sequences = True

    def test_live_run_email_with_standard_citation(self):
        "There should be an email sent with the live-run switch"
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['"Victor S. Tofu" <tofu@beans.com>'])
        self.assertEqual(email.track_clicks, True)
        self.assertEqual(
            email.from_email,
            '"The RetractoBot Team, University of Oxford" <ben@retracted.net>',
        )
        self.assertEqual(email.recentest_citing_paper_id, "500010")
        html = email.alternatives[0][0]
        # Check copy is as in Protocol Appendix 2
        self.assertIn(
            '"Empagliflozin limits Tofu eating" (Frontiers in Tofu, 2017)',
            html,
        )
        self.assertIn(
            '"Empagliflozin enhances Tofu eating" (Frontiers in Tofu, 2018)',
            html,
        )
        self.assertIn("response/alreadyknewsome", html)
        self.assertIn(
            'which <a href="https://www.ncbi.nlm.nih.gov/pubmed/?term=4000">'
            "was retracted in 2000</a>",
            html,
        )


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class NoCitationTestCase(TransactionTestCase):
    fixtures = ["email_no_citing.json"]
    reset_sequences = True

    def test_live_run_no_email_with_no_citation(self):
        """There should be no emails sent if a paper with no
        citing papers tries to have emails sent for it when
        it is not in the RCT cohort."""

        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class MultipleNoticesTestCase(TransactionTestCase):
    fixtures = ["email_two_notices.json"]
    reset_sequences = True

    def test_live_run_email_with_standard_citation(self):
        "With two notices for one paper, should use date from earliest PMID"

        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        html = email.alternatives[0][0]

        self.assertIn(
            'which <a href="https://www.ncbi.nlm.nih.gov/pubmed/?term=3900001">'
            "was retracted in 2000</a>",
            html,
        )


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class MailSendErrors(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    reset_sequences = True

    def test_error_mailgun_api(self):
        """Sending a mail when the MailGun API is returning errors should
        fail, but try again next time"""

        # Try while the API is failing
        with unittest.mock.patch.object(
            anymail.backends.test.EmailBackend,
            "post_to_esp",
            # exception documented here:
            # https://anymail.readthedocs.io/en/stable/sending/exceptions/
            side_effect=anymail.exceptions.AnymailInvalidAddress(),
        ):
            call_command("send_retraction_emails", "--live-run")

        self.assertEqual(len(mail.outbox), 0)

        # Try again while it is working
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)

    def test_database_error(self):
        """Sending a mail when the database throws an exception
        succeeds, ending the script, and will try again next time"""

        # Try while the database is failing
        with unittest.mock.patch.object(
            MailSent, "save", side_effect=django.db.Error()
        ):
            self.assertRaises(
                django.db.utils.Error,
                call_command,
                "send_retraction_emails",
                "--live-run",
            )
        # Note that in this case the mail has been sent, we
        # just didn't record in the database that it was :(
        self.assertEqual(len(mail.outbox), 1)

        # Try again while the database is working again
        call_command("send_retraction_emails", "--live-run")
        # The mail gets sent (again)
        self.assertEqual(len(mail.outbox), 2)

        # Third time lucky
        call_command("send_retraction_emails", "--live-run")
        # No more mails
        self.assertEqual(len(mail.outbox), 2)


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class NewEmailsAndAuthorsAppear(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    cmd = "retractions.management.commands.send_retraction_emails"
    reset_sequences = True

    def test_new_email_address_nothing_sent(self):
        """When sending a second time with a new email address for an
        existing author, nothing new is sent."""

        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)

        # set to have an extra email
        AuthorAlias.objects.create(
            author=Author.objects.get(pk=1000),
            email_address="beans@tofu.com",
            surname="Tofu",
            given_name="Victor",
        )

        # nothing new is sent
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)

    def test_new_author_mail_sent(self):
        """When sending a second time with a new email address for a
        new author, a new email is sent."""

        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['"Victor S. Tofu" <tofu@beans.com>'])

        # set to have an extra author
        a = Author.objects.create(
            pk=1001,
            auid="1001",
        )
        a.save()
        a.citing_papers.set([CitingPaper.objects.first()])
        a.pairs.add(CitationRetractionPair.objects.first())
        a.save()
        AuthorAlias.objects.create(
            author=a,
            email_address="beans@tofu.com",
            surname="Soya",
            given_name="Victoria",
        )

        # a new email to the new author is sent
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 2)
        email = mail.outbox[1]
        self.assertEqual(email.to, ["Victoria Soya <beans@tofu.com>"])


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class NewEmailsAndAuthorsAppearRCTControl(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    cmd = "retractions.management.commands.send_retraction_emails"
    reset_sequences = True

    def test_new_email_address_control(self):
        """When attempting to send a second time with a new email address for
        an existing author for a paper in the RCT control group, still nothing
        is sent."""

        # check the paper in the database is now set in the RCT cohort
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 1)
        self.assertIsNone(retracted_papers[0].exclusion_reason)

        # force into the control group for this test
        retracted_papers[0].rct_group = "c"
        retracted_papers[0].save()

        # check no emails are sent, as in control group
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 0)

        # set to have an extra author
        a = Author.objects.create(
            pk=1001,
            auid="1001",
        )
        a.save()
        a.citing_papers.set([CitingPaper.objects.first()])
        a.pairs.add(CitationRetractionPair.objects.first())
        a.save()
        AuthorAlias.objects.create(
            author=a,
            email_address="beans@tofu.com",
            surname="Soya",
            given_name="Victoria",
        )

        # nothing new is sent
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class NewEmailsAndAuthorsAppearRCTIntervention(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    cmd = "retractions.management.commands.send_retraction_emails"
    reset_sequences = True

    def test_new_email_address_intervention(self):
        """When attempting to send a second time with a new email address for
        an existing author for a paper in the RCT intervention group, a
        second mail is sent."""

        # check the paper in the database is now set in the RCT cohort
        retracted_papers = RetractedPaper.objects.all()
        self.assertEqual(len(retracted_papers), 1)
        self.assertIsNone(retracted_papers[0].exclusion_reason)

        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['"Victor S. Tofu" <tofu@beans.com>'])

        # set to have an extra author
        a = Author.objects.create(
            pk=1001,
            auid="1001",
        )
        a.save()
        a.citing_papers.set([CitingPaper.objects.first()])
        a.pairs.add(CitationRetractionPair.objects.first())
        a.save()
        AuthorAlias.objects.create(
            author=a,
            email_address="beans@tofu.com",
            surname="Soya",
            given_name="Victoria",
        )

        # a new mail is sent
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 2)
        email = mail.outbox[1]
        self.assertEqual(email.to, ["Victoria Soya <beans@tofu.com>"])
