import datetime
import json
import os
import re

import lxml.etree
import vcr
from django.test import TestCase
from vcr.filters import decode_response

import retractions.pubmed as pubmed
from common import setup
from retractions.management.commands import get_missing_citation_metadata
from retractions.models import Author, AuthorAlias, CitingPaper, RetractedPaper


def scrub_string(response):
    response["headers"]["Date"] = []
    response["headers"]["Set-Cookie"] = []
    response["headers"]["CF-Cache-Status"] = []
    response["headers"]["CF-RAY"] = []
    response["headers"]["Vary"] = []
    to_remove = []
    # We cannot update a dict while iterating, so do in two steps
    for key in response["headers"]:
        if key.startswith("X") or key.startswith("NCBI"):
            to_remove.append(key)
    for key in to_remove:
        del response["headers"][key]

    # Remove unnecessary author info
    try:
        json.loads(response["body"]["string"].decode("utf-8"))
        return scrub_json(response)
    except json.JSONDecodeError:
        # Data is not json (probably pubmed xml)
        pass
    try:
        lxml.etree.fromstring(response["body"]["string"].decode("utf-8"))
        return scrub_xml(response)
    except lxml.etree.ParserError:
        pass
    return response


def scrub_json(response):
    data = json.loads(response["body"]["string"].decode("utf-8"))
    if "abstracts-retrieval-response" in data.keys():
        data["abstracts-retrieval-response"]["coredata"]["dc:creator"] = {}
        data["abstracts-retrieval-response"]["authors"] = {}
        data["abstracts-retrieval-response"]["affiliation"] = []

        author_count = 0
        for word in str(
            data["abstracts-retrieval-response"]["item"]["bibrecord"]["head"][
                "author-group"
            ]
        ).split():
            if word == "'@auid':":
                author_count += 1

        data["abstracts-retrieval-response"]["item"]["bibrecord"] = {
            "head": {"author-group": [{"@auid": x} for x in range(author_count)]}
        }

        response["body"]["string"] = json.dumps(data).encode("utf-8")
    return response


def scrub_xml(response):
    tree = lxml.etree.fromstring(response["body"]["string"].decode("utf-8"))
    for index, author in enumerate(tree.find(".//AuthorList")):
        author[0].text = f"Last Name {index}"
        author[1].text = f"First Name {index}"
        author[2].text = f"Initials {index}"
        if len(author) == 4:
            author[3][0].text = f"Affiliation {index}"
    response["body"]["string"] = lxml.etree.tostring(
        tree, doctype=tree.getroottree().docinfo.doctype
    )
    return response


class CommandsTestCase(TestCase):
    def setUp(self):
        self.c = get_missing_citation_metadata.Command()
        setup.setup_logger(2)

    def test_check_cassettes(self):
        """
        Check there are no environment vars in the test file
        This is to ensure there are no secret keys
        """
        keys = set(dict(setup.environ).keys())
        vals = set(dict(setup.environ).values())
        for test_file in [
            "fixtures/vcr_cassettes/citation_one.yaml",
            "fixtures/vcr_cassettes/citation_two.yaml",
        ]:
            with vcr.use_cassette(test_file) as cass:
                for res in cass.responses:
                    decoded = decode_response(res)
                    self.assertEqual(
                        len(set(decoded["headers"].keys()).intersection(keys)),
                        0,
                    )
                    self.assertEqual(
                        len(
                            set(sum(decoded["headers"].values(), [])).intersection(vals)
                        ),
                        0,
                    )
                    body = decoded["body"]["string"].decode("utf-8")
                    self.assertFalse(
                        any(key in re.findall('"pubmed"', body) for key in keys)
                    )
                    self.assertFalse(
                        any(val in re.findall('"pubmed"', body) for val in vals)
                    )

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/citation_one.yaml",
        allow_playback_repeats=True,
        filter_headers=["X-ELS-APIKey", "X-ELS-Insttoken"],
        before_record_response=scrub_string,
    )
    def test_update_citation_one(self):
        scopus_id = "38149032931"
        retracted_paper = RetractedPaper.objects.create(pmid="123", title="Foo bar")
        citing_paper = CitingPaper.objects.create(scopus_id=scopus_id)
        citing_paper.paper.add(retracted_paper)
        self.c.handle(verbosity=0, scopus_only=False, pubmed_only=False)
        citing_paper.refresh_from_db()
        self.assertNotEqual(citing_paper.journaldate, None)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/citation_two.yaml",
        allow_playback_repeats=True,
        filter_headers=["X-ELS-APIKey", "X-ELS-Insttoken"],
        before_record_response=scrub_string,
    )
    def test_prefer_pubmed_pmid(self):
        scopus_id = "85050606598"
        citing_paper = CitingPaper.objects.create(scopus_id=scopus_id)
        # First, query scopus
        self.c.handle(verbosity=0, scopus_only=True, pubmed_only=False)
        citing_paper.refresh_from_db()
        self.assertEqual(citing_paper.pmid, "29913552")
        # Change the pmid and ensure pubmed overwrites
        citing_paper.pmid = "100000000000"
        citing_paper.save()
        self.c.handle(verbosity=0, scopus_only=False, pubmed_only=True)
        citing_paper.refresh_from_db()
        self.assertEqual(citing_paper.pmid, "29913552")
        # Change the pmid and ensure scopus does not overwrite
        citing_paper.pmid = "10"
        citing_paper.save()
        self.c.handle(verbosity=0, scopus_only=True, pubmed_only=False)
        citing_paper.refresh_from_db()
        self.assertEqual(citing_paper.pmid, "10")

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/citation_two.yaml",
        allow_playback_repeats=True,
        filter_headers=["X-ELS-APIKey", "X-ELS-Insttoken"],
        before_record_response=scrub_string,
    )
    def test_update_citation_two(self):
        scopus_id = "85050606598"
        retracted_paper = RetractedPaper.objects.create(pmid="123", title="Foo bar")
        citing_paper = CitingPaper.objects.create(scopus_id=scopus_id)
        citing_paper.paper.add(retracted_paper)
        self.c.handle(verbosity=0, scopus_only=False, pubmed_only=False)
        citing_paper.refresh_from_db()
        self.assertEqual(citing_paper.journaldate, datetime.date(2018, 7, 28))
        self.assertEqual(citing_paper.issn, "17388872 10177825")
        self.assertEqual(citing_paper.pmid, "29913552")

    def test_update_citing_paper_normal(self):
        retracted_paper = RetractedPaper.objects.create(pmid="123", title="Foo bar")
        scopus_id = "84896692651"
        r = CitingPaper.objects.create(scopus_id=scopus_id)
        r.paper.add(retracted_paper)

        # Test a paper that is not an erratum.
        title = "Bar foo"
        pmid = "24125653"
        doi = "10.1089/ten.tea.2013.0193"
        issn = "1937335X"
        d = "2014-03-01"
        data = {
            "dc:title": title,
            "pubmed-id": pmid,
            "prism:doi": doi + "1",
            "prism:issn": issn,
            "prism:coverDate": d,
            "eid": "2-s2.0-84896692651",
            "authors": [
                {
                    "@auid": "7406655307",
                    "@seq": "3",
                    "ce:initials": "S.M.",
                    "ce:indexed-name": "Smith S.M.",
                    "ce:surname": "Smith",
                    "preferred-name": {
                        "ce:initials": "S.M.",
                        "ce:indexed-name": "Smith S.",
                        "ce:surname": "Smith",
                        "ce:given-name": "S. M.",
                    },
                    "ce:e-address": {
                        "@type": "email",
                        "$": "email@edu",
                    },
                },
                {
                    "@auid": "57191404525",
                    "@seq": "4",
                    "ce:initials": "P.V.",
                    "ce:indexed-name": "Lawford P.V.",
                    "ce:surname": "Lawford",
                    "preferred-name": {
                        "ce:initials": "P.V.",
                        "ce:indexed-name": "Lawford P.",
                        "ce:surname": "Lawford",
                        "ce:given-name": "P. V.",
                    },
                    "ce:e-address": {
                        "@type": "email",
                        "$": "email2@edu",
                    },
                },
            ],
        }
        self.c._update_citing_paper(scopus_id, data)
        r.refresh_from_db()
        self.assertEqual(r.title, title)
        self.assertEqual(r.pmid, pmid)
        self.assertEqual(r.doi, doi + "1")
        self.assertEqual(r.issn, issn)
        self.assertEqual(r.prismcoverdate, datetime.date(2014, 3, 1))
        self.assertEqual(r.issn, issn)

        # Check author objects saved correctly
        a = Author.objects.all()
        self.assertEqual(len(a), 2)
        aa = AuthorAlias.objects.all()
        self.assertEqual(len(aa), 2)
        a = AuthorAlias.objects.get(surname="Lawford")
        self.assertEqual(a.author.auid, "57191404525")
        self.assertEqual(a.given_name, "P. V.")
        self.assertEqual(a.email_address, "email2@edu")

    def test_get_paper_info_from_pubmed_xml(self):
        input_dir = os.path.dirname(__file__)
        fname = os.path.join(input_dir, "../fixtures/pubmed_citing_paper.xml")
        with open(fname) as myfile:
            xml_str = myfile.read()
            r = pubmed.get_paper_info_from_pubmed_xml(xml_str)
            self.assertEqual(r["doi"], "10.7150/thno.54822")
            self.assertEqual(r["issn"], "1838-7640")
            self.assertEqual(r["journal_iso"], "Theranostics")
            title = (
                "Current status of sorafenib nanoparticle delivery "
                "systems in the treatment of hepatocellular "
                "carcinoma."
            )
            self.assertEqual(r["title"], title)
            self.assertEqual(r["journaldate"], datetime.date(2021, 1, 1))
            self.assertEqual(r["journaldate_granularity"], "y")
            self.assertEqual(r["artdate"], datetime.date(2021, 3, 13))
            pubtypes = [
                "Journal Article",
                "Research Support, Non-U.S. Gov't",
                "Review",
            ]
            self.assertEqual(r["pub_types"], pubtypes)
