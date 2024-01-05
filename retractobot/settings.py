from pathlib import Path

from environs import Env


# Build paths inside the project like this: SITE_ROOT / ...
SITE_ROOT = Path(__file__).resolve().parent.parent

env = Env()
env.read_env(SITE_ROOT / "environment")

SECRET_KEY = env.str("RETR_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CACHE_API_CALLS = env.bool("RETR_CACHE_API_CALLS")
USE_NCBI_API_KEY = env.bool("RETR_USE_NCBI_API_KEY")  # use pubmed auth

# Application definition

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "anymail",
    "retractions",
]


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env.str("RETR_DB_HOST"),
        "NAME": env.str("RETR_DB_NAME"),
        "USER": env.str("RETR_DB_USER"),
        "PASSWORD": env.str("RETR_DB_PASS"),
    }
}


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = False
USE_L10N = True
USE_TZ = False

# Email config
ANYMAIL = {
    "MAILGUN_API_KEY": env.str("RETR_MAILGUN_API_KEY"),
    "MAILGUN_API_URL": "https://api.eu.mailgun.net/v3",
    "MAILGUN_SENDER_DOMAIN": "retracted.net",
}
EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"


FIXTURE_DIRS = ((SITE_ROOT / "retractions" / "tests" / "fixtures"),)

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
