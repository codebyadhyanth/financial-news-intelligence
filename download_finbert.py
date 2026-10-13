
from huggingface_hub import snapshot_download

MODEL_NAME = "ProsusAI/finbert"
DOWNLOAD_DIR = r"E:\WebScraping\models\finbert"

print("Downloading FinBERT model...")

model_path = snapshot_download(
    repo_id=MODEL_NAME,
    local_dir=DOWNLOAD_DIR,
)

print("\nFinBERT downloaded successfully!")
print(f"Model location: {model_path}")
