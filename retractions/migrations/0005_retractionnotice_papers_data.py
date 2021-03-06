# Generated by Django 3.2.15 on 2022-10-12 20:29

from django.db import migrations


def forward(apps, schema_editor):
    RetractionNotice = apps.get_model("retractions", "RetractionNotice")
    for notice in RetractionNotice.objects.all():
        if notice.paper:
            notice.papers.add(notice.paper)


def backward(apps, schema_editor):
    # NOTE: in order to know which notices might have had more than one paper
    # we drop all
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("retractions", "0004_retractionnotice_papers"),
    ]

    operations = [migrations.RunPython(forward, backward)]
