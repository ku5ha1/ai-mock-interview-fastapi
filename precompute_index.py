import asyncio
import logging
from services.rag.doc_loader import load_docx_files
from services.rag.embedding import get_embedding
from services.rag.qdrant_client import client as qdrant_client
from qdrant_client.models import Distance, VectorParams, PointStruct
import os
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = "data/docs"
COLLECTION_NAME = "docs"
VECTOR_SIZE = 1536  # OpenAI ada-002
CHUNK_SIZE = 7500  # words
SUBCHUNK_SIZE = 3000  # words, for splitting oversized chunks

# Helper to split oversized chunks
def split_text(text, max_words=SUBCHUNK_SIZE):
    words = text.split()
    return [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]

async def main():
    try:
        logger.info(f"Loading documents from {DATA_DIR}")
        documents = load_docx_files(DATA_DIR, chunk_size=CHUNK_SIZE)

        # Further split oversized chunks
        final_chunks = []
        for doc in documents:
            if len(doc["text"].split()) > CHUNK_SIZE:
                subchunks = split_text(doc["text"], max_words=SUBCHUNK_SIZE)
                for idx, sub in enumerate(subchunks):
                    final_chunks.append({
                        "source": f"{doc['source']}-sub{idx}",
                        "text": sub
                    })
            else:
                final_chunks.append(doc)

        logger.info(f"Total chunks to index after splitting: {len(final_chunks)}")

        logger.info(f"Computing embeddings for {len(final_chunks)} chunks")
        embeddings = await asyncio.gather(*[get_embedding(doc["text"]) for doc in final_chunks])

        points = []
        for i, (doc, embedding) in enumerate(zip(final_chunks, embeddings)):
            if embedding:
                points.append(PointStruct(
                    id=i,
                    vector=embedding,
                    payload={
                        "source": doc["source"],
                        "text": doc["text"]
                    }
                ))
            else:
                logger.warning(f"Skipping chunk {doc['source']} due to missing embedding")

        logger.info(f"Upserting {len(points)} vectors to Qdrant collection '{COLLECTION_NAME}'")
        if not qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
            )
        else:
            qdrant_client.delete_collection(collection_name=COLLECTION_NAME)
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
            )
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info("RAG index precomputed and uploaded to Qdrant successfully")
    except Exception as e:
        logger.error(f"Error in precompute: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())