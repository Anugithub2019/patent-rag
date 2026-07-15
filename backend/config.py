import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("HASHTAG_API_KEY")
BASE_URL = "https://kg-api.hashtag.ai/patentrag"

# Redis & Celery configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default

if not API_KEY:
    raise ValueError("HASHTAG_API_KEY not found in environment variables")