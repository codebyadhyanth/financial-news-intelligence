
"""
Nifty 50 + Sensex Recursive Financial News Crawler
==================================================

Output:
    E:/WebScraping/data/news/nifty50_sensex_deep_crawl.csv

Features:
    - Google News RSS search for Nifty 50 and Sensex
    - Official exchange, regulator, and financial-news seed sites
    - Recursive HTML link crawling
    - Relevant external-link discovery
    - PDF text extraction when accessible
    - Robots.txt checks
    - Domain and page limits to prevent infinite crawling
    - URL deduplication
    - Full extracted text without deliberate character truncation
    - Incremental CSV writes
    - Error logging in a separate CSV

Important:
    This is a bounded web crawler, not a guarantee that every page
    on the internet or every historical article will be retrieved.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
    urlencode,
    parse_qsl,
)
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from io import BytesIO


# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_DIR = Path(r"E:\WebScraping\data\news")

OUTPUT_CSV = OUTPUT_DIR / "nifty50_sensex_deep_crawl.csv"
ERROR_CSV = OUTPUT_DIR / "nifty50_sensex_crawler_errors.csv"

USER_AGENT = (
    "NiftySensexResearchCrawler/1.0 "
    "(research; contact: replace-with-your-email@example.com)"
)

REQUEST_TIMEOUT = 60 # Changed to 60 seconds to allow for slower responses from some servers
REQUEST_DELAY_SECONDS = 1.8 # Changed to 1.8 seconds to reduce the risk of being blocked by servers

MAX_PAGES_TOTAL = 3000
MAX_DEPTH = 3
MAX_PAGES_PER_DOMAIN = 80

MAX_RESPONSE_BYTES = 20 * 1024 * 1024  # 20 MB per response
MAX_PDF_PAGES = 500

# Only crawl pages that appear relevant to these markets.
MARKET_TERMS = [
    "nifty 50",
    "nifty50",
    "sensex",
    "bse sensex",
    "nifty index",
    "nifty futures",
    "nifty options",
    "sensex futures",
    "sensex index",
    "indian benchmark index",
    "indian stock market",
]

# Relevant financial context can help classify pages that mention
# the indices in less obvious ways.
CONTEXT_TERMS = [
    "stock market",
    "equity market",
    "share market",
    "market index",
    "stock exchange",
    "market closing",
    "market opening",
    "market rally",
    "market selloff",
    "market volatility",
    "market outlook",
    "market sentiment",
    "market breadth",
    "index futures",
    "index options",
    "corporate results",
    "market news",
]

CSV_FIELDS = [
    "record_id",
    "headline",
    "published",
    "source",
    "source_domain",
    "url",
    "canonical_url",
    "discovered_from",
    "crawl_depth",
    "content_type",
    "content_status",
    "matched_market",
    "article_text",
    "text_characters",
    "content_sha256",
    "fetched_at_utc",
]

ERROR_FIELDS = [
    "url",
    "source_domain",
    "depth",
    "error_type",
    "error_message",
    "logged_at_utc",
]


# ============================================================
# SOURCE SEEDS
# ============================================================

# These are discovery entry points, not guarantees of full access.
# Add more sites here as you validate their feeds and terms.
SEED_URLS = [
    # Official exchanges and regulators
    "https://www.nseindia.com/static/rss-feed",
    "https://www.nseindia.com/companies-listing/corporate-filings-application?id=eqCorpAnnouncementsNav",
    "https://www.nseindia.com/static/investor-relations/announcements",
    "https://www.bseindia.com/corporates.html",
    "https://www.bseindia.com/corporates/Comp_Resultsnew.aspx",
    "https://www.sebi.gov.in/rss.html",
    "https://www.sebi.gov.in/sebirss.xml",
    "https://www.rbi.org.in/Scripts/rss.aspx",
    "https://www.pib.gov.in/",
    "https://mospi.gov.in/",
    "https://finmin.gov.in/",
    "https://www.mcxindia.com/",

    # Indian financial news
    "https://www.moneycontrol.com/",
    "https://economictimes.indiatimes.com/markets",
    "https://www.business-standard.com/",
    "https://www.livemint.com/",
    "https://www.cnbctv18.com/",
    "https://www.financialexpress.com/",
    "https://www.thehindubusinessline.com/",
    "https://www.ndtvprofit.com/",
    "https://www.zeebiz.com/",
    "https://www.businesstoday.in/",
    "https://www.businessworld.in/",
    "https://www.outlookbusiness.com/",
    "https://www.dsij.in/",
    "https://www.informistmedia.com/",

    # International financial news
    "https://www.reuters.com/markets/",
    "https://www.reuters.com/world/india/",
    "https://www.bloomberg.com/markets",
    "https://www.cnbc.com/world/",
    "https://www.ft.com/markets",
    "https://www.wsj.com/news/markets",
    "https://finance.yahoo.com/",
    "https://www.marketwatch.com/",
    "https://www.investing.com/",
    "https://www.tradingview.com/news/",
    "https://www.fxstreet.com/",
    "https://www.forexlive.com/",
    "https://oilprice.com/",
    "https://www.kitco.com/",
    "https://www.eia.gov/",
    "https://www.federalreserve.gov/feeds/feeds.htm",
    "https://www.ecb.europa.eu/home/html/rss.en.html",
    "https://www.imf.org/en/News",
    "https://www.worldbank.org/en/news",
    "https://www.bls.gov/",
    "https://www.bea.gov/",
    "https://fred.stlouisfed.org/",
]

# Known source domains are eligible for internal crawling.
# Relevant outbound links can also be followed when discovered.
SEED_DOMAINS = {
    (urlparse(url).hostname or "").lower().removeprefix("www.")
    for url in SEED_URLS
    if urlparse(url).hostname
}

GOOGLE_NEWS_QUERIES = [
    '"Nifty 50" OR Nifty50',
    '"Sensex" OR "BSE Sensex"',
    '"Nifty 50" stock market India',
    '"Sensex" stock market India',
    '"Nifty 50" earnings OR results OR outlook',
    '"Sensex" earnings OR results OR outlook',
    '"Nifty 50" RBI OR inflation OR interest rates',
    '"Sensex" RBI OR inflation OR interest rates',
    '"Nifty 50" FII OR DII OR foreign investors',
    '"Sensex" FII OR DII OR foreign investors',
    '"Nifty 50" crude oil OR rupee OR dollar',
    '"Sensex" crude oil OR rupee OR dollar',
    '"Nifty 50" market closing OR market opening',
    '"Sensex" market closing OR market opening',
    '"Nifty 50" global markets OR Wall Street',
    '"Sensex" global markets OR Wall Street',
    '"Nifty 50" NSE announcement OR exchange filing',
    '"Sensex" BSE announcement OR exchange filing',
]


# ============================================================
# INITIALIZATION
# ============================================================

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml,"
        "application/rss+xml,application/pdf;q=0.9,*/*;q=0.5"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
})

visited_urls = set()
seen_content_hashes = set()
domain_page_counts = {}
robots_cache = {}
record_ids = set()

csv_file = None
csv_writer = None
error_file = None
error_writer = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def host_of(url):
    return (urlparse(url).hostname or "").lower()


def normalized_domain(url):
    return host_of(url).removeprefix("www.")


def canonicalize_url(url):
    """Remove fragments and common tracking parameters."""
    try:
        p = urlparse(url.strip())

        if p.scheme.lower() not in {"http", "https"}:
            return None

        if not p.hostname:
            return None

        if p.username or p.password:
            return None

        tracking_prefixes = ("utm_",)
        tracking_keys = {
            "gclid", "fbclid", "mc_cid", "mc_eid",
            "ref", "referrer", "cmpid",
        }

        kept = []
        for key, value in parse_qsl(
            p.query, keep_blank_values=True
        ):
            k = key.lower()
            if k in tracking_keys or any(
                k.startswith(prefix) for prefix in tracking_prefixes
            ):
                continue
            kept.append((key, value))

        path = re.sub(r"/{2,}", "/", p.path or "/")

        # Do not reorder query parameters: some sites depend on order.
        query = urlencode(kept, doseq=True)

        return urlunparse((
            p.scheme.lower(),
            p.netloc.lower(),
            path,
            "",
            query,
            "",
        ))

    except Exception:
        return None


def open_csv_files():
    global csv_file, csv_writer, error_file, error_writer

    output_exists = OUTPUT_CSV.exists() and OUTPUT_CSV.stat().st_size > 0
    csv_file = open(
        OUTPUT_CSV, "a", newline="", encoding="utf-8-sig"
    )
    csv_writer = csv.DictWriter(
        csv_file,
        fieldnames=CSV_FIELDS,
        extrasaction="ignore",
    )
    if not output_exists:
        csv_writer.writeheader()
        csv_file.flush()

    error_exists = ERROR_CSV.exists() and ERROR_CSV.stat().st_size > 0
    error_file = open(
        ERROR_CSV, "a", newline="", encoding="utf-8-sig"
    )
    error_writer = csv.DictWriter(
        error_file,
        fieldnames=ERROR_FIELDS,
        extrasaction="ignore",
    )
    if not error_exists:
        error_writer.writeheader()
        error_file.flush()


def log_error(url, depth, error_type, error_message):
    try:
        error_writer.writerow({
            "url": url,
            "source_domain": normalized_domain(url),
            "depth": depth,
            "error_type": str(error_type),
            "error_message": str(error_message),
            "logged_at_utc": utc_now(),
        })
        error_file.flush()
    except Exception:
        logging.exception("Could not write error log")


# ============================================================
# ROBOTS.TXT
# ============================================================

def robots_allowed(url):
    """
    Respect robots.txt where it can be fetched and parsed.
    If robots.txt cannot be fetched, this conservative implementation
    skips the page rather than assuming crawling is allowed.
    """
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    robots_url = origin + "/robots.txt"

    if robots_url not in robots_cache:
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            response = session.get(
                robots_url, timeout=REQUEST_TIMEOUT
            )
            time.sleep(REQUEST_DELAY_SECONDS)

            if response.status_code == 404:
                # A confirmed missing robots.txt means no rules file.
                parser.parse([])
                robots_cache[robots_url] = parser
            elif response.status_code == 200:
                parser.parse(response.text.splitlines())
                robots_cache[robots_url] = parser
            else:
                robots_cache[robots_url] = None

        except requests.RequestException:
            robots_cache[robots_url] = None

    parser = robots_cache[robots_url]
    if parser is None:
        return False

    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return False


# ============================================================
# MARKET RELEVANCE
# ============================================================

def matched_markets(text):
    text = (text or "").lower()
    matches = []

    if any(term in text for term in [
        "nifty 50", "nifty50", "nifty index",
        "nifty futures", "nifty options",
    ]):
        matches.append("Nifty 50")

    if any(term in text for term in [
        "sensex", "bse sensex", "sensex futures",
    ]):
        matches.append("Sensex")

    return matches


def is_relevant(text, url=""):
    """
    Strictly retain pages mentioning Nifty 50 or Sensex.
    A link is considered worth following if its anchor/URL mentions
    a target market, or if the discovered page itself is relevant.
    """
    combined = f"{text or ''} {url or ''}".lower()

    if any(term in combined for term in MARKET_TERMS):
        return True

    return False


def is_relevant_link(anchor_text, url):
    combined = f"{anchor_text or ''} {url or ''}".lower()

    if any(term in combined for term in MARKET_TERMS):
        return True

    # These terms allow discovery of links that may contain market
    # coverage even if the URL does not literally say Nifty or Sensex.
    # The destination page still must pass is_relevant() to be saved.
    return (
        any(term in combined for term in CONTEXT_TERMS)
        and any(
            word in combined
            for word in [
                "india", "indian", "market", "stock", "index",
                "nse", "bse", "equity", "finance",
            ]
        )
    )


# ============================================================
# FETCHING AND TEXT EXTRACTION
# ============================================================

def fetch_url(url):
    """
    Download one response. Enforces a response-size ceiling so that
    one huge file cannot consume unlimited memory.
    """
    with session.get(
        url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
        stream=True,
    ) as response:
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).split(";")[0].strip().lower()

        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > MAX_RESPONSE_BYTES:
                    raise ValueError(
                        f"Response exceeds {MAX_RESPONSE_BYTES} bytes"
                    )
            except ValueError as exc:
                if "exceeds" in str(exc):
                    raise

        chunks = []
        total = 0

        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue

            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"Response exceeded {MAX_RESPONSE_BYTES} bytes"
                )

            chunks.append(chunk)

        return (
            response.url,
            content_type,
            b"".join(chunks),
            response.status_code,
        )


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements but retain the rest of the page text.
    for element in soup([
        "script", "style", "noscript", "svg", "canvas",
    ]):
        element.decompose()

    title = ""
    if soup.title:
        title = soup.title.get_text(" ", strip=True)

    # Prefer article/main content when present, but fall back to full
    # visible-page text if those semantic containers are unavailable.
    content_node = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )

    text = content_node.get_text(separator="\n", strip=True)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text).strip()

    links = []
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()

        if not href:
            continue

        absolute = canonicalize_url(urljoin("", href))
        # The actual base URL is applied later in crawl_page().
        links.append((tag.get_text(" ", strip=True), href))

    canonical_link = soup.find(
        "link", rel=lambda value: value and "canonical" in value
    )
    canonical_url = (
        canonical_link.get("href", "").strip()
        if canonical_link else ""
    )

    published = ""
    for attr, key in [
        ("property", "article:published_time"),
        ("name", "datePublished"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
        ("property", "og:updated_time"),
    ]:
        tag = soup.find("meta", attrs={attr: key})
        if tag and tag.get("content"):
            published = tag["content"].strip()
            break

    return title, text, links, canonical_url, published


def pdf_to_text(data):
    reader = PdfReader(BytesIO(data))
    texts = []

    page_count = min(len(reader.pages), MAX_PDF_PAGES)

    for index in range(page_count):
        page_text = reader.pages[index].extract_text() or ""
        texts.append(page_text)

    text = "\n\n".join(texts).strip()

    status = "success"
    if len(reader.pages) > MAX_PDF_PAGES:
        status = "partial_pdf_page_limit"

    if not text:
        status = "pdf_no_extractable_text"

    return text, status


def extract_rss_items(data, feed_url):
    feed = feedparser.parse(data)
    rows = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = canonicalize_url(entry.get("link", ""))

        if not link:
            continue

        summary_html = entry.get("summary", "")
        summary_text = BeautifulSoup(
            summary_html, "html.parser"
        ).get_text(" ", strip=True)

        published = (
            entry.get("published", "")
            or entry.get("updated", "")
        )

        rows.append({
            "headline": title,
            "published": published,
            "url": link,
            "source": feed.feed.get("title", ""),
            "source_domain": normalized_domain(link),
            "discovered_from": feed_url,
            "article_text": summary_text,
            "content_type": "rss",
            "content_status": "rss_summary_only",
            "matched_market": ", ".join(
                matched_markets(title + " " + summary_text)
            ),
        })

    return rows


# ============================================================
# RECORD STORAGE AND DEDUPLICATION
# ============================================================

def record_id_for(url, text):
    raw = (url + "\n" + text).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def write_record(row):
    article_text = row.get("article_text", "") or ""
    url = row.get("url", "") or ""
    headline = row.get("headline", "") or ""

    content_hash = hashlib.sha256(
        article_text.encode("utf-8", errors="replace")
    ).hexdigest()

    record_id = record_id_for(url, article_text)

    # Deduplicate identical URLs/records and identical text bodies.
    if record_id in record_ids:
        return False

    # Empty bodies should not cause all empty pages to collapse together.
    if article_text.strip() and content_hash in seen_content_hashes:
        return False

    record_ids.add(record_id)
    if article_text.strip():
        seen_content_hashes.add(content_hash)

    csv_writer.writerow({
        "record_id": record_id,
        "headline": headline,
        "published": row.get("published", ""),
        "source": row.get("source", ""),
        "source_domain": row.get(
            "source_domain", normalized_domain(url)
        ),
        "url": url,
        "canonical_url": row.get("canonical_url", ""),
        "discovered_from": row.get("discovered_from", ""),
        "crawl_depth": row.get("crawl_depth", 0),
        "content_type": row.get("content_type", ""),
        "content_status": row.get("content_status", ""),
        "matched_market": row.get("matched_market", ""),
        "article_text": article_text,
        "text_characters": len(article_text),
        "content_sha256": content_hash,
        "fetched_at_utc": utc_now(),
    })

    csv_file.flush()
    return True


# ============================================================
# GOOGLE NEWS RSS DISCOVERY
# ============================================================

def discover_google_news():
    logging.info("Starting Google News RSS discovery")

    for query in GOOGLE_NEWS_QUERIES:
        params = {
            "q": query,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }

        rss_url = (
            "https://news.google.com/rss/search?"
            + urlencode(params)
        )

        try:
            response = session.get(
                rss_url, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()

            for item in extract_rss_items(
                response.content, rss_url
            ):
                # Store RSS metadata/summary as a fallback. The article
                # page may later be fetched separately by the crawler.
                if is_relevant(
                    item["headline"] + " " + item["article_text"],
                    item["url"],
                ):
                    write_record({
                        **item,
                        "crawl_depth": 0,
                    })

                enqueue_url(
                    item["url"],
                    depth=0,
                    parent=rss_url,
                )

            time.sleep(REQUEST_DELAY_SECONDS)

        except Exception as exc:
            log_error(
                rss_url, 0, type(exc).__name__, str(exc)
            )
            logging.warning(
                "Google News query failed: %s | %s", query, exc
            )


# ============================================================
# CRAWLER QUEUE
# ============================================================

crawl_queue = deque()


def enqueue_url(url, depth, parent=""):
    url = canonicalize_url(url)
    if not url:
        return

    if url in visited_urls:
        return

    if depth > MAX_DEPTH:
        return

    crawl_queue.append((url, depth, parent))


def can_crawl_domain(url):
    domain = normalized_domain(url)
    return domain_page_counts.get(domain, 0) < MAX_PAGES_PER_DOMAIN


def save_and_follow_page(url, depth, parent):
    final_url, content_type, data, status_code = fetch_url(url)

    final_url = canonicalize_url(final_url) or url

    if "pdf" in content_type or final_url.lower().endswith(".pdf"):
        text, extraction_status = pdf_to_text(data)

        if is_relevant(text, final_url):
            write_record({
                "headline": Path(urlparse(final_url).path).name,
                "published": "",
                "source": normalized_domain(final_url),
                "source_domain": normalized_domain(final_url),
                "url": final_url,
                "canonical_url": final_url,
                "discovered_from": parent,
                "crawl_depth": depth,
                "content_type": "application/pdf",
                "content_status": extraction_status,
                "matched_market": ", ".join(matched_markets(text)),
                "article_text": text,
            })
        return

    if (
        "html" not in content_type
        and "xml" not in content_type
        and content_type not in ("", "text/plain")
    ):
        return

    # RSS/XML feeds may appear as links on source pages.
    if "xml" in content_type or "rss" in content_type:
        for item in extract_rss_items(data, final_url):
            if is_relevant(
                item["headline"] + " " + item["article_text"],
                item["url"],
            ):
                write_record({
                    **item,
                    "crawl_depth": depth,
                })

            enqueue_url(
                item["url"],
                depth=depth + 1,
                parent=final_url,
            )
        return

    html = data.decode("utf-8", errors="replace")

    title, text, links, canonical_url, published = html_to_text(html)

    page_is_relevant = is_relevant(
        title + "\n" + text,
        final_url,
    )

    if page_is_relevant:
        write_record({
            "headline": title,
            "published": published,
            "source": normalized_domain(final_url),
            "source_domain": normalized_domain(final_url),
            "url": final_url,
            "canonical_url": (
                canonicalize_url(urljoin(final_url, canonical_url))
                if canonical_url else final_url
            ),
            "discovered_from": parent,
            "crawl_depth": depth,
            "content_type": content_type or "text/html",
            "content_status": (
                "success" if text else "empty_extracted_text"
            ),
            "matched_market": ", ".join(
                matched_markets(title + "\n" + text)
            ),
            "article_text": text,
        })

    # Follow relevant links. Internal links are considered even when
    # the current page itself is not relevant, which helps discover
    # articles from source landing pages.
    for anchor_text, href in links:
        absolute_url = canonicalize_url(urljoin(final_url, href))
        if not absolute_url:
            continue

        dest_domain = normalized_domain(absolute_url)
        source_domain = normalized_domain(final_url)

        same_domain = dest_domain == source_domain
        known_source_domain = dest_domain in SEED_DOMAINS

        if same_domain:
            # Crawl links from the current source, but the target page
            # must still pass the Nifty/Sensex relevance filter to save.
            enqueue_url(
                absolute_url,
                depth=depth + 1,
                parent=final_url,
            )

        elif known_source_domain and is_relevant_link(
            anchor_text, absolute_url
        ):
            enqueue_url(
                absolute_url,
                depth=depth + 1,
                parent=final_url,
            )

        elif is_relevant_link(anchor_text, absolute_url):
            # Relevant outbound links may point to a new publisher,
            # official filing, PDF, or source not in the initial list.
            enqueue_url(
                absolute_url,
                depth=depth + 1,
                parent=final_url,
            )


def crawl():
    total_processed = 0

    while crawl_queue and total_processed < MAX_PAGES_TOTAL:
        url, depth, parent = crawl_queue.popleft()

        if url in visited_urls:
            continue

        if depth > MAX_DEPTH:
            continue

        if not can_crawl_domain(url):
            continue

        visited_urls.add(url)

        if not robots_allowed(url):
            logging.info("Skipped by robots/policy: %s", url)
            log_error(
                url, depth, "RobotsDisallowed",
                "robots.txt disallowed crawling or could not be verified",
            )
            continue

        try:
            logging.info(
                "[%s/%s] depth=%s %s",
                total_processed + 1,
                MAX_PAGES_TOTAL,
                depth,
                url,
            )

            save_and_follow_page(url, depth, parent)

            domain = normalized_domain(url)
            domain_page_counts[domain] = (
                domain_page_counts.get(domain, 0) + 1
            )

            total_processed += 1

        except Exception as exc:
            log_error(
                url, depth, type(exc).__name__, str(exc)
            )
            logging.warning("Failed: %s | %s", url, exc)

        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

    logging.info("Crawler stopped.")
    logging.info("Pages processed: %s", total_processed)
    logging.info("URLs visited: %s", len(visited_urls))
    logging.info("Remaining queued URLs: %s", len(crawl_queue))
    logging.info("Output CSV: %s", OUTPUT_CSV)
    logging.info("Error CSV: %s", ERROR_CSV)

    if crawl_queue:
        logging.warning(
            "Crawl stopped due to configured limits. "
            "The queue still contains URLs; this was not an "
            "exhaustive crawl."
        )


# ============================================================
# MAIN
# ============================================================

def main():
    # Raise Python's CSV field limit to accommodate long article text.
    # Windows builds can have different C long limits, so fall back
    # gradually instead of failing during startup.
    csv_limit = sys_maxsize = 2**31 - 1
    while True:
        try:
            csv.field_size_limit(csv_limit)
            break
        except OverflowError:
            csv_limit //= 10

    open_csv_files()

    try:
        # Add seed pages first.
        for seed_url in SEED_URLS:
            enqueue_url(seed_url, depth=0, parent="SEED")

        # RSS discovery can add many direct article URLs to the queue.
        discover_google_news()

        # Crawl recursively until the queue is exhausted or limits hit.
        crawl()

    finally:
        if csv_file:
            csv_file.close()
        if error_file:
            error_file.close()


if __name__ == "__main__":
    import sys
    main()
