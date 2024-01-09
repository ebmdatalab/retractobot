import datetime
import logging

import requests
from django.core.management.base import BaseCommand

from common import setup
from retractions.models import MailSent


class Command(BaseCommand):
    args = ""
    help = """Retrieve tracking information from the Mailgun API.
    NB: Mailgun only retains information for 30 days, so we need to
    run this script at least that often."""  # noqa: A003

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])

        MAILGUN_API_KEY = setup.get_env_setting("RETR_MAILGUN_API_KEY")

        # Get all events available
        url = "https://api.eu.mailgun.net/v3/retracted.net/events"

        # Loop through pages of events
        while True:
            logging.info("Getting Mailgun URL: %s", url)
            resp = requests.get(url, auth=("api", MAILGUN_API_KEY))
            resp.raise_for_status()
            data = resp.json()
            items = data["items"]
            logging.info("Events from Mailgun: %d", len(items))
            if len(items) == 0:
                break

            # Loop through them
            for i in list(items):
                event = i["event"]
                try:
                    message_id = i["message"]["headers"]["message-id"]
                except KeyError:
                    logging.warning(f"{i['event']} has no message id, skipped")
                    continue
                when = datetime.datetime.utcfromtimestamp(i["timestamp"])
                url = None
                if event == "clicked":
                    if "url" not in i:
                        logging.warning("No URL in clicked event")
                        continue
                    url = i["url"]

                try:
                    mail_sent = MailSent.objects.get(message_id=message_id)
                except MailSent.DoesNotExist:
                    logging.warning(
                        "Message not found in our sent database: %s %s %s %s",
                        message_id,
                        event,
                        when,
                        url,
                    )
                    continue
                logging.info(
                    "Processing event: %s %s %s %s",
                    message_id,
                    event,
                    when,
                    url,
                )

                if event == "accepted":
                    # take earliest accepted event
                    if not mail_sent.accepted or when < mail_sent.accepted:
                        mail_sent.accepted = when
                elif event == "delivered":
                    # take earliest delivered event
                    if not mail_sent.delivered or when < mail_sent.delivered:
                        mail_sent.delivered = when
                elif event == "opened":
                    # take earliest delivered event
                    if not mail_sent.opened or when < mail_sent.opened:
                        mail_sent.opened = when
                elif event == "unsubscribed":
                    # take earliest unsubscribed event
                    if not mail_sent.unsubscribed or when < mail_sent.unsubscribed:
                        mail_sent.unsubscribed = when
                elif event == "clicked":
                    if "didntknowany" in url:
                        # take latest click event
                        if (
                            not mail_sent.clicked_didntknowany
                            or when > mail_sent.clicked_didntknowany
                        ):
                            mail_sent.clicked_didntknowany = when
                    elif "alreadyknewall" in url:
                        # take latest click event
                        if (
                            not mail_sent.clicked_alreadyknewall
                            or when > mail_sent.clicked_alreadyknewall
                        ):
                            mail_sent.clicked_alreadyknewall = when
                    elif "alreadyknewsome" in url:
                        # take latest click event
                        if (
                            not mail_sent.clicked_alreadyknewsome
                            or when > mail_sent.clicked_alreadyknewsome
                        ):
                            mail_sent.clicked_alreadyknewsome = when
                    else:
                        # take latest click event
                        if (
                            not mail_sent.clicked_other
                            or when > mail_sent.clicked_other
                        ):
                            mail_sent.clicked_other = when
                elif event == "failed":
                    continue
                else:
                    logging.warning("Unknown event '%s'" % event)

                mail_sent.save()

            paging = data["paging"]
            if "next" not in paging:
                break
            url = paging["next"]
