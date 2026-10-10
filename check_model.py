
import json
import os
from transformers import __version__

MODEL_DIR = r"E:\WebScraping\models\financial-summarization-pegasus"

print("Transformers version:", __version__)

with open(os.path.join(MODEL_DIR, "config.json"), "r", encoding="utf-8") as f:
    config = json.load(f)

for key in [
    "model_type",
    "architectures",
    "transformers_version",
    "max_position_embeddings",
    "d_model",
    "vocab_size"
]:
    print(f"{key}: {config.get(key)}")
