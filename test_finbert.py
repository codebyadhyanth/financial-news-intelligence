
import os

# Tell Transformers not to use TensorFlow.
os.environ["USE_TF"] = "0"

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_PATH = r"E:\WebScraping\models\finbert"

print("Loading FinBERT tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

print("Loading FinBERT model...")
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_PATH
)

model.eval()

texts = [
    "ICICI Bank reports strong quarterly profit growth.",
    "HDFC Bank faces rising bad loans and declining profits.",
    "The bank announced its quarterly results today.",
]

print("\nRunning sentiment analysis...\n")

for text in texts:
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    )

    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.softmax(outputs.logits, dim=-1)[0]

    predicted_index = probabilities.argmax().item()
    predicted_label = model.config.id2label[predicted_index]

    print(f"Headline: {text}")
    print(f"Sentiment: {predicted_label}")

    for index, probability in enumerate(probabilities):
        label = model.config.id2label[index]
        print(f"  {label}: {probability.item():.4f}")

    print("-" * 50)
