from django.test import TestCase

from retractions.models import CitationRetractionPair, CitingPaper, RetractedPaper


class ModelsTestCase(TestCase):
    def test_get_scopus_paper_url(self):
        retracted_paper = RetractedPaper.objects.create(pmid="123", title="Foo bar")
        citing_paper = CitingPaper.objects.create(scopus_id="456")
        citing_paper.paper.add(retracted_paper)

        url = citing_paper.scopus_paper_url()
        expected = (
            "https://api.elsevier.com/content/abstract/scopus_id/"
            "456?httpAccept=application%2Fjson"
        )
        self.assertEqual(url, expected)

    def test_citationretractionpair(self):
        """
        Test that the custom ManyToMany model is auto populated
        """
        retracted_paper1 = RetractedPaper.objects.create(pmid="123", title="Foo bar")
        retracted_paper2 = RetractedPaper.objects.create(pmid="456", title="Bar foo")
        citing_paper = CitingPaper.objects.create(scopus_id="789")
        citing_paper.paper.add(retracted_paper1)
        citing_paper.paper.add(retracted_paper2)
        self.assertEqual(CitationRetractionPair.objects.count(), 2)

    def test_citation_publicationtype(self):
        retracted_paper = RetractedPaper.objects.create(pmid="123", title="Foo bar")
        citing_paper = CitingPaper.objects.create(scopus_id="456")
        citing_paper.paper.add(retracted_paper)
        pair = CitationRetractionPair.objects.get(
            citingpaper=citing_paper, retractedpaper=retracted_paper
        )
        pair.citation_location = CitationRetractionPair.PublicationType.REVIEW
        self.assertEqual(pair.citation_location.label, "Systematic review")

    def test_citing_flagged_location(self):
        citing_paper = CitingPaper.objects.create(scopus_id="456")
        citing_paper.retraction_flagged = CitingPaper.FlaggedLocation.NEITHER
        self.assertEqual(citing_paper.retraction_flagged.label, "Neither")
