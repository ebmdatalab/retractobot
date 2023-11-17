import logging
from os import environ

from django.core.exceptions import ImproperlyConfigured


# Take the Django manage.py command line verbosity option and apply it as a
# general logging level in Python. Set test to True if in test mode.
def setup_logger(verbosity, test=False):
    handlers = [logging.StreamHandler()]
    # If specified in an environment var, also write to file
    # This will be desired for the run for the RCT
    log_file = environ.get("RETR_LOG_FILE")
    if log_file:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)

    if test:
        # By default (verbosity 1) don't log exceptions in test as we
        # deliberately raise them
        logging_level = logging.CRITICAL
        if verbosity > 1:
            logging_level = logging.WARNING
        if verbosity > 2:
            logging_level = logging.INFO
    else:
        logging_level = logging.ERROR
        if verbosity > 0:
            logging_level = logging.WARNING
        if verbosity > 1:
            logging_level = logging.INFO
        if verbosity > 2:
            logging_level = logging.DEBUG

    # database logging
    if verbosity > 2:
        ll = logging.getLogger("django.db.backends")
        ll.setLevel(logging.DEBUG)

    logging.basicConfig(
        level=logging_level,
        format="%(asctime)s: %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def get_env_setting(setting):
    """Get the environment setting or return exception"""
    try:
        return environ[setting]
    except KeyError:
        error_msg = "Set the %s env variable" % setting
        raise ImproperlyConfigured(error_msg)
