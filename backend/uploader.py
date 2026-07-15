import os
import sys
import hashlib
import time
import requests
from backend.config import API_KEY, BASE_URL
from backend import db

INPUT_DIR = "patents_5"

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}


# ---------- 1. helpers ----------
def read_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def file_hash(path: str) -> str:
    """Return SHA-256 hash of the file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------- 2. post API ----------
def upload(text, corpus="patentrag"):
    url = f"{BASE_URL}/process"

    payload = {
        "type": "text",
        "url": text
    }

    r = requests.post(url, headers=HEADERS, json=payload)

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

        try:
            print(f"\n[{i+1}/{len(files)}] Processing: {file}")

            # ----- content hash (dedup check) -----
            content_hash = file_hash(path)
            file_size = os.path.getsize(path)

            if db.is_uploaded(content_hash):
                print(f"⏭ Already uploaded, skipping")
                skip_count += 1
                continue

            text = read_txt(path)

            if not text.strip():
                print("⚠ Empty file, skipped")
                continue

            ok = upload(text)

            if ok:
                db.mark_uploaded(
                    file_name=file,
                    file_path=path,
                    file_hash=content_hash,
                    file_size=file_size,
                    status="success"
                )
                print("✅ Uploaded:", file)
                success_count += 1
            else:
                db.mark_uploaded(
                    file_name=file,
                    file_path=path,
                    file_hash=content_hash,
                    file_size=file_size,
                    status="failed",
                    error_message=f"HTTP error from API"
                )
                print("❌ Failed:", file)
                fail_count += 1

        except Exception as e:
            print("❌ Error:", file, str(e))
            # Still record the failure so it isn't retried blindly
            try:
                content_hash = file_hash(os.path.join(INPUT_DIR, file))
                file_size = os.path.getsize(os.path.join(INPUT_DIR, file))
                db.mark_uploaded(
                    file_name=file,
                    file_path=os.path.join(INPUT_DIR, file),
                    file_hash=content_hash,
                    file_size=file_size,
                    status="failed",
                    error_message=str(e)
                )
            except Exception:
                pass
            fail_count += 1

    print("\n===== DONE =====")
    print("Success:", success_count)
    print("Skipped (already uploaded):", skip_count)
    print("Failed:", fail_count)

    # Print summary from DB
    stats = db.get_stats()
    print(f"\n📊 DB Stats — Total attempts: {stats['total_attempts']}, "
          f"Successful: {stats['success_count']}, "
          f"Failed: {stats['fail_count']}, "
          f"Unique files: {stats['unique_files']}")


def show_uploaded():
    """Print a table of all successfully uploaded files."""
    rows = db.list_uploaded()
    if not rows:
        print("No uploaded files found.")
        return

    print(f"\n{'File Name':<40} {'Size':>10}  {'Uploaded At'}")
    print("-" * 70)
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["uploaded_at"]))
        size_kb = r["file_size"] / 1024
        print(f"{r['file_name']:<40} {size_kb:>8.1f} KB  {ts}")
    print(f"\nTotal: {len(rows)} file(s)")


def show_failed():
    """Print a table of all failed upload attempts."""
    rows = db.list_failed()
    if not rows:
        print("No failed uploads found.")
        return

    print(f"\n{'File Name':<40} {'Error':<50}  {'Attempted At'}")
    print("-" * 100)
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["uploaded_at"]))
        err = (r["error_message"] or "N/A")[:48]
        print(f"{r['file_name']:<40} {err:<50}  {ts}")
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
            print(f"Unique files:   {stats['unique_files']}")
            if stats['last_upload']:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats['last_upload']))
                print(f"Last upload:    {ts}")
        else:
            print(f"Usage: python3 uploader.py [--list | --failed | --stats]")
            sys.exit(1)
    else:
        main()
