# Generated by Django 3.2.15 on 2022-10-12 21:23

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("retractions", "0005_retractionnotice_papers_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="retractionnotice",
            name="paper",
        ),
    ]
