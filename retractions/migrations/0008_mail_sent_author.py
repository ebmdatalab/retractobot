# Generated by Django 3.2.15 on 2022-10-22 15:54

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("retractions", "0007_author_pairs"),
    ]

    operations = [
        migrations.RenameField(
            model_name="mailsent",
            old_name="clicked_alreadyknew",
            new_name="clicked_alreadyknewall",
        ),
        migrations.RenameField(
            model_name="mailsent",
            old_name="clicked_didntknow",
            new_name="clicked_didntknowany",
        ),
        migrations.RemoveField(
            model_name="mailsent",
            name="citing_paper_ids",
        ),
        migrations.RemoveField(
            model_name="mailsent",
            name="clicked_explicitly",
        ),
        migrations.RemoveField(
            model_name="mailsent",
            name="paper",
        ),
        migrations.AddField(
            model_name="mailsent",
            name="clicked_alreadyknewsome",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mailsent",
            name="pairs",
            field=models.ManyToManyField(
                related_name="mails_sent", to="retractions.CitationRetractionPair"
            ),
        ),
        migrations.AlterField(
            model_name="mailsent",
            name="author",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mail_sent",
                to="retractions.author",
            ),
        ),
        migrations.AlterField(
            model_name="retractedpaper",
            name="rct_group",
            field=models.CharField(
                choices=[
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
    ]
