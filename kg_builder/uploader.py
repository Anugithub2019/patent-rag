import os
import sys
import json
import hashlib
import time
import requests
from urllib.parse import quote
from backend.config import API_KEY, HASHTAG_BASE_URL, HASHTAG_NAMESPACE, CORPUS_NAME
from kg_builder import db

with open(os.path.join(os.path.dirname(__file__), "uploader_config.json")) as f:
    _config = json.load(f)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = _config["input_dir"]
if not os.path.isabs(INPUT_DIR):
    INPUT_DIR = os.path.join(PROJECT_ROOT, INPUT_DIR)

CORPUS_DESTINATION = (
    f"{quote(HASHTAG_NAMESPACE, safe='')}/{quote(CORPUS_NAME, safe='')}"
)

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}


# ---------- 1. helpers ----------
def read_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def text_hash(text: str) -> str:
    """Return a SHA-256 hash of the exact UTF-8 text sent to Hashtag."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- 2. post API ----------
def upload(text, corpus=CORPUS_NAME, namespace=HASHTAG_NAMESPACE):
    namespace = namespace.strip()
    corpus = corpus.strip()
    if not namespace:
        raise ValueError("Namespace must not be empty")
    if not corpus:
        raise ValueError("Corpus name must not be empty")

    url = (
        f"{HASHTAG_BASE_URL}/{quote(namespace, safe='')}"
        f"/{quote(corpus, safe='')}/process"
    )

    payload = {
        "type": "text",
        "url": text
    }

    r = requests.post(url, headers=HEADERS, json=payload, timeout=300)

    if r.status_code != 200:
        print("❌ Upload failed:", r.status_code, r.text)
        return False

    return True


# ---------- 3. main ----------
def main():
    db.init_db()

    files = sorted(os.listdir(INPUT_DIR))

    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, file in enumerate(files):
        if not file.endswith(".txt"):
            continue

        path = os.path.join(INPUT_DIR, file)

        print(f"\n[{i+1}/{len(files)}] Processing: {file}")

        try:
            # Read once so the hash always describes the exact text being posted.
            text = read_txt(path)
            if not text.strip():
                print("⚠ Empty file, skipped")
                continue

            encoded_text = text.encode("utf-8")
            content_hash = text_hash(text)
            file_size = len(encoded_text)
            claim = db.claim_upload(
                file_name=file,
                file_path=path,
                file_hash=content_hash,
                file_size=file_size,
                corpus=CORPUS_DESTINATION,
            )
        except Exception as exc:
            print("❌ Could not prepare upload:", file, str(exc))
            fail_count += 1
            continue

        if not claim.acquired:
            if claim.reason == "already_uploaded":
                print("⏭ Already uploaded, skipping")
            else:
                print("⏭ Upload already in progress, skipping")
            skip_count += 1
            continue

        try:
            ok = upload(text)
        except Exception as exc:
            try:
                db.finish_upload(
                    claim.token,
                    status="failed",
                    error_message=str(exc),
                )
            except Exception as db_exc:
                print("❌ Could not record upload failure:", str(db_exc))
            print("❌ Upload error:", file, str(exc))
            fail_count += 1
            continue

        if not ok:
            try:
                db.finish_upload(
                    claim.token,
                    status="failed",
                    error_message="HTTP error from API",
                )
            except Exception as exc:
                print("❌ Could not record upload failure:", str(exc))
            print("❌ Failed:", file)
            fail_count += 1
            continue

        try:
            db.finish_upload(claim.token, status="success")
        except Exception as exc:
            # Keep the claim in processing state. A later run can recover it
            # after the lease expires without immediately duplicating the POST.
            print("❌ Uploaded but could not record completion:", file, str(exc))
            fail_count += 1
            continue

        print("✅ Uploaded:", file)
        success_count += 1

    print("\n===== DONE =====")
    print("Success:", success_count)
    print("Skipped (already uploaded):", skip_count)
    print("Failed:", fail_count)

    # Print summary from DB
    stats = db.get_stats(CORPUS_DESTINATION)
    print(f"\n📊 DB Stats — Total attempts: {stats['total_attempts']}, "
          f"Successful: {stats['success_count']}, "
          f"Failed: {stats['fail_count']}, "
          f"In progress: {stats['in_progress_count']}, "
          f"Abandoned: {stats['abandoned_count']}, "
          f"Unique files: {stats['unique_files']}")


def show_uploaded(corpus=None):
    """Print a table of all successfully uploaded files."""
    rows = db.list_uploaded(corpus)
    if not rows:
        print("No uploaded files found.")
        return

    print(f"\n{'File Name':<40} {'Size':>10}  {'Destination':<36} {'Uploaded At'}")
    print("-" * 108)
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["uploaded_at"]))
        size_kb = r["file_size"] / 1024
        print(f"{r['file_name']:<40} {size_kb:>8.1f} KB  {r['corpus']:<36} {ts}")
    print(f"\nTotal: {len(rows)} file(s)")


def show_failed(corpus=None):
    """Print a table of all failed upload attempts."""
    rows = db.list_failed(corpus)
    if not rows:
        print("No failed uploads found.")
        return

    print(f"\n{'File Name':<40} {'Destination':<36} {'Error':<50}  {'Attempted At'}")
    print("-" * 138)
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["uploaded_at"]))
        err = (r["error_message"] or "N/A")[:48]
        print(f"{r['file_name']:<40} {r['corpus']:<36} {err:<50}  {ts}")
    print(f"\nTotal: {len(rows)} failed attempt(s)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--list":
            db.init_db()
            show_uploaded()
        elif arg == "--failed":
            db.init_db()
            show_failed()
        elif arg == "--stats":
            db.init_db()
            stats = db.get_stats()
            print(f"Total attempts: {stats['total_attempts']}")
            print(f"Successful:     {stats['success_count']}")
            print(f"Failed:         {stats['fail_count']}")
            print(f"In progress:    {stats['in_progress_count']}")
            print(f"Abandoned:      {stats['abandoned_count']}")
            print(f"Unique files:   {stats['unique_files']}")
            if stats['last_upload']:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats['last_upload']))
                print(f"Last upload:    {ts}")
        else:
            print(f"Usage: python3 uploader.py [--list | --failed | --stats]")
            sys.exit(1)
    else:
        main()
