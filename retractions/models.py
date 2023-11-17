import urllib.parse

from django.contrib.postgres.fields import ArrayField
from django.db import models

from common import fetch_utils


class Paper(models.Model):
    """
    Base class for retracted papers, retraction notices, and
    citing papers.
    """

    DATE_GRANULARITY = (("y", "year"), ("m", "month"), ("d", "day"))
    doi = models.CharField(max_length=200, null=True, blank=True, verbose_name="DOI")
    title = models.CharField(max_length=2000, null=True, blank=True)
    artdate = models.DateField(
        "Publication date",
        null=True,
        blank=True,
        help_text=("PubMed Article/ArticleDate field"),
    )
    journaldate = models.DateField(
        "Journal date",
        null=True,
        blank=True,
        help_text=("PubMed Journal/PubDate field, or Scopus coverDate field"),
    )
    journaldate_granularity = models.CharField(
        max_length=1,
        null=True,
        blank=True,
        choices=DATE_GRANULARITY,
        help_text=("Granularity, which varies in PubMed dates"),
    )
    pub_types = ArrayField(
        models.CharField(max_length=2000, null=True, blank=True), default=list
    )
    issn = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="Journal ISSN"
    )
    journaltitle = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Journal title",
        help_text="PubMed Journal title",
    )
    comparisondate = models.DateField(
        "Comparison date",
        null=True,
        blank=True,
        help_text=("Best available date field"),
    )
    errors = models.CharField(max_length=2000, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def url(self):
        if self.pmid:
            return "https://www.ncbi.nlm.nih.gov/pubmed/?term=%s" % urllib.parse.quote(
                self.pmid
            )
        else:
            assert self.doi
            return "http://dx.doi.org/%s" % urllib.parse.quote(self.doi)


RCT_CHOICES = (
    ("c", "Control group"),  # no email is sent
    ("i", "Intervention group"),  # email is sent
    ("x", "Excluded group"),  # no emails would be sent, so wasn't put in RCT
)


class RetractedPaper(Paper):
    pmid = models.CharField(primary_key=True, max_length=200, verbose_name="PubMed ID")
    scopus_id = models.CharField(
        null=True, blank=True, max_length=200, verbose_name="Scopus ID"
    )
    journal_iso = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Journal ISO name",
        help_text="PubMed Journal/ISOAbbreviation",
    )

    rct_group = models.CharField(
        max_length=1,
        choices=RCT_CHOICES,
        null=True,
        default=None,
        help_text="Included in our RCT, and if so which group it ended up in",
    )
    exclusion_reason = models.CharField(
        max_length=100,
        null=True,
        help_text="Reason for exclusion from the RCT",
    )
    stratifying_group = models.IntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.scopus_id:
            # Get rid of random prefixes, and just save the ID.
            # The second of these is the "Scopus EID", but it's always
            # prefixed with "2-s2.0-" so we can recreate the EID
            # programmatically where we need to.
            self.scopus_id = self.scopus_id.replace("SCOPUS_ID:", "")
            self.scopus_id = self.scopus_id.replace("2-s2.0-", "")
        super().save(*args, **kwargs)

    def scopus_paper_url(self):
        url = "https://api.elsevier.com/content/abstract/"
        url += "scopus_id/%s?" % self.scopus_id
        url += fetch_utils.sorted_urlencode({"httpAccept": "application/json"})
        return url

    def get_notice(self):
        # sort by PMID, which is roughly a sort by date
        notices = (
            self.notices.all()
            .extra(select={"pmid_float": "pmid::float"})
            .order_by("pmid_float")
        )
        # take the earliest retraction notice
        return notices[0]

    class Meta:
        db_table = "retracted_paper"


class RetractionNotice(Paper):
    pmid = models.CharField(primary_key=True, max_length=200, verbose_name="PubMed ID")
    papers = models.ManyToManyField(
        RetractedPaper,
        related_name="notices",
    )

    class Meta:
        db_table = "retraction_notice"

    def comparison_date(self):
        return self.artdate or self.journaldate


class CitingPaper(Paper):
    # One paper can cite multiple retracted papers, so we use a many to many
    # relationship and scopus_id as the primary key
    scopus_id = models.CharField(
        primary_key=True, max_length=200, verbose_name="Scopus ID"
    )

    pmid = models.CharField(
        null=True, blank=True, max_length=200, verbose_name="PubMed ID"
    )
    paper = models.ManyToManyField(
        "RetractedPaper",
        through="CitationRetractionPair",
    )
    journalname = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Journal name",
        help_text="Scopus prism:publicationName",
    )

    prismcoverdate = models.DateField(
        "Scopus prism:coverDate field", null=True, blank=True
    )

    cited_in_rct = models.BooleanField(default=False)

    # Manually extracted optional fields
    full_text = models.BooleanField(null=True, blank=True)

    class FlaggedLocation(models.TextChoices):
        JOURNAL = "JP", "Journal webpage"
        PUBMED = "PM", "Pubmed"
        BOTH = "BT", "Both"
        NEITHER = "NT", "Neither"

    retraction_flagged = models.CharField(
        max_length=2, choices=FlaggedLocation.choices, null=True, blank=True
    )
    litsearch_date = models.DateField(
        "Literature search date",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "citing_paper"

    def scopus_paper_url(self):
        url = "https://api.elsevier.com/content/abstract/"
        url += "scopus_id/%s?" % self.scopus_id
        url += fetch_utils.sorted_urlencode({"httpAccept": "application/json"})
        return url


class CitationRetractionPair(models.Model):
    citingpaper = models.ForeignKey(CitingPaper, on_delete=models.CASCADE)
    retractedpaper = models.ForeignKey("RetractedPaper", on_delete=models.CASCADE)

    negative_citation = models.BooleanField(null=True, blank=True)
    context_citation = models.BooleanField(null=True, blank=True)

    class PublicationType(models.TextChoices):
        REVIEW = "SR", "Systematic review"
        META = "MA", "Meta-analysis"
        BOTH = "BT", "Both"

    citation_location = models.CharField(
        max_length=2, choices=PublicationType.choices, null=True, blank=True
    )

    class Meta:
        db_table = "citing_paper_paper"
        unique_together = (("citingpaper", "retractedpaper"),)


class Author(models.Model):
    citing_papers = models.ManyToManyField(CitingPaper, related_name="authors")
    retracted_papers = models.ManyToManyField(RetractedPaper, related_name="authors")
    pairs = models.ManyToManyField(
        CitationRetractionPair, related_name="contactable_authors"
    )

    auid = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name="Scopus ID",
        unique=True,
    )

    class Meta:
        db_table = "author"


# Each author can have lots of email addresses, e.g. as they move between
# universities
class AuthorAlias(models.Model):
    author = models.ForeignKey(
        Author,
        related_name="author_aliases",
        on_delete=models.CASCADE,
    )
    email_address = models.EmailField(null=True, blank=True)

    surname = models.CharField(max_length=1000, null=True, blank=True)
    given_name = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        db_table = "author_alias"
        unique_together = ("author", "email_address")

    def full_name(self):
        return ("{} {}".format(self.given_name or "", self.surname or "")).strip()


class MailSent(models.Model):
    # We send one email per citing paper author
    pairs = models.ManyToManyField(
        CitationRetractionPair,
        related_name="mails_sent",
    )
    author = models.ForeignKey(
        Author,
        related_name="mail_sent",
        on_delete=models.CASCADE,
    )

    # Message id of sent mail returned by Mailgun
    message_id = models.CharField(
        max_length=1000,
        verbose_name="The Message-ID of sent mail returned from Mailgun",
        null=True,
        db_index=True,
    )
    to = models.TextField(
        null=True,
        verbose_name=("Emails and names sent to, in form like an email To: field"),
    )

    # Info about citing papers email is about
    recentest_citing_paper_id = models.TextField(
        null=True,
        verbose_name=("The Scopus ID of the most recent citing paper in the email"),
    )

    # Populated via Mailgun
    accepted = models.DateTimeField(null=True, blank=True)
    delivered = models.DateTimeField(null=True, blank=True)
    opened = models.DateTimeField(null=True, blank=True)
    unsubscribed = models.DateTimeField(null=True, blank=True)

    clicked_didntknowany = models.DateTimeField(null=True, blank=True)
    clicked_alreadyknewall = models.DateTimeField(null=True, blank=True)
    clicked_alreadyknewsome = models.DateTimeField(null=True, blank=True)
    clicked_other = models.DateTimeField(null=True, blank=True)

    # Just database default times for this model
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mail_sent"
