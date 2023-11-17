from datetime import date

import lxml
from django.test import TestCase

from retractions.pubmed import get_pubmed_date_from_medline, get_pubmed_date_from_node


class PubmedDatesTestCase(TestCase):
    # Date formats documented here:
    # https://www.nlm.nih.gov/bsd/licensee/elements_descriptions.html
    def test_get_date_from_structured_node_day_granularity(self):
        node = lxml.etree.fromstring(
            """
            <DateRevised><Year>2000</Year>
            <Month>Jan</Month>
            <Day>3</Day></DateRevised>
        """
        )
        expected = {"date": date(2000, 1, 3), "granularity": "d"}

        self.assertEqual(get_pubmed_date_from_node(node), expected)

    def test_get_date_from_structured_node_minute_granularity(self):
        node = lxml.etree.fromstring(
            """<PubMedPubDate PubStatus="entrez">
                <Year>2008</Year>
                <Month>1</Month>
                <Day>22</Day>
                <Hour>9</Hour>
                <Minute>0</Minute>
                </PubMedPubDate>"""
        )
        expected = {"date": date(2008, 1, 22), "granularity": "d"}

        self.assertEqual(get_pubmed_date_from_node(node), expected)

    def test_get_date_from_structured_node_month_granularity(self):
        node = lxml.etree.fromstring("<Date><Year>2000</Year><Month>Jan</Month></Date>")
        expected = {"date": date(2000, 1, 1), "granularity": "m"}

        self.assertEqual(get_pubmed_date_from_node(node), expected)

    def test_get_date_from_text_node(self):
        node = lxml.etree.fromstring(
            "<PubDate><MedlineDate>2007 Nov-Dec</MedlineDate></PubDate>"
        )
        expected = {"date": date(2007, 11, 1), "granularity": "m"}

        self.assertEqual(get_pubmed_date_from_node(node), expected)

    def test_get_pubmed_date_from_medline(self):
        for s, expected in [
            ("1983 Sep 22-28", {"date": date(1983, 9, 22), "granularity": "d"}),
            ("1984 Jul-Aug", {"date": date(1984, 7, 1), "granularity": "m"}),
            ("2007 Aug 9-Sep 12", {"date": date(2007, 8, 9), "granularity": "d"}),
            ("2012", {"date": date(2012, 1, 1), "granularity": "y"}),
            ("2018 Jul/Aug", {"date": date(2018, 7, 1), "granularity": "m"}),
            ("2018 Mar - Apr", {"date": date(2018, 3, 1), "granularity": "m"}),
            ("Winter 2016", {"date": date(2016, 1, 1), "granularity": "m"}),
        ]:
            self.assertEqual(get_pubmed_date_from_medline(s), expected)
