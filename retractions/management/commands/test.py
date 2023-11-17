"""
Set logging when you run tests. This has the same name as the built
in Django command and so overrides it.
"""

from django.core.management.commands.test import Command as TestCommand

from common import setup


class Command(TestCommand):
    def handle(self, *args, **options):
        # Set logging in our tests to the -v verbosity set on the command line
        setup.setup_logger(options["verbosity"], test=True)

        super().handle(*args, **options)
