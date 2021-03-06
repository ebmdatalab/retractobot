# Generated by Django 3.2.15 on 2022-10-12 20:49

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("retractions", "0003_paper_authors"),
    ]

    operations = [
        migrations.AddField(
            model_name="retractionnotice",
            name="papers",
            field=models.ManyToManyField(
                related_name="notices", to="retractions.RetractedPaper"
            ),
        ),
    ]
