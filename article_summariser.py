
import csv
import os
import time
import requests
import feedparser
import trafilatura
import torch

from urllib.parse import quote
from googlenewsdecoder import gnewsdecoder
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM


# ============================================================
# CONFIGURATION
# ============================================================

TICKERS = [
    "Nifty 50",
    "Sensex",
    "Reliance Industries",
    "HDFC Bank",
    "ICICI Bank",
]

MODEL_DIR = r"E:\WebScraping\models\financial-summarization-pegasus"
CSV_FILE = r"E:\WebScraping\financial_news.csv"

REQUEST_DELAY = 1.5
CHUNK_TOKENS = 500
SUMMARY_TOKENS = 150

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

CSV_FIELDS = [
    "ticker",
    "headline",
    "published",
    "url",
    "article",
    "summary",
    "article_word_count",
]


# ============================================================
# LOAD LOCAL PEGASUS MODEL
# ============================================================

def load_summarization_model():
    """Load the locally downloaded Pegasus model."""

    print("Loading local summarization model...")

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_DIR,
        local_files_only=True,
    )

    model = AutoModelForSeq2SeqLM.from_pretrained(
        MODEL_DIR,
        local_files_only=True,
    )

    model.to("cpu")
    model.eval()

    print("Summarization model loaded.")

    return tokenizer, model


# ============================================================
# CSV FUNCTIONS
# ============================================================

def initialize_csv():
    """Create the CSV and header if it does not exist."""

    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
            writer.writeheader()


def load_saved_urls():
    """Read URLs already saved, allowing the pipeline to resume."""

    saved_urls = set()

    if not os.path.exists(CSV_FILE):
        return saved_urls

    with open(CSV_FILE, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("url"):
                saved_urls.add(row["url"].strip())

    return saved_urls


def save_article_to_csv(record):
    """Append one completed article and summary immediately."""

    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writerow(record)

        # Push buffered data to disk immediately.
        file.flush()
        os.fsync(file.fileno())


# ============================================================
# FETCH GOOGLE NEWS RSS RESULTS
# ============================================================

def fetch_news_links(ticker):
    """Fetch all entries exposed by the RSS feed."""

    query = quote(f'"{ticker}"')
    rss_url = (
        f"https://news.google.com/rss/search?q={query}"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    articles = []
    seen_links = set()

    try:
        response = requests.get(
            rss_url,
            headers=HEADERS,
            timeout=25,
        )
        response.raise_for_status()

        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            print(f"[RSS ERROR] {ticker}: {feed.bozo_exception}")
            return []

        for entry in feed.entries:
            link = entry.get("link", "").strip()

            if not link or link in seen_links:
                continue

            seen_links.add(link)

            articles.append({
                "ticker": ticker,
                "headline": entry.get("title", "").strip(),
                "google_news_url": link,
                "published": entry.get("published", ""),
            })

    except requests.RequestException as error:
        print(f"[RSS ERROR] {ticker}: {error}")

    return articles


# ============================================================
# DECODE GOOGLE NEWS URL
# ============================================================

def decode_article_url(google_news_url):
    """Get the publisher URL from the Google News link."""

    try:
        result = gnewsdecoder(
            google_news_url,
            interval=1,
        )

        if result and result.get("success"):
            return result.get("decoded_url", "")

    except Exception as error:
        print(f"[DECODER ERROR] {error}")

    return ""


# ============================================================
# EXTRACT FULL AVAILABLE ARTICLE
# ============================================================

def extract_article_text(article_url):
    """Extract the readable article body from the publisher."""

    if not article_url:
        return ""

    try:
        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()

        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=True,
            favor_precision=False,
        )

        return text.strip() if text else ""

    except requests.RequestException as error:
        print(f"[ARTICLE ERROR] {article_url}: {error}")
        return ""


# ============================================================
# SUMMARIZATION HELPERS
# ============================================================

def summarize_chunk(text, tokenizer, model):
    """Summarize a single chunk that fits the model context."""

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=CHUNK_TOKENS,
    )

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=SUMMARY_TOKENS,
            num_beams=4,
            do_sample=False,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )

    return tokenizer.decode(
        output[0],
        skip_special_tokens=True,
    ).strip()


def summarize_article(article, tokenizer, model):
    """
    Summarize the whole available article in chunks.
    Each chunk's summary is combined into one summary string.
    """

    token_ids = tokenizer.encode(
        article,
        add_special_tokens=False,
    )

    if not token_ids:
        return ""

    chunk_summaries = []

    for start in range(0, len(token_ids), CHUNK_TOKENS):
        chunk_ids = token_ids[start:start + CHUNK_TOKENS]

        chunk_text = tokenizer.decode(
            chunk_ids,
            skip_special_tokens=True,
        ).strip()

        if not chunk_text:
            continue

        summary = summarize_chunk(
            chunk_text,
            tokenizer,
            model,
        )

        if summary:
            chunk_summaries.append(summary)

    # Store a single continuous summary in the CSV cell.
    return " ".join(chunk_summaries)


# ============================================================
# PROCESS ONE ARTICLE
# ============================================================

def process_article(
    news_item,
    tokenizer,
    model,
    saved_urls,
):
    """Decode, extract, summarize, and save one article."""

    headline = news_item["headline"]

    publisher_url = decode_article_url(
        news_item["google_news_url"]
    )

    if not publisher_url:
        print(f"[SKIP] Could not decode: {headline}")
        return

    # Skip URLs already saved in earlier runs.
    if publisher_url in saved_urls:
        print(f"[EXISTS] Already saved: {headline}")
        return

    time.sleep(REQUEST_DELAY)

    article_text = extract_article_text(publisher_url)

    if not article_text:
        print(f"[NO ARTICLE TEXT] {headline}")
        return

    print(f"  Extracted {len(article_text.split())} words.")
    print("  Summarizing...")

    try:
        summary = summarize_article(
            article_text,
            tokenizer,
            model,
        )
    except Exception as error:
        print(f"[SUMMARY ERROR] {headline}: {error}")
        return

    if not summary:
        print(f"[EMPTY SUMMARY] {headline}")
        return

    record = {
        "ticker": news_item["ticker"],
        "headline": headline,
        "published": news_item["published"],
        "url": publisher_url,
        "article": article_text,
        "summary": summary,
        "article_word_count": len(article_text.split()),
    }

    # Save immediately after this article is summarized.
    save_article_to_csv(record)
    saved_urls.add(publisher_url)

    print(f"  SAVED: {headline}")
    print(f"  Summary words: {len(summary.split())}")


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    initialize_csv()

    saved_urls = load_saved_urls()

    print(f"Previously saved articles: {len(saved_urls)}")

    tokenizer, model = load_summarization_model()

    # Deduplicate publisher URLs across ticker searches.
    seen_this_run = set(saved_urls)

    for ticker in TICKERS:
        print(f"\n{'=' * 60}")
        print(f"SEARCHING: {ticker}")
        print("=" * 60)

        news_items = fetch_news_links(ticker)

        print(f"RSS entries returned: {len(news_items)}")

        for index, news_item in enumerate(news_items, start=1):
            print(
                f"\n[{index}/{len(news_items)}] "
                f"{news_item['headline']}"
            )

            # Google URLs can differ for the same publisher article.
            # Decode in process_article before the final duplicate check.
            # Here we process each feed entry; saved URLs are checked again
            # against the actual publisher URL before extraction.

            try:
                process_article(
                    news_item,
                    tokenizer,
                    model,
                    saved_urls,
                )
            except KeyboardInterrupt:
                print("\nStopped by user. Saved CSV rows are preserved.")
                return

            time.sleep(REQUEST_DELAY)

    print("\nPipeline finished.")
    print(f"CSV file: {CSV_FILE}")
    print(f"Saved article URLs: {len(saved_urls)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user. Previously saved CSV rows are preserved.")
