from django.test import TestCase

from common import setup
from retractions.management.commands import contactable_authors
from retractions.models import Author, AuthorAlias, RetractedPaper


class CommandsTestCase(TestCase):
    def setUp(self):
        self.c = contactable_authors.Command()
        setup.setup_logger(2)

    def test_update_citing_paper_normal(self):
        retracted_paper = RetractedPaper.objects.create(
            pmid="123", scopus_id="abcd", title="Foo bar"
        )

        # Test a paper that is not an erratum.
        data = {
            "authors": [
                {
                    "ce:given-name": "Denise F.",
                    "preferred-name": {
                        "ce:given-name": "Denise F.",
                        "ce:initials": "D.F.",
                        "ce:surname": "Blake",
                        "ce:indexed-name": "Blake D.",
                    },
                    "@seq": "1",
                    "ce:initials": "D.F.",
                    "@_fa": "true",
                    "@type": "auth",
                    "ce:e-address": {
                        "$": "drsblakeinoz@bigpond.com",
                        "@type": "email",
                    },
                    "ce:surname": "Blake",
                    "@auid": "23484157000",
                    "ce:indexed-name": "Blake D.F.",
                },
                {
                    "ce:given-name": "Derelle A.",
                    "preferred-name": {
                        "ce:given-name": "Derelle A.",
                        "ce:initials": "D.A.",
                        "ce:surname": "Young",
                        "ce:indexed-name": "Young D.",
                    },
                    "@seq": "2",
                    "ce:initials": "D.A.",
                    "@_fa": "true",
                    "@type": "auth",
                    "ce:surname": "Young",
                    "@auid": "55539598300",
                    "ce:indexed-name": "Young D.A.",
                },
                {
                    "ce:given-name": "Lawrence H.",
                    "preferred-name": {
                        "ce:given-name": "Lawrence H.",
                        "ce:initials": "L.H.",
                        "ce:surname": "Brown",
                        "ce:indexed-name": "Brown L.",
                    },
                    "@seq": "3",
                    "ce:initials": "L.H.",
                    "@date-locked": "2017-03-09T15:31:16.567",
                    "@_fa": "true",
                    "@type": "auth",
                    "ce:surname": "Brown",
                    "@auid": "7404220468",
                    "ce:indexed-name": "Brown L.H.",
                },
            ]
        }

        self.c._update_retracted_paper("abcd", data)
        retracted_paper.refresh_from_db()

        # Check author objects saved correctly
        a = Author.objects.all()
        self.assertEqual(len(a), 3)
        aa = AuthorAlias.objects.all()
        self.assertEqual(len(aa), 3)
        a = AuthorAlias.objects.get(surname="Blake")
        self.assertEqual(a.author.auid, "23484157000")
        self.assertEqual(a.given_name, "Denise F.")
        self.assertEqual(a.email_address, "drsblakeinoz@bigpond.com")
