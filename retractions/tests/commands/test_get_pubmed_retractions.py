import datetime
import os

from django.test import TestCase

import retractions.pubmed as pubmed
from retractions.management.commands import get_pubmed_retractions
from retractions.models import RetractedPaper, RetractionNotice


class CommandsTestCase(TestCase):
    def setUp(self):
        self.c = get_pubmed_retractions.Command()
        self.c.IS_VERBOSE = False

    def test_get_pubmed_ids_from_results(self):
        data = {"esearchresult": {"idlist": [1, 2, 3]}}
        r = self.c._get_pubmed_ids_from_results(data)
        self.assertEqual(r, [1, 2, 3])

    def test_get_paper_info_from_pubmed_xml(self):
        input_dir = os.path.dirname(__file__)
        fname = os.path.join(input_dir, "../fixtures/pubmed_retracted_publication.xml")
        with open(fname) as myfile:
            xml_str = myfile.read()
            r = pubmed.get_paper_info_from_pubmed_xml(xml_str)
            self.assertEqual(r["doi"], None)
            self.assertEqual(r["issn"], "0021-9258")
            self.assertEqual(r["journal_iso"], "J. Biol. Chem.")
            title = (
                "CREB-binding [corrected] protein interacts with the "
                "homeodomain protein Cdx2 and enhances transcriptional "
                "activity."
            )
            self.assertEqual(r["title"], title)
            self.assertEqual(r["journaldate"], datetime.date(1999, 3, 12))
            self.assertEqual(r["journaldate_granularity"], "d")
            self.assertEqual(r["artdate"], None)
            pubtypes = [
                "Journal Article",
                "Research Support, Non-U.S. Gov't",
                "Research Support, U.S. Gov't, P.H.S.",
                "Retracted Publication",
            ]
            self.assertEqual(r["pub_types"], pubtypes)

    def test__get_paper_info_from_pubmed_xml_journaldate_granularity(self):
        input_dir = os.path.dirname(__file__)
        n = "../fixtures/pubmed_retraction_notice.xml"
        fname = os.path.join(input_dir, n)
        with open(fname) as myfile:
            xml_str = myfile.read()
            r = pubmed.get_paper_info_from_pubmed_xml(xml_str)
            self.assertEqual(r["journaldate"], datetime.date(2016, 5, 1))
            self.assertEqual(r["journaldate_granularity"], "m")

    def test_get_related_pmid_from_notice_xml(self):
        input_dir = os.path.dirname(__file__)
        n = "../fixtures/pubmed_retraction_notice.xml"
        fname = os.path.join(input_dir, n)
        with open(fname) as myfile:
            xml_str = myfile.read()
            paper_id = pubmed.get_related_pmid_from_notice_xml(xml_str)
            self.assertEqual(paper_id, ["26435620"])

    def test_create_paper(self):
        data = {
            "journaltitle": "BMC genomics",
            "journal_iso": "BMC Genomics",
            "doi": "10.1186/1471-2164-15-1089",
            "title": "Species-specific chemosensory gene expression",
            "issn": "1471-2164",
            "artdate": "2016-9-01",
            "journaldate": "2016-8-1",
            "journaldate_granularity": "d",
            "pub_types": ["foo", "bar"],
        }
        self.c._create_or_update_item(data, "123", False)
        paper = RetractedPaper.objects.get(pmid="123")
        self.assertEqual(paper.doi, "10.1186/1471-2164-15-1089")
        self.assertEqual(paper.pub_types[0], "foo")
        self.assertEqual(paper.artdate, datetime.date(2016, 9, 1))
        self.assertEqual(paper.journaldate, datetime.date(2016, 8, 1))
        self.assertEqual(paper.journal_iso, "BMC Genomics")
        self.assertEqual(paper.issn, "1471-2164")

    def test_create_notice(self):
        data = {
            "journaltitle": "BMC genomics",
            "journal_iso": "BMC Genomics",
            "doi": "10.1186/1471-2164-15-1089",
            "title": "Species-specific chemosensory gene expression",
            "issn": "1471-2164",
            "artdate": "2016-9-01",
            "journaldate": "2016-8-1",
            "journaldate_granularity": "d",
            "pub_types": ["foo", "bar"],
        }
        paper = self.c._create_or_update_item(data, "124", False)
        data = {
            "journaltitle": "BMC genomics",
            "journal_iso": "BMC Genomics",
            "doi": "10.1186/1471-2164-15-1089",
            "title": "Species-specific chemosensory gene expression",
            "issn": "1471-2164",
            "artdate": "2016-9-01",
            "journaldate": "2016-8-1",
            "journaldate_granularity": "d",
            "pub_types": [],
            "papers": [paper],
        }
        self.c._create_or_update_item(data, "125", True)
        notice = RetractionNotice.objects.get(pmid="125")
        self.assertEqual(notice.doi, "10.1186/1471-2164-15-1089")
        self.assertEqual(notice.papers.first().pmid, "124")

    def test_notice_m2m(self):
        data = {
            "journaltitle": "JAMA pediatrics",
            "journal_iso": "JAMA Pediatr",
            "doi": "10.1001/jamapediatrics.2013.82",
            "title": """Preordering school lunch encourages better food
                     choices by children.""",
            "issn": "2168-6211",
            "artdate": None,
            "journaldate": "2013-07-01",
            "journaldate_granularity": "m",
            "pub_types": [
                "Letter",
                "Research Support, U.S. Gov't, Non-P.H.S.",
                "Retracted Publication",
            ],
        }
        paper1 = self.c._create_or_update_item(data, "124", False)
        data = {
            "journaltitle": "Archives of pediatrics & adolescent medicine",
            "journal_iso": "Arch Pediatr Adolesc Med",
            "doi": "10.1001/archpedi.162.10.994",
            "title": "Consequences of belonging to the 'clean plate club'.",
            "issn": "1538-3628",
            "artdate": None,
            "journaldate": "2008-10-1",
            "journaldate_granularity": "m",
            "pub_types": [
                "Journal Article",
                "Randomized Controlled Trial",
                "Research Support, Non-U.S. Gov't",
                "Retracted Publication",
            ],
        }
        paper2 = self.c._create_or_update_item(data, "568", False)
        data = {
            "journaltitle": "JAMA pediatrics",
            "journal_iso": None,
            "doi": "10.1001/jamapediatrics.2017.4603",
            "title": """Notice of Retraction. Wansink B, Just DR, Payne CR.
                     Can Branding Improve School Lunches?""",
            "issn": "2168-6211",
            "artdate": None,
            "journaldate": "2017-12-1",
            "journaldate_granularity": "d",
            "pub_types": ["Journal Article", "Retraction of Publication"],
            "papers": [paper2],
        }
        self.c._create_or_update_item(data, "125", True)
        notice = RetractionNotice.objects.get(pmid="125")
        self.assertEqual(notice.doi, "10.1001/jamapediatrics.2017.4603")
        self.assertEqual(notice.papers.first().pmid, "568")

        data = {
            "journaltitle": "JAMA pediatrics",
            "journal_iso": None,
            "doi": "10.1001/jamapediatrics.2018.3747",
            "title": """Notice of Retraction: 'Consequences of Belonging to the
                      Clean Plate Club' and 'Preordering School Lunch
                      Encourages Better Food Choices by Children' by Brian
                      Wansink.""",
            "issn": "2168-6211",
            "artdate": None,
            "journaldate": "2018-11-1",
            "journaldate_granularity": "d",
            "pub_types": ["Journal Article", "Retraction of Publication"],
            "papers": [paper1, paper2],
        }
        self.c._create_or_update_item(data, "569", True)
        notice = RetractionNotice.objects.get(pmid="569")
        self.assertEqual(notice.doi, "10.1001/jamapediatrics.2018.3747")
        self.assertEqual(
            set(notice.papers.values_list("pmid", flat=True)),
            set([paper1.pmid, paper2.pmid]),
        )
        self.assertEqual(paper2.notices.count(), 2)
