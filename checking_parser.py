
import feedparser
from urllib.parse import quote
import requests as re
from bs4 import BeautifulSoup

def search_for_stock_news_urls(ticker):
    query = f"Moneycontrol {ticker}"
    rss_url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    feed = feedparser.parse(rss_url)

    if feed.bozo and not feed.entries:
        print("RSS feed could not be parsed:", feed.bozo_exception)
        return []

    articles = []

    for entry in feed.entries:
        articles.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", "")
        })

    return articles

tickers = ["Nifty 50", "Sensex"]
for ticker in ["Nifty 50"]:
    articles = search_for_stock_news_urls(ticker)[:20]

    print(articles[0]["url"])
    r = re.get(articles[0]["url"])
    print(r.content)
    soup = BeautifulSoup(r.content, 'html.parser')
    paragraphs = soup.find_all('p')
    print(paragraphs)
    # for article in articles:
    #     print(article["title"])
    #     print(article["url"])
    #     print(article["published"])
    #     print("-" * 60)

    # print(f"\n{ticker}: {len(articles)} results")


