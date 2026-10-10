
import time
import requests
import feedparser
import trafilatura

from urllib.parse import quote
from googlenewsdecoder import gnewsdecoder


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

TICKERS = [
    "Nifty 50",
    "Sensex",
    "Reliance Industries",
    "HDFC Bank",
    "ICICI Bank",
]

REQUEST_DELAY = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}


# Final dictionary: one entry per unique article URL
NEWS_DATA = {}


# --------------------------------------------------
# 1. FETCH NEWS LINKS
# --------------------------------------------------

def fetch_news_links(ticker):
    """Fetch all entries exposed by the Google News RSS feed."""

    query = quote(f'"{ticker}"')
    rss_url = (
        f"https://news.google.com/rss/search?q={query}"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    articles = []
    seen_links = set()
    next_url = rss_url

    with requests.Session() as session:
        session.headers.update(HEADERS)

        while next_url:
            try:
                response = session.get(next_url, timeout=25)
                response.raise_for_status()

                feed = feedparser.parse(response.content)

                if feed.bozo and not feed.entries:
                    print(f"[RSS ERROR] {ticker}: {feed.bozo_exception}")
                    break

                for entry in feed.entries:
                    link = entry.get("link", "").strip()

                    if not link or link in seen_links:
                        continue

                    seen_links.add(link)

                    articles.append({
                        "headline": entry.get("title", "").strip(),
                        "google_news_url": link,
                        "published": entry.get("published", ""),
                        "ticker": ticker,
                    })

                # Follow pagination only if the feed exposes a next link.
                next_link = next(
                    (
                        item.get("href")
                        for item in feed.feed.get("links", [])
                        if item.get("rel") == "next"
                    ),
                    None,
                )

                next_url = next_link

            except requests.RequestException as error:
                print(f"[RSS ERROR] {ticker}: {error}")
                break

            time.sleep(REQUEST_DELAY)

    return articles


# --------------------------------------------------
# 2. DECODE GOOGLE NEWS URL
# --------------------------------------------------

def decode_article_url(google_news_url):
    """Resolve a Google News article link to its publisher URL."""

    try:
        result = gnewsdecoder(google_news_url, interval=1)

        if result and result.get("success"):
            return result.get("decoded_url", "")

    except Exception as error:
        print(f"[DECODER ERROR] {error}")

    return ""


# --------------------------------------------------
# 3. EXTRACT FULL AVAILABLE ARTICLE TEXT
# --------------------------------------------------

def extract_article_text(article_url):
    """Extract the main readable article text from a publisher page."""

    if not article_url:
        return ""

    try:
        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()

        article_text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=True,
            favor_precision=False,
        )

        return article_text.strip() if article_text else ""

    except requests.RequestException as error:
        print(f"[ARTICLE ERROR] {article_url}: {error}")
        return ""


# --------------------------------------------------
# 4. PROCESS ONE ARTICLE
# --------------------------------------------------

def process_article(article):
    """Decode a link and return one complete article record."""

    google_url = article["google_news_url"]
    publisher_url = decode_article_url(google_url)

    if not publisher_url:
        print(f"[SKIP] Could not decode: {article['headline']}")
        return None

    time.sleep(REQUEST_DELAY)

    full_text = extract_article_text(publisher_url)

    if not full_text:
        print(f"[NO TEXT] {article['headline']}")
        return None

    # Use the publisher URL as the unique dictionary key.
    return {
        "ticker": article["ticker"],
        "headline": article["headline"],
        "published": article["published"],
        "url": publisher_url,
        "article": full_text,
        "word_count": len(full_text.split()),
    }


# --------------------------------------------------
# 5. SCRAPE ALL TICKERS
# --------------------------------------------------

def scrape_all_news(tickers):
    """Collect all accessible, unique articles for each ticker."""

    news_data = {}

    for ticker in tickers:
        print(f"\n{'=' * 55}")
        print(f"Searching: {ticker}")
        print("=" * 55)

        links = fetch_news_links(ticker)
        print(f"RSS entries found: {len(links)}")

        for index, link in enumerate(links, start=1):
            print(f"[{index}/{len(links)}] {link['headline']}")

            record = process_article(link)

            if record is None:
                continue

            url_key = record["url"]

            # Deduplicate articles appearing under multiple tickers.
            if url_key in news_data:
                existing = news_data[url_key]

                if ticker not in existing["tickers"]:
                    existing["tickers"].append(ticker)

                continue

            record["tickers"] = [ticker]
            news_data[url_key] = record

            print(
                f"  Saved: {record['word_count']} words"
            )

    return news_data


# --------------------------------------------------
# 6. RUN
# --------------------------------------------------

if __name__ == "__main__":
    NEWS_DATA = scrape_all_news(TICKERS)

    print(f"\nTotal unique articles extracted: {len(NEWS_DATA)}")

    # Example: display one complete article
    if NEWS_DATA:
        first_article = next(iter(NEWS_DATA.values()))

        print("\nHEADLINE:")
        print(first_article["headline"])

        print("\nFULL ARTICLE:")
        print(first_article["article"])
