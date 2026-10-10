from transformers import PegasusTokenizer, PegasusForConditionalGeneration
from bs4 import BeautifulSoup
import requests as re
from huggingface_hub import login
import os


HF_TOKEN = os.getenv("HF_TOKEN")
login(HF_TOKEN)

model_name = "human-centered-summarization/financial-summarization-pegasus"
MODEL_DIR = r"E:\WebScraping\models\financial-summarization-pegasus"

tokenizer = PegasusTokenizer.from_pretrained(MODEL_DIR, token=HF_TOKEN,local_files_only=True)
model = PegasusForConditionalGeneration.from_pretrained(MODEL_DIR, token=HF_TOKEN,local_files_only=True)

url = "https://www.moneycontrol.com/news/business/markets/sensex-up-550-pts-nifty-above-22-400-buying-in-it-shares-among-key-factors-behind-market-rise-14048237.html"
r = re.get(url)
soup = BeautifulSoup(r.content, 'html.parser')
paragraphs = soup.find_all('p')

text = [paragraph.text for paragraph in paragraphs]
words = ' '.join(text).split(' ')[:400]
ARTICLE = ' '.join(words)

input_ids = tokenizer(ARTICLE, return_tensors="pt")
output = model.generate(input_ids['input_ids'], max_length=150, num_beams=4, early_stopping=True)
summary = tokenizer.decode(output[0], skip_special_tokens=True)

print("Summary:")
print(summary)  