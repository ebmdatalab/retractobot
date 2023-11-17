import email.utils
import logging
import mailbox

import anymail.exceptions
import anymail.utils
import django.core.exceptions
import django.db
import html2text
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand

from common import setup
from retractions.models import Author, CitingPaper, MailSent


text_maker = html2text.HTML2Text()
text_maker.links_each_paragraph = True


class OurEmail(EmailMultiAlternatives):
    def __init__(self, *args, **kwargs):
        self.recentest_citing_paper_id = None
        self.papers = None
        super().__init__(*args, **kwargs)


class Command(BaseCommand):
    """
    Regular task.
    """

    args = ""
    help = """For all new citations of retracted papers, mail the
        authors, using anymail. Can put papers in the RCT,
        in which case they will be excluded, or randomly
        put in the intervention or control group and mailed
        appropriately.
        """  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument(
            "--live-run",
            action="store_true",
            dest="live-run",
            help="Actually send emails, rather than (default) do a dry run",
        )
        parser.add_argument(
            "--test-email",
            action="store",
            dest="test-email",
            help="Sends outgoing emails to this email address",
            default=None,
        )
        parser.add_argument(
            "--limit",
            action="store",
            dest="limit",
            help="Maximum number of authors to send to",
            default=None,
        )

    def handle(self, *args, **options):
        setup.setup_logger(options["verbosity"])
        if options["live-run"]:
            self.mb = mailbox.mbox("live-all-sent-mails.mbox")
        else:
            self.mb = mailbox.mbox("debug-last-sent-mails.mbox")
            self.mb.clear()
            self.mb.flush()

        if options["live-run"]:
            self.live_run = True
            logging.info("Live run - sending emails for real")
        else:
            self.live_run = False
            logging.info("Dry run - not actually sending emails")

        self.test_email = options["test-email"]

        # Filter for the authors who we would send mail to
        authors = (
            Author.objects.filter(pairs__retractedpaper__rct_group="i")
            .filter(mail_sent__isnull=True)
            .extra(select={"auid_float": "auid::float"})
            .order_by("auid_float")
        ).distinct()
        if options["limit"]:
            authors = authors[: int(options["limit"])]
        logging.info("Total authors to send %d", len(authors))
        # Could also add info about the pairs
        for author in authors:
            logging.info(
                "Author: AUID %s",
                author.auid,
            )

            self._send_for_author(author)

    def _send_for_author(self, author):
        """
        Create and send mails for the author.
        """

        intervention_pairs = author.pairs.filter(retractedpaper__rct_group="i")
        mail_to_send = self._get_mail_to_send(author, intervention_pairs)
        # Check we have emails to send
        if not mail_to_send:
            logging.info("  Sending no mails as none due to send")
            return

        # Send the mails
        self._actually_send_mails(author, intervention_pairs, mail_to_send)

    def _get_mail_to_send(self, author, intervention_pairs):
        """
        Constructs the emails to send to each author of the citing papers
        of a retracted paper. Only includes mails which haven't been
        already sent.
        """

        if intervention_pairs.count() == 0:
            logging.info("  Skipping emailing author not in any intervention pairs")
            return
        # have we already sent to this author?
        to_emails = []
        already_sent = False
        for mail_sent in author.mail_sent.all():
            assert set(mail_sent.pairs.all()) == set(intervention_pairs)
            if mail_sent.author == author:
                already_sent = True
        if already_sent:
            logging.info(
                f"  Skipping emailing author: {','.join(to_emails)} as already sent",
            )
            return
        # Find unique list of to email addresses we have for that author
        for author_alias in author.author_aliases.all():
            if author_alias.email_address:
                # see if the mail is valid according to anymail
                valid = True
                try:
                    anymail.utils.parse_single_address(author_alias.email_address)
                except anymail.exceptions.AnymailInvalidAddress:
                    logging.info(
                        "  Ignoring invalid email %s",
                        author_alias.email_address,
                    )
                    valid = False

                if valid:
                    if self.test_email:
                        logging.warning(
                            "  Changed author email %s to %s for debugging",
                            author_alias.email_address,
                            self.test_email,
                        )
                        to_email = email.utils.formataddr(
                            (author_alias.full_name(), self.test_email)
                        )
                    else:
                        to_email = email.utils.formataddr(
                            (
                                author_alias.full_name(),
                                author_alias.email_address,
                            )
                        )
                    to_emails.append(to_email)

        # If no emails to send to, skip this author
        if len(to_emails) == 0:
            logging.info("  Skipping emailing author as no email address present")
            return

        pairs_repr = "|".join(
            [
                f"{p.retractedpaper.pmid}:{p.citingpaper.scopus_id}"
                for p in intervention_pairs
            ]
        )
        logging.info(
            f"  Preparing to email author: {','.join(to_emails)} Citing papers: {pairs_repr}"
        )
        mail_to_send = self._generate_mail(intervention_pairs, author, to_emails)
        return mail_to_send

    def _generate_mail(self, pairs, author, to_emails):
        pairs = pairs.order_by("-citingpaper__comparisondate")
        recentest_citing_paper = pairs.first().citingpaper
        subject, body = self._get_body_and_subject(
            pairs, recentest_citing_paper, author
        )
        body_plaintext = text_maker.handle(body).strip()
        msg = OurEmail(
            subject=subject,
            body=body_plaintext,
            from_email='"The RetractoBot Team, University of Oxford" <ben@retracted.net>',
            to=to_emails,
        )
        msg.attach_alternative(body, "text/html")
        msg.track_clicks = True
        msg.recentest_citing_paper_id = recentest_citing_paper.scopus_id
        msg.pairs = pairs
        return msg

    # TODO: check that comparison date is not null
    def _get_body_and_subject(self, pairs, recentest_citing_paper, author):
        subject = (
            "RetractoBot: You cited a retracted paper "
            f"in your {recentest_citing_paper.journalname} paper published in {recentest_citing_paper.comparisondate.year}"
        )

        aliases = author.author_aliases.all()
        assert len(aliases) > 0

        # Introduction.
        body = "<p>Dear %s,</p>" % aliases[0].full_name()
        body += "<p>"
        body += """We're writing to let you know that the following paper(s) cited a
                paper which has been retracted."""
        body += "</p>"
        body += "<table border='1' cellpadding='0' cellspacing='0' width='80%' style='border-collapse: collapse;'>"
        body += "<tr>"
        body += "<th style='padding: 8px; text-align: left;'>Citing Paper</th>"
        body += "<th style='padding: 8px; text-align: left;'>Retracted Citation</th>"
        body += "</tr>"
        # Use order_by and distinct to preserve order
        citing_papers = list(
            pairs.order_by("-citingpaper__scopus_id")
            .values_list("citingpaper__scopus_id", flat=True)
            .distinct()
        )
        # Just need count so we don't need to preserve order (can use a set)
        total_papers = len(set(pairs.values_list("retractedpaper__pmid", flat=True)))
        for scopus_id in citing_papers:
            citing_paper = CitingPaper.objects.get(scopus_id=scopus_id)
            body += "<tr>"
            body += f'<td style="padding: 8px;">"{citing_paper.title}" ({citing_paper.journalname}, {citing_paper.comparisondate.year})</td>'
            body += "<td style='padding: 8px;'>"
            body += "<ul>"
            for pair in pairs.filter(
                citingpaper__scopus_id=citing_paper.scopus_id
            ).order_by("-retractedpaper__comparisondate"):
                retracted_paper = pair.retractedpaper
                retraction_notice = retracted_paper.get_notice()
                body += f'<li>"{retracted_paper.title}" ({retracted_paper.journal_iso}, {retracted_paper.comparisondate.year}), which <a href="{retraction_notice.url()}">was retracted in {retraction_notice.comparisondate.year}</a>.</li>'
            body += "</ul>"
            body += "</td>"
            body += "</tr>"
        body += "</table>"
        # Collect information about whether the mail was useful.
        body += """<p>We run the <a href="https://retracted.net/">RetractoBot</a>
            research project, which aims to reduce the propagation of flawed
            research in the biomedical literature by reducing citations of
            retracted research papers.</p>

            <p><strong>Was this information useful?</strong><br/>
            Please click below to let us know whether you knew about the
            retraction.

            <br>Your voluntary click, below, is taken as consent for your anonymous
            response to be included in our analysis. If you have any other
            comments, please reply to this email; your voluntary reply is taken
            as consent for your comments to be used anonymously in our
            qualitative analysis of the project unless otherwise noted."""

        body += """</p>"""
        if total_papers > 1:
            body += """<p><a href="https://retracted.net/response/alreadyknewall">I
                <strong>already knew ALL</strong> of these papers were
                retracted, thanks!</a><br/>"""
            body += """<b>or</b><br>
                <a href="https://retracted.net/response/alreadyknewsome">I
                <strong>already knew SOME</strong> of these papers were
                retracted, thanks!</a><br/>"""
            body += """<b>or</b><br>
                <a href="https://retracted.net/response/didntknowany">I
                <strong>didn't know ANY</strong> of these papers were
                retracted, thanks!</a>"""

        else:
            body += """<p><a href="https://retracted.net/response/alreadyknewall">I
                <strong>already knew this</strong> paper was
                retracted, thanks!</a><br/>"""
            body += """<b>or</b><br>
                <a href="https://retracted.net/response/didntknowany">I
                <strong>didn't know this</strong> paper was retracted,
                thanks!</a>"""
        # Signoff.
        body += """<p>Many thanks for your time.</p>"""
        body += """<p>Yours sincerely,<br>The RetractoBot Team
                <br>(Dr Nicholas DeVito, Christine Cunningham, Seb Bacon,
                Prof Ben Goldacre)</p>"""

        body += """<p><small><a href="https://www.bennett.ox.ac.uk/">
            The Bennett Institute for Applied Data Science</a>,
            <br>Nuffield Department of Primary Care Health Sciences,
                University of Oxford
            <br>Radcliffe Observatory Quarter, Woodstock Road, Oxford,
                OX2 6GG</small></p>"""

        body += """<hr>"""

        body += """<p><small>In accordance with the European Union General Data
        Protection Regulation 2016 we would like to inform you of the following
        information. We are using publicly accessible bibliographic information
        from the PubMed and Scopus databases. We are processing only your name
        and email address associated with your Scopus Author ID, which we
        obtained from Scopus only to send you this message. <em>If you would
        like to stop receiving emails from RetractoBot at this email address,
        choose the 'unsubscribe' link below. If you would like to correct your
        data on PubMed or Scopus, please contact those organisations
        directly.</em></small></p>"""

        return (subject, body)

    def _actually_send_mails(self, author, pairs, mail_to_send):
        """
        Actually send emails, storing via MailSent objects in the
        database that have done so.
        """
        try:
            # Double check this author hasn't already been mailed
            # Each author should have only one set of pairs
            assert MailSent.objects.filter(author=author).count() == 0

            # Write message to debug mailbox file
            self.mb.add(mail_to_send.message())
            self.mb.flush()

            # Don't do anything if a dry run
            if not self.live_run:
                logging.warning("  Dry run, not *actually* sent")
                return

            with django.db.transaction.atomic():
                # Send using Django's anymail (which for production
                # setups will go via MailGun)
                ret = mail_to_send.send()
                # For any errors we should get an exception, so
                # one mail should always be sent.
                assert ret == 1

                # Record it was sent in the database
                (mail_sent, created) = MailSent.objects.get_or_create(author=author)
                assert created
                mail_sent.message_id = (
                    str(mail_to_send.anymail_status.message_id)
                    .replace("<", "")
                    .replace(">", "")
                )
                mail_sent.to = ",".join(mail_to_send.to)
                mail_sent.recentest_citing_paper_id = str(
                    mail_to_send.recentest_citing_paper_id
                )
                mail_sent.pairs.set(pairs)
                mail_sent.save()
                logging.info(
                    "  Mail sent via anymail message id %s",
                    mail_to_send.anymail_status.message_id,
                )
        except anymail.exceptions.AnymailError as e:
            logging.exception("  Error trying to send email: %s", str(e))
        except django.db.utils.Error as e:
            logging.exception("  Database error while mailing: %s", str(e))
            raise
