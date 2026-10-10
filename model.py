
import os
from huggingface_hub import snapshot_download

# Your project folder
MODEL_DIR = r"E:\WebScraping\models\financial-summarization-pegasus"

# Create the folder if it doesn't exist
os.makedirs(MODEL_DIR, exist_ok=True)

# Token is optional for public repositories
HF_TOKEN = os.getenv("HF_TOKEN")

print("Downloading Pegasus model files...")
print("Destination:", MODEL_DIR)

path = snapshot_download(
    repo_id="human-centered-summarization/financial-summarization-pegasus",
    local_dir=MODEL_DIR,
    token=HF_TOKEN if HF_TOKEN else None,
    max_workers=2
)

print("\nDownload complete!")
print("Model location:", path)
