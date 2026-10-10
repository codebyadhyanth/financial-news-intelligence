from transformers import PegasusTokenizer, PegasusForConditionalGeneration
from bs4 import BeautifulSoup
import requests as re


ticker = ["Nifty 50", "Sensex", "BSE", "NSE", "Stock Market", "Share Market", "Equity Market","Derivatives", "Nifty 50 Futures", "Nifty 50 Options","Sensex Futures", "Sensex Options"]

MODEL_DIR = r"E:\WebScraping\models\financial-summarization-pegasus"

tokenizer = PegasusTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
model = PegasusForConditionalGeneration.from_pretrained(MODEL_DIR, local_files_only=True)


def search_for_stock_news_urls(ticker):
    search_url = "https://www.google.com/search?q=moneycontrol+{}&tbm=nws".format(ticker)
    r = re.get(search_url)
    soup = BeautifulSoup(r.content, 'html.parser')
    atags = soup.find_all('a')
    hrefs = [links['href'] for links in atags ]
    return hrefs

text = [paragraph.text for paragraph in paragraphs]
words = ' '.join(text).split(' ')[:400]
ARTICLE = ' '.join(words)

input_ids = tokenizer(ARTICLE, return_tensors="pt")
output = model.generate(input_ids['input_ids'], max_length=150, num_beams=4, early_stopping=True)
summary = tokenizer.decode(output[0], skip_special_tokens=True)

print("Summary:")
print(summary)  