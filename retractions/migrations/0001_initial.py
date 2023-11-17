# Generated by Django 3.2.13 on 2022-05-05 16:11

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Author",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "auid",
                    models.CharField(
                        blank=True,
                        max_length=200,
                        null=True,
                        unique=True,
                        verbose_name="Scopus ID",
                    ),
                ),
            ],
            options={
                "db_table": "author",
            },
        ),
        migrations.CreateModel(
            name="CitationRetractionPair",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("negative_citation", models.BooleanField(blank=True, null=True)),
                ("context_citation", models.BooleanField(blank=True, null=True)),
                (
                    "citation_location",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("SR", "Systematic review"),
                            ("MA", "Meta-analysis"),
                            ("BT", "Both"),
                        ],
                        max_length=2,
                        null=True,
                    ),
                ),
            ],
            options={
                "db_table": "citing_paper_paper",
            },
        ),
        migrations.CreateModel(
            name="RetractedPaper",
            fields=[
                (
                    "doi",
                    models.CharField(
                        blank=True, max_length=200, null=True, verbose_name="DOI"
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=2000, null=True)),
                (
                    "artdate",
                    models.DateField(
                        blank=True,
                        help_text="PubMed Article/ArticleDate field",
                        null=True,
                        verbose_name="Publication date",
                    ),
                ),
                (
                    "journaldate",
                    models.DateField(
                        blank=True,
                        help_text="PubMed Journal/PubDate field, or Scopus coverDate field",
                        null=True,
                        verbose_name="Journal date",
                    ),
                ),
                (
                    "journaldate_granularity",
                    models.CharField(
                        blank=True,
                        choices=[("y", "year"), ("m", "month"), ("d", "day")],
                        help_text="Granularity, which varies in PubMed dates",
                        max_length=1,
                        null=True,
                    ),
                ),
                (
                    "pub_types",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(
                            blank=True, max_length=2000, null=True
                        ),
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "issn",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        null=True,
                        verbose_name="Journal ISSN",
                    ),
                ),
                (
                    "journaltitle",
                    models.CharField(
                        blank=True,
                        help_text="PubMed Journal title",
                        max_length=500,
                        null=True,
                        verbose_name="Journal title",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pmid",
                    models.CharField(
                        max_length=200,
                        primary_key=True,
                        serialize=False,
                        verbose_name="PubMed ID",
                    ),
                ),
                (
                    "scopus_id",
                    models.CharField(
                        blank=True, max_length=200, null=True, verbose_name="Scopus ID"
                    ),
                ),
                (
                    "journal_iso",
                    models.CharField(
                        blank=True,
                        help_text="PubMed Journal/ISOAbbreviation",
                        max_length=100,
                        null=True,
                        verbose_name="Journal ISO name",
                    ),
                ),
                ("in_rct_cohort", models.BooleanField(default=False)),
                (
                    "rct_group",
                    models.CharField(
                        choices=[
                            ("p", "Pilot"),
                            ("c", "Control group"),
                            ("i", "Intervention group"),
                            ("x", "Excluded group"),
                        ],
                        default=None,
                        help_text="Included in our RCT, and if so which group it ended up in",
                        max_length=1,
                        null=True,
                    ),
                ),
                (
                    "exclusion_reason",
                    models.CharField(
                        help_text="Reason for exclusion from the RCT",
                        max_length=100,
                        null=True,
                    ),
                ),
            ],
            options={
                "db_table": "retracted_paper",
            },
        ),
        migrations.CreateModel(
            name="RetractionNotice",
            fields=[
                (
                    "doi",
                    models.CharField(
                        blank=True, max_length=200, null=True, verbose_name="DOI"
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=2000, null=True)),
                (
                    "artdate",
                    models.DateField(
                        blank=True,
                        help_text="PubMed Article/ArticleDate field",
                        null=True,
                        verbose_name="Publication date",
                    ),
                ),
                (
                    "journaldate",
                    models.DateField(
                        blank=True,
                        help_text="PubMed Journal/PubDate field, or Scopus coverDate field",
                        null=True,
                        verbose_name="Journal date",
                    ),
                ),
                (
                    "journaldate_granularity",
                    models.CharField(
                        blank=True,
                        choices=[("y", "year"), ("m", "month"), ("d", "day")],
                        help_text="Granularity, which varies in PubMed dates",
                        max_length=1,
                        null=True,
                    ),
                ),
                (
                    "pub_types",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(
                            blank=True, max_length=2000, null=True
                        ),
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "issn",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        null=True,
                        verbose_name="Journal ISSN",
                    ),
                ),
                (
                    "journaltitle",
                    models.CharField(
                        blank=True,
                        help_text="PubMed Journal title",
                        max_length=500,
                        null=True,
                        verbose_name="Journal title",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pmid",
                    models.CharField(
                        max_length=200,
                        primary_key=True,
                        serialize=False,
                        verbose_name="PubMed ID",
                    ),
                ),
                (
                    "paper",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="retraction_notices",
                        to="retractions.retractedpaper",
                    ),
                ),
            ],
            options={
                "db_table": "retraction_notice",
            },
        ),
        migrations.CreateModel(
            name="MailSent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "message_id",
                    models.CharField(
                        db_index=True,
                        max_length=1000,
                        null=True,
                        verbose_name="The Message-ID of sent mail returned from Mailgun",
                    ),
                ),
                (
                    "to",
                    models.TextField(
                        null=True,
                        verbose_name="Emails and names sent to, in form like an email To: field",
                    ),
                ),
                (
                    "recentest_citing_paper_id",
                    models.TextField(
                        null=True,
                        verbose_name="The Scopus ID of the most recent citing paper in the email",
                    ),
                ),
                (
                    "citing_paper_ids",
                    models.TextField(
                        null=True,
                        verbose_name="The Scopus ID of each citing paper in the email, oldest first, | separated",
                    ),
                ),
                ("accepted", models.DateTimeField(blank=True, null=True)),
                ("delivered", models.DateTimeField(blank=True, null=True)),
                ("opened", models.DateTimeField(blank=True, null=True)),
                ("unsubscribed", models.DateTimeField(blank=True, null=True)),
                ("clicked_didntknow", models.DateTimeField(blank=True, null=True)),
                ("clicked_alreadyknew", models.DateTimeField(blank=True, null=True)),
                ("clicked_explicitly", models.DateTimeField(blank=True, null=True)),
                ("clicked_other", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mails_sent",
                        to="retractions.author",
                    ),
                ),
                (
                    "paper",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mails_sent",
                        to="retractions.retractedpaper",
                    ),
                ),
            ],
            options={
                "db_table": "mail_sent",
            },
        ),
        migrations.CreateModel(
            name="CitingPaper",
            fields=[
                (
                    "doi",
                    models.CharField(
                        blank=True, max_length=200, null=True, verbose_name="DOI"
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=2000, null=True)),
                (
                    "artdate",
                    models.DateField(
                        blank=True,
                        help_text="PubMed Article/ArticleDate field",
                        null=True,
                        verbose_name="Publication date",
                    ),
                ),
                (
                    "journaldate",
                    models.DateField(
                        blank=True,
                        help_text="PubMed Journal/PubDate field, or Scopus coverDate field",
                        null=True,
                        verbose_name="Journal date",
                    ),
                ),
                (
                    "journaldate_granularity",
                    models.CharField(
                        blank=True,
                        choices=[("y", "year"), ("m", "month"), ("d", "day")],
                        help_text="Granularity, which varies in PubMed dates",
                        max_length=1,
                        null=True,
                    ),
                ),
                (
                    "pub_types",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(
                            blank=True, max_length=2000, null=True
                        ),
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "issn",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        null=True,
                        verbose_name="Journal ISSN",
                    ),
                ),
                (
                    "journaltitle",
                    models.CharField(
                        blank=True,
                        help_text="PubMed Journal title",
                        max_length=500,
                        null=True,
                        verbose_name="Journal title",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scopus_id",
                    models.CharField(
                        max_length=200,
                        primary_key=True,
                        serialize=False,
                        verbose_name="Scopus ID",
                    ),
                ),
                (
                    "pmid",
                    models.CharField(
                        blank=True, max_length=200, null=True, verbose_name="PubMed ID"
                    ),
                ),
                (
                    "journalname",
                    models.CharField(
                        blank=True,
                        help_text="Scopus prism:publicationName",
                        max_length=500,
                        null=True,
                        verbose_name="Journal name",
                    ),
                ),
                (
                    "prismcoverdate",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Scopus prism:coverDate field",
                    ),
                ),
                ("full_text", models.BooleanField(blank=True, null=True)),
                (
                    "retraction_flagged",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("JP", "Journal webpage"),
                            ("PM", "Pubmed"),
                            ("BT", "Both"),
                            ("NT", "Neither"),
                        ],
                        max_length=2,
                        null=True,
                    ),
                ),
                (
                    "litsearch_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="Literature search date"
                    ),
                ),
                (
                    "paper",
                    models.ManyToManyField(
                        through="retractions.CitationRetractionPair",
                        to="retractions.RetractedPaper",
                    ),
                ),
            ],
            options={
                "db_table": "citing_paper",
            },
        ),
        migrations.AddField(
            model_name="citationretractionpair",
            name="citingpaper",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="retractions.citingpaper",
            ),
        ),
        migrations.AddField(
            model_name="citationretractionpair",
            name="retractedpaper",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="retractions.retractedpaper",
            ),
        ),
        migrations.AddField(
            model_name="author",
            name="papers",
            field=models.ManyToManyField(
                related_name="authors", to="retractions.CitingPaper"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="citationretractionpair",
            unique_together={("citingpaper", "retractedpaper")},
        ),
        migrations.CreateModel(
            name="AuthorAlias",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "email_address",
                    models.EmailField(blank=True, max_length=254, null=True),
                ),
                ("surname", models.CharField(blank=True, max_length=1000, null=True)),
                (
                    "given_name",
                    models.CharField(blank=True, max_length=1000, null=True),
                ),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="author_aliases",
                        to="retractions.author",
                    ),
                ),
            ],
            options={
                "db_table": "author_alias",
                "unique_together": {("author", "email_address")},
            },
        ),
    ]
