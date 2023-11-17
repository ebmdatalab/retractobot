import datetime
import json
import logging
import re

import lxml.etree

from common import fetch_utils


month_mapper = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

season_mapper = {
    "Summer": 7,
    "Spring": 4,
    "Winter": 1,
    "Fall": 10,
}


def get_paper_xml(pmid):
    """Fetch XML about one paper via its PMID (PubMed ID)"""
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        "?db=pubmed&rettype=abstract&id=%s"
    ) % pmid
    resp = fetch_utils.fetch_url(url=url, is_scopus=False)
    return resp.text


def get_paper_xml_parallel(pmids):
    """Fetch XML about multiple papers via their PMIDs (PubMed ID), in
    parallel for speed.
    """

    def make_url(pmid):
        if pmid:
            return (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                "?db=pubmed&rettype=abstract&id=%s"
            ) % pmid
        else:
            return None

    urls = [make_url(pmid) for pmid in pmids]
    rs = fetch_utils.fetch_urls_parallel(urls, is_scopus=False)

    def get_text(r):
        if r:
            return r.text
        else:
            return None

    ress = [get_text(r) for r in rs]
    return ress


def get_pmid_via_dois_parallel(dois):
    """
    Search pubmed for papers via the DOI, e.g. 10.1177/0148607111413903
    Returns their PMIDs. Does multiple papers at once for speed.
    """

    def make_url(doi):
        if doi:
            return (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                "?db=pubmed&retmode=json&field=aid&term=%s"
            ) % doi
        else:
            return None

    urls = [make_url(doi) for doi in dois]
    rs = fetch_utils.fetch_urls_parallel(urls, is_scopus=False)

    def get_pmid(r):
        errors = None
        if r:
            data = json.loads(r.text)
            search_result = data["esearchresult"]
            c = int(search_result.get("count", 0))
            if search_result.get("errorlist"):
                errors = ",".join(
                    [key for key, val in search_result.get("errorlist").items() if val]
                )
                logging.warning(
                    f"Error querying pubmed {search_result.get('errorlist')}"
                )
                return (None, errors)
            if c < 1:
                errors = "Found no results searching for DOI"
                logging.error(search_result)
                return (None, errors)
            if c == 2:
                logging.warning(
                    "Found two results searching for DOI, using first one: %s",
                    search_result["idlist"],
                )
                errors = "Found two results searching for DOI"
            if c > 2:
                logging.error("Found many entries searching up DOI: %s", r.text)
                assert False
            assert len(search_result["idlist"]) == c
            return (search_result["idlist"][0], errors)

        else:
            return None

    ress = [get_pmid(r) for r in rs]
    return ress


def get_paper_info_from_pubmed_xml(xml_str):
    """
    Extract fields of interest from PubMed XML. We don't know
    now exactly what we're going to want, but save the key bits.
    Use get_or_create rather than update_or_create to avoid
    creating multiple objects if any of the details change.
    """

    assert isinstance(xml_str, str)

    data = {
        "pmid": None,
        "doi": None,
        "issn": None,
        "journaltitle": None,
        "journal_iso": None,
        "title": None,
        "artdate": None,
        "journaldate": None,
        "journaldate_granularity": None,
        "pub_types": [],
    }
    tree = lxml.etree.fromstring(xml_str)

    xpath = ".//PubmedData/ArticleIdList/ArticleId"
    article_ids = tree.findall(xpath)
    for a in article_ids:
        if a.get("IdType") == "doi":
            data["doi"] = a.text
        if a.get("IdType") == "pubmed":
            data["pmid"] = a.text
    xpath = ".//PublicationType"
    pub_types = tree.findall(xpath)
    for pub_type in pub_types:
        data["pub_types"].append(pub_type.text)
    journal = tree.find(".//Article/Journal")
    if journal is not None:
        issn_el = journal.find("ISSN")
        if issn_el is not None:
            data["issn"] = issn_el.text
        journaltitle_el = journal.find("Title")
        if journaltitle_el is not None:
            data["journaltitle"] = journaltitle_el.text
        journaldate = journal.find("JournalIssue/PubDate")
        iso_el = journal.find("ISOAbbreviation")
        if iso_el is not None:
            data["journal_iso"] = iso_el.text
        jdate = get_pubmed_date_from_node(journaldate)
        data["journaldate"] = jdate["date"]
        if data["journaldate"]:
            data["journaldate_granularity"] = jdate["granularity"]

    articledate = tree.find(".//Article/ArticleDate")
    adate = get_pubmed_date_from_node(articledate)
    data["artdate"] = adate["date"]
    if data["artdate"]:
        assert adate["granularity"] == "d"

    createddate = tree.find(".//MedlineCitation/DateCreated")
    cdate = get_pubmed_date_from_node(createddate)
    data["createddate"] = cdate["date"]
    if data["createddate"]:
        assert cdate["granularity"] == "d"

    reviseddate = tree.find(".//MedlineCitation/DateRevised")
    rdate = get_pubmed_date_from_node(reviseddate)
    data["reviseddate"] = rdate["date"]
    if data["reviseddate"]:
        assert rdate["granularity"] == "d"

    for status in [
        "accepted",
        "entrez",
        "medline",
        "pubmed",
        "received",
        "revised",
    ]:
        status_path = './/History/PubMedPubDate[@PubStatus = "%s"]' % status
        historydate = tree.find(status_path)
        hdate = get_pubmed_date_from_node(historydate)
        data["historydate-" + status] = hdate["date"]
        if data["historydate-" + status]:
            assert hdate["granularity"] == "d"

    title = tree.find(".//Article/ArticleTitle")
    if title is not None and title.text:
        data["title"] = title.text
    if all([(x is None or x == []) for x in data.values()]):
        data["errors"] = "Pubmed returned no data"
    return data


def get_related_pmid_from_notice_xml(xml_str):
    """
    Extract ids of retracted papers from retraction notice PubMed XML.
    """
    tree = lxml.etree.fromstring(xml_str)
    xpath = ".//CommentsCorrectionsList/CommentsCorrections"
    corrections = tree.findall(xpath)
    pmids = []
    for c in corrections:
        if c.get("RefType") == "RetractionOf":
            pmid = c.find("PMID")
            if pmid is not None:
                pmids.append(pmid.text)
    return pmids


def get_pubmed_date_from_node(node):
    """
    PubMed date fields are messy. Use a custom algorithm
    to handle the date formats explicitly, and save the granularity
    supplied, which varies wildly.
    """
    y, m, d = None, None, None
    if node is None:
        return {"date": None, "granularity": None}

    medlinedate = node.find("MedlineDate")
    if medlinedate is not None:
        return get_pubmed_date_from_medline(medlinedate.text.strip())

    year = node.find("Year")
    if year is None or year.text == "":
        return {"date": None, "granularity": None}

    granularity = "y"
    assert year.text.isdigit(), year.text
    y = int(year.text)
    month = node.find("Month")
    if month is not None and month.text:
        granularity = "m"
        if month.text.isdigit():
            m = int(month.text)
            assert 1 <= m <= 12, "Month out of range: %s" % (month.text)
        else:
            assert month.text in month_mapper, month.text
            m = month_mapper[month.text]
    else:
        m = 1
    day = node.find("Day")
    if day is not None and day.text:
        granularity = "d"
        assert day.text.isdigit(), day.text
        d = int(day.text)
    else:
        d = 1

    assert y, node
    assert m, node
    assert d, node

    try:
        processed_date = datetime.date(y, m, d)
    except ValueError:
        logging.warning("Ignoring erroneous date: %s %s %s", y, m, d)
        processed_date = None

    return {"date": processed_date, "granularity": granularity}


def get_pubmed_date_from_medline(s):
    subpatterns = {
        "year": r"\d{4}",
        "month": r"\w{3}",
        "day": r"\d{1,2}",
        "season": r"\w{4,6}",
        "sep": " *[-/] *",
    }

    patterns = [
        # eg "1983 Sep 22-28"
        "({year}) ({month}) ({day}){sep}{day}",
        # eg "2007 Aug 9-Sep 12",
        "({year}) ({month}) ({day}){sep}{month} {day}",
        # eg "1984 Jul-Aug",
        "({year}) ({month}){sep}{month}",
        # eg "Winter 2019",
        "({season}) ({year})",
        # eg "2012",
        "({year})",
    ]

    for pattern in patterns:
        pattern = pattern.format(**subpatterns) + "$"
        match = re.match(pattern, s)
        if match:
            groups = match.groups()
            # Season is special case where year does not come first
            if groups[0] in season_mapper.keys():
                month = season_mapper[groups[0]]
                year = int(groups[1])
                day = 1
            else:
                year = int(groups[0])

                if len(groups) > 1:
                    month = month_mapper[groups[1]]
                else:
                    month = 1

                if len(groups) > 2:
                    day = int(groups[2])
                else:
                    day = 1

            granularity = {1: "y", 2: "m", 3: "d"}[len(groups)]

            return {
                "date": datetime.date(year, month, day),
                "granularity": granularity,
            }

    return {"date": None, "granularity": None}
