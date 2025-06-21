import os
from qdrant_client import QdrantClient

QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")

if not QDRANT_URL:
    raise ValueError("QDRANT_URL must be set in environment variables.")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)