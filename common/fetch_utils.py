import collections
import concurrent.futures as futures
import logging
import time
import timeit
from urllib import parse

import requests
from django.conf import settings

from common.setup import get_env_setting


def add_url_params(url, params):
    """Add GET params to URL, respecting existing"""
    # Extracting url info
    parsed_url = parse.urlparse(url)
    # Extracting URL arguments from parsed URL
    get_args = parsed_url.query
    # Converting URL arguments to dict
    parsed_get_args = dict(parse.parse_qsl(get_args))
    # Merging URL arguments dict with new params
    parsed_get_args.update(params)
    # Converting URL argument to proper query string
    encoded_get_args = parse.urlencode(parsed_get_args, doseq=True)
    # Creating new parsed result object based on provided with new
    # URL arguments. Same thing happens inside of urlparse.
    new_url = parse.urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            encoded_get_args,
            parsed_url.fragment,
        )
    )
    return new_url


def fetch_urls_parallel(urls, is_scopus=False):
    if is_scopus:
        # Their API is flakey
        threads = 2
    else:
        if settings.USE_NCBI_API_KEY:
            # Rate limit with API key is 10 queries/second
            # We occasionally hit the limit with 4 threads
            threads = 3
            logging.info(f"Using pubmed api key with {threads} thread(s)")
        else:
            # If we are not using the API key, run
            threads = 1
            logging.info(f"No pubmed api key, using {threads} thread(s)")
    c = len(urls)
    logging.info("Fetching %d URLs in parallel", c)
    start = timeit.default_timer()

    # number of simultaneous requests
    pool = futures.ThreadPoolExecutor(threads)
    fs = [pool.submit(fetch_url, url, is_scopus) for url in urls]

    for r in futures.as_completed(fs):
        logging.debug("Future completed: %s", r)

    # Pull out results separately, so we get them in the right order
    results = [r.result() for r in fs]

    end = timeit.default_timer()
    logging.info("Time taken to fetch URLs in parallel: %s", end - start)

    return results


def fetch_url(url, is_scopus=False, paper_id=None):
    logging.info("  Fetching url %s", url)
    if url is None:
        return None
    domain = parse.urlparse(url).netloc

    if "ncbi.nlm.nih.gov" in domain:
        if settings.USE_NCBI_API_KEY:
            api_key = get_env_setting("NCBI_API_KEY")
            url = add_url_params(url, {"api_key": api_key})
        else:
            logging.warning("Use of pubmed API key has been suppressed")
    got_response = False
    attempt_count = 0
    while not got_response:
        if attempt_count > 2:
            logging.warning(
                "FAILED to get info after many goes. For: paper %s scopus %s",
                paper_id,
                is_scopus,
            )
            return
        try:
            headers = {}
            if is_scopus:
                headers = {
                    "X-ELS-Insttoken": get_env_setting("SCOPUS_INSTTOKEN"),
                    "X-ELS-APIKey": get_env_setting("SCOPUS_API_KEY"),
                }
            start = timeit.default_timer()
            resp = requests.get(url, timeout=300, headers=headers)
            end = timeit.default_timer()
            logging.info("  Time taken %s to fetch URL %s", end - start, url)
            if not resp.ok:
                logging.warning("  Bad response %s to fetch URL %s", resp, url)
                time.sleep(5)
            else:
                got_response = True
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
        ):
            logging.warning(
                "  Connection error PMID %s fetching "
                "URL %s attempt %d, Headers: %s ",
                paper_id,
                url,
                attempt_count,
                headers,
            )
            time.sleep(5)
        attempt_count = attempt_count + 1
    return resp


# So idempotent for caching with requests_cache
def sorted_urlencode(params):
    pairs = params.items()
    sorted_pairs = sorted(pairs)
    ordered_params = collections.OrderedDict(sorted_pairs)
    return parse.urlencode(ordered_params)
