import os
import json
from pathlib import Path
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("HASHTAG_API_KEY")
HASHTAG_BASE_URL = os.getenv("HASHTAG_BASE_URL", "https://kg-api.hashtag.ai").rstrip("/")

_HASHTAG_CONFIG_PATH = Path(__file__).with_name("hashtag_config.json")
with _HASHTAG_CONFIG_PATH.open(encoding="utf-8") as _config_file:
    _hashtag_config = json.load(_config_file)

HASHTAG_NAMESPACE = os.getenv("HASHTAG_NAMESPACE", _hashtag_config["namespace"]).strip()
CORPUS_NAME = os.getenv("HASHTAG_CORPUS_NAME", _hashtag_config["corpus_name"]).strip()
if not HASHTAG_NAMESPACE:
    raise ValueError("Hashtag namespace must not be empty")
if not CORPUS_NAME:
    raise ValueError("Hashtag corpus name must not be empty")

# Backwards-compatible alias for code that still refers to a Hashtag project.
HASH_TAG_PROJECT = CORPUS_NAME
BASE_URL = (
    f"{HASHTAG_BASE_URL}/{quote(HASHTAG_NAMESPACE, safe='')}"
    f"/{quote(CORPUS_NAME, safe='')}"
)

# Redis & Celery configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default
DEBUG_INVALID_REPORTS = os.getenv("DEBUG_INVALID_REPORTS", "false").lower() == "true"

if not API_KEY:
    raise ValueError("HASHTAG_API_KEY not found in environment variables")
