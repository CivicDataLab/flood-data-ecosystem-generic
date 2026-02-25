from google.cloud import storage
from pathlib import Path
import os

# ===== 1. CONFIGURATION =====
KEY_PATH = input("enter the path to your json key:  ")
BUCKET_NAME = input("enter the Bucket name :  ")
PREFIX = input("enter the folder prefix :  ")   # folder prefix used during export
DOWNLOAD_DIR = Path.cwd() / 'Sources' / 'NASADEM' / 'data'

# ===== 2. INITIALIZE CLIENT =====
print("🔐 Authenticating with Google Cloud Storage...")
client = storage.Client.from_service_account_json(KEY_PATH)
bucket = client.bucket(BUCKET_NAME)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"Connected to bucket: {BUCKET_NAME}")
print(f"Local download directory: {DOWNLOAD_DIR}\n")

# ===== 3. LIST FILES IN BUCKET =====
print("Listing files in bucket...")
blobs = list(bucket.list_blobs(prefix=PREFIX))

if not blobs:
    print("No files found in the bucket under prefix:", PREFIX)
    print("   → Check if Earth Engine export completed successfully.")
else:
    print(f"Found {len(blobs)} files to download:\n")
    for b in blobs:
        print(f" - {b.name} ({b.size/1024/1024:.2f} MB)")

# ===== 4. DOWNLOAD FILES =====
for blob in blobs:
    # Skip "folder" placeholders
    if blob.name.endswith("/"):
        continue

    filename = os.path.basename(blob.name)
    local_path = DOWNLOAD_DIR / filename

    print(f"\Downloading {filename} ...")
    blob.download_to_filename(local_path)
    print(f"Saved: {local_path}")

print("\n🎉 All files downloaded successfully!")
print(f"Local folder: {DOWNLOAD_DIR}")
