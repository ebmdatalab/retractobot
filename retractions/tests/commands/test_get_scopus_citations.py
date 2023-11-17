import json
import os
import re

import vcr
from django.test import TestCase
from vcr.filters import decode_response

from common import setup
from retractions.management.commands import get_scopus_citations
from retractions.models import CitationRetractionPair, CitingPaper, RetractedPaper


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
    return response


class CommandsTestCase(TestCase):
    def setUp(self):
        self.c = get_scopus_citations.Command()
        setup.setup_logger(2)

    def _get_scopus_id_from_pmid(self):
        pass

    def test_check_cassette(self):
        """
        Check there are no environment vars in the test file
        This is to ensure there are no secret keys
        """
        keys = set(dict(setup.environ).keys())
        vals = set(dict(setup.environ).values())
        with vcr.use_cassette(
            "fixtures/vcr_cassettes/citations_list.yaml",
            allow_playback_repeats=True,
            filter_headers=["X-ELS-APIKey", "X-ELS-Insttoken"],
            before_record_response=scrub_string,
        ) as cass:
            for res in cass.responses:
                # Cassette may already be decoded, but we decode to make sure
                decoded = decode_response(res)
                self.assertEqual(
                    len(set(decoded["headers"].keys()).intersection(keys)), 0
                )
                self.assertEqual(
                    len(set(sum(decoded["headers"].values(), [])).intersection(vals)),
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
        "fixtures/vcr_cassettes/citations_list.yaml",
        allow_playback_repeats=True,
        filter_headers=["X-ELS-APIKey", "X-ELS-Insttoken"],
        before_record_response=scrub_string,
    )
    def test_check_existing(self):
        """
        Existing citing papers should not be recreated
        """
        RetractedPaper.objects.create(pmid="18204201", title="Foo bar")
        c = CitingPaper.objects.create(scopus_id="49049117794", pmid=1234)
        creation_date = c.created_at
        self.c.handle(verbosity=0)
        self.assertEqual(CitationRetractionPair.objects.count(), 92)
        self.assertEqual(
            CitingPaper.objects.get(scopus_id=c.scopus_id).created_at, creation_date
        )

    def test_get_citations_from_json(self):
        input_dir = os.path.dirname(__file__)
        fname = os.path.join(input_dir, "../fixtures/scopus-citations.json")
        data = json.load(open(fname))
        citations = self.c._get_citations_from_json(data)
        self.assertEqual(len(citations), 20)
