
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from transformers import PegasusTokenizer, PegasusForConditionalGeneration

MODEL_DIR = r"E:\WebScraping\models\financial-summarization-pegasus"

tokenizer = PegasusTokenizer.from_pretrained(
    MODEL_DIR,
    local_files_only=True
)

model = PegasusForConditionalGeneration.from_pretrained(
    MODEL_DIR,
    local_files_only=True
)

model.eval()
print("Local financial summarization model loaded!")