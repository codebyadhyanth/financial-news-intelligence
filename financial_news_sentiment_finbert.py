
from pathlib import Path

import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# =========================================================
# CONFIGURATION
# =========================================================

INPUT_CSV = Path(r"E:\WebScraping\data\news\financial_news.csv")

OUTPUT_CSV = Path(
    r"E:\WebScraping\data\output\financial_news_sentiment.csv"
)

MODEL_PATH = Path(r"E:\WebScraping\models\finbert")

DEVICE = "cpu"
BATCH_SIZE = 4

# FinBERT accepts at most 512 tokens per input.
MAX_LENGTH = 512
CHUNK_OVERLAP = 64

# =========================================================
# LOAD DATA
# =========================================================

if not INPUT_CSV.exists():
    raise FileNotFoundError(f"CSV not found: {INPUT_CSV}")

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"FinBERT model not found: {MODEL_PATH}")

df = pd.read_csv(INPUT_CSV)

required_columns = [
    "ticker",
    "headline",
    "published",
    "url",
    "article",
    "summary",
    "article_word_count",
]

missing = [c for c in required_columns if c not in df.columns]

if missing:
    raise ValueError(f"Missing CSV columns: {missing}")

print(f"Loaded {len(df)} rows from {INPUT_CSV.name}")

# =========================================================
# LOAD LOCAL FINBERT
# =========================================================

print("Loading FinBERT from local disk...")

tokenizer = AutoTokenizer.from_pretrained(
    str(MODEL_PATH),
    local_files_only=True,
)

model = AutoModelForSequenceClassification.from_pretrained(
    str(MODEL_PATH),
    local_files_only=True,
)

model.to(DEVICE)
model.eval()

# Map output IDs to sentiment names.
id2label = {
    int(k): str(v).lower()
    for k, v in model.config.id2label.items()
}

expected = {"positive", "negative", "neutral"}

# ProsusAI/finbert's standard label order.
if not expected.issubset(set(id2label.values())):
    if model.config.num_labels == 3:
        id2label = {
            0: "positive",
            1: "negative",
            2: "neutral",
        }
    else:
        raise ValueError(f"Unexpected FinBERT labels: {id2label}")

print(f"Model loaded. Labels: {id2label}")

# =========================================================
# SENTIMENT FUNCTION
# =========================================================

def analyze_sentiment(text):
    """
    Analyze a summary or a complete article.

    Long inputs are split into overlapping chunks.
    Chunk probabilities are averaged to produce one
    article-level sentiment result.
    """

    if pd.isna(text) or not str(text).strip():
        return {
            "label": None,
            "positive": None,
            "negative": None,
            "neutral": None,
            "score": None,
            "chunks": 0,
        }

    text = str(text).strip()

    # Generate overlapping chunks when the input is long.
    encoded = tokenizer(
        text,
        max_length=MAX_LENGTH,
        truncation=True,
        stride=CHUNK_OVERLAP,
        return_overflowing_tokens=True,
        padding=False,
        return_attention_mask=True,
    )

    chunks = [
        {
            "input_ids": ids,
            "attention_mask": mask,
        }
        for ids, mask in zip(
            encoded["input_ids"],
            encoded["attention_mask"],
        )
    ]

    chunk_probabilities = []

    with torch.inference_mode():
        for start in range(0, len(chunks), BATCH_SIZE):
            batch_chunks = chunks[start:start + BATCH_SIZE]

            batch = tokenizer.pad(
                batch_chunks,
                padding=True,
                return_tensors="pt",
            )

            batch = {
                key: value.to(DEVICE)
                for key, value in batch.items()
            }

            logits = model(**batch).logits
            probs = torch.softmax(logits, dim=-1)

            chunk_probabilities.extend(
                probs.cpu().tolist()
            )

    # Average probabilities across all article chunks.
    averaged = [
        sum(row[i] for row in chunk_probabilities)
        / len(chunk_probabilities)
        for i in range(model.config.num_labels)
    ]

    scores = {
        id2label[i]: float(averaged[i])
        for i in range(len(averaged))
    }

    return {
        "label": max(scores, key=scores.get),
        "positive": scores["positive"],
        "negative": scores["negative"],
        "neutral": scores["neutral"],
        "score": scores["positive"] - scores["negative"],
        "chunks": len(chunks),
    }


# =========================================================
# ANALYZE SUMMARIES AND FULL ARTICLES
# =========================================================

summary_results = []
article_results = []

total = len(df)

for position, row in enumerate(df.itertuples(index=False), start=1):
    # Access columns by name so their CSV order does not matter.
    data = row._asdict()

    print(
        f"[{position}/{total}] "
        f"{str(data['ticker'])} | "
        f"{str(data['headline'])[:65]}"
    )

    # Analysis 1: existing summary
    summary_results.append(
        analyze_sentiment(data["summary"])
    )

    # Analysis 2: complete article, chunk by chunk
    article_results.append(
        analyze_sentiment(data["article"])
    )

# =========================================================
# CREATE REFERENCE-ONLY OUTPUT
# =========================================================

# Keep identifiers and references only.
# Do NOT include article or summary text.
output = df[
    [
        "ticker",
        "headline",
        "published",
        "url",
        "article_word_count",
    ]
].copy()


def add_results(output_df, results, prefix):
    output_df[f"{prefix}_sentiment"] = [
        r["label"] for r in results
    ]

    output_df[f"{prefix}_positive_probability"] = [
        r["positive"] for r in results
    ]

    output_df[f"{prefix}_negative_probability"] = [
        r["negative"] for r in results
    ]

    output_df[f"{prefix}_neutral_probability"] = [
        r["neutral"] for r in results
    ]

    output_df[f"{prefix}_sentiment_score"] = [
        r["score"] for r in results
    ]

    output_df[f"{prefix}_chunks_analyzed"] = [
        r["chunks"] for r in results
    ]


add_results(output, summary_results, "summary")
add_results(output, article_results, "article")

output["model_name"] = "ProsusAI/finbert"

# Save references and sentiment results, not article bodies.
output.to_csv(
    OUTPUT_CSV,
    index=False,
    encoding="utf-8-sig",
)

print("\n" + "=" * 55)
print("FINBERT SENTIMENT PIPELINE COMPLETED")
print("=" * 55)
print(f"Total rows: {len(output)}")
print(f"Summary analyses: {sum(r['chunks'] > 0 for r in summary_results)}")
print(f"Article analyses: {sum(r['chunks'] > 0 for r in article_results)}")
print(f"Output: {OUTPUT_CSV}")
print("Full article and summary text were not written to the output.")
