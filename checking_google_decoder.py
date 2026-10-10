
import feedparser
import requests
from urllib.parse import quote
from googlenewsdecoder import gnewsdecoder
import trafilatura


def search_for_stock_news_urls(ticker):
    query = f"Moneycontrol {ticker}"

    rss_url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    response = requests.get(rss_url, timeout=20)
    response.raise_for_status()

    feed = feedparser.parse(response.content)

    articles = []

    for entry in feed.entries:
        articles.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", "")
        })

    return articles


def extract_article_text(google_news_url):
    # 1. Decode Google News URL into the publisher's URL
    result = gnewsdecoder(google_news_url, interval=1)

    if not result or not result.get("success"):
        print("Could not decode Google News URL:", result)
        return None

    article_url = result["decoded_url"]
    print("\nPublisher URL:", article_url)

    # 2. Request the actual publisher page
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(
        article_url,
        headers=headers,
        timeout=25
    )

    print("HTTP status:", response.status_code)
    print("Final URL:", response.url)
    response.raise_for_status()

    # 3. Extract the main article text
    text = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=False
    )

    if text:
        return text

    print("No article text extracted.")
    print("The publisher may block scraping or load content dynamically.")
    return None


# Test with one ticker
ticker = "Nifty 50"
articles = search_for_stock_news_urls(ticker)

print(f"Found {len(articles)} news results.")

if articles:
    print("\nArticle title:", articles[0]["title"])

    article_text = extract_article_text(articles[0]["url"])

    if article_text:
        print("\n--- ARTICLE TEXT ---\n")
        print(article_text[:10000])
    else:
        print("Try another article from the results.")
else:
    print("No news results returned.")
