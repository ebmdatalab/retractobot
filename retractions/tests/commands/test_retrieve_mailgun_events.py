import datetime
import unittest.mock

from django.core import mail
from django.core.management import call_command
from django.test import TransactionTestCase
from django.test.utils import override_settings

from retractions.models import MailSent


class FakeResponse:
    """Pretend to be the return object from requests.get, with
    only capability of returning JSON. For use by fake_get below.
    """

    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d

    def raise_for_status(self):
        pass


def fake_get(message_id, test_case):
    """Capture the message_id in a closure to make a function that mocks
    requests.get to pretends to return messages with that ID from the MailGun
    API.

    test_case can be:

    "default" - one message which is opened, and 'already knew' clicked
    "multipage" - two pages of results with a click on each page
    """

    assert test_case in ["default", "multipage"]

    def _inner_fake_get(url, auth):
        """Overrides requests.get to pretends to be the MailGun API in a limited
        way"""
        base_url = "https://api.eu.mailgun.net/v3/retracted.net/events"
        second_url = base_url + "/2"
        third_url = base_url + "/3"
        last_url = second_url
        if test_case == "multipage":
            last_url = third_url

        message = {
            "headers": {
                "to": "Victor S. Tofu <tofu@beans.com>",
                "message-id": message_id,
                "from": '"Ben Goldacre, University of Oxford" <team@retracted.net>',
                "subject": """RetractoBot: You cited a retracted paper in your
                              Frontiers in Tofu paper published in 2018""",
            },
        }

        if url == base_url:
            response = {
                "items": [
                    {
                        "timestamp": 1530000000.19166,
                        "recipient": "tofu@beans.com",
                        "message": message,
                        "event": "accepted",
                    },
                    {
                        "timestamp": 1530277144.19166,
                        "recipient": "tofu@beans.com",
                        "message": message,
                        "event": "delivered",
                    },
                    {
                        "timestamp": 1530345664.19166,
                        "recipient": "tofu@beans.com",
                        "message": message,
                        "event": "opened",
                    },
                    {
                        "timestamp": 1530345694.19166,
                        "recipient": "tofu@beans.com",
                        "message": message,
                        "event": "clicked",
                        "url": "//retracted.net/response/alreadyknewall",
                    },
                ],
                "paging": {
                    "previous": base_url,
                    "first": base_url,
                    "last": last_url,
                    "next": second_url,
                },
            }
            return FakeResponse(response)

        if test_case == "multipage" and url == second_url:
            response = {
                "items": [
                    {
                        "timestamp": 1530345674.19166,
                        "recipient": "tofu@beans.com",
                        "message": message,
                        "event": "opened",
                    },
                    {
                        "timestamp": 1530345684.19166,
                        "recipient": "tofu@beans.com",
                        "message": message,
                        "event": "clicked",
                        "url": "//retracted.net/response/alreadyknewall",
                    },
                ],
                "paging": {
                    "previous": base_url,
                    "first": base_url,
                    "last": last_url,
                    "next": last_url,
                },
            }
            return FakeResponse(response)

        # Last page returns nothing to show end of events
        assert (test_case == "default" and url == second_url) or (
            test_case == "multipage" and url == third_url
        )
        prev_url = base_url
        if test_case == "multipage":
            prev_url = second_url
        return FakeResponse(
            {
                "items": [],
                "paging": {
                    "previous": prev_url,
                    "first": base_url,
                    "last": last_url,
                    "next": last_url,
                },
            }
        )

    return _inner_fake_get


@override_settings(EMAIL_BACKEND="anymail.backends.test.EmailBackend")
class CommandsTestCase(TransactionTestCase):
    fixtures = ["email_cited_after_retraction.json"]
    reset_sequences = True

    def setUp(self):
        call_command("send_retraction_emails", "--live-run")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.message_id = email.anymail_status.message_id

    def test_gets_open_and_click_event(self):
        """If mail is opened and 'already knew all' clicked, returns
        right date stamps."""

        with unittest.mock.patch("requests.get", fake_get(self.message_id, "default")):
            call_command("retrieve_mailgun_events")

        mails_sent = MailSent.objects.all()
        self.assertEqual(len(mails_sent), 1)
        mail_sent = mails_sent[0]
        # Check same as unix time 1530345664.19166 as put in messages above
        self.assertEqual(
            mail_sent.opened, datetime.datetime(2018, 6, 30, 8, 1, 4, 191660)
        )
        self.assertIsNone(mail_sent.clicked_didntknowany)
        self.assertIsNone(mail_sent.clicked_alreadyknewsome)
        # Check same as unix time 1530345694.19166 as put in messages above
        self.assertEqual(
            mail_sent.clicked_alreadyknewall,
            datetime.datetime(2018, 6, 30, 8, 1, 34, 191660),
        )

    def test_gets_events_on_multiple_pages(self):
        """If mail is opened and 'already knew' clicked twice,
        with events on different pages returns earlier stamp for opening
        and later stamp for clicking."""

        with unittest.mock.patch(
            "requests.get", fake_get(self.message_id, "multipage")
        ):
            call_command("retrieve_mailgun_events")

        mails_sent = MailSent.objects.all()
        self.assertEqual(len(mails_sent), 1)
        mail_sent = mails_sent[0]
        # Check same as unix time 1530345664.19166 as put in messages above
        self.assertEqual(
            mail_sent.opened, datetime.datetime(2018, 6, 30, 8, 1, 4, 191660)
        )
        self.assertIsNone(mail_sent.clicked_didntknowany)
        # Check same as unix time 1530345694.19166 as put in messages above
        self.assertEqual(
            mail_sent.clicked_alreadyknewall,
            datetime.datetime(2018, 6, 30, 8, 1, 34, 191660),
        )
