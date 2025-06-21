import os
import logging
from typing import Optional
from services.rag.retriever import RAGRetriever

logger = logging.getLogger(__name__)

# Global retriever instance
_rag_retriever = None

async def get_rag_retriever(force_rebuild: bool = False) -> RAGRetriever:
    """
    Get or create a Qdrant-based RAG retriever instance
    """
    global _rag_retriever
    if _rag_retriever is not None and not force_rebuild:
        logger.info("Returning existing RAG retriever instance")
        return _rag_retriever
    try:
        logger.info("Initializing Qdrant-based RAG retriever...")
        _rag_retriever = RAGRetriever(collection_name="docs")
        logger.info("Qdrant-based RAG retriever initialized successfully")
        return _rag_retriever
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant-based RAG retriever: {str(e)}")
        raise

def get_retriever():
    if _rag_retriever is None:
        raise RuntimeError("RAGRetriever not initialized. Call get_rag_retriever() first.")
    return _rag_retriever

def get_retriever_status() -> dict:
    """
    Get the current status of the RAG retriever
    """
    global _rag_retriever
    if _rag_retriever is None:
        return {
            "initialized": False,
            "message": "RAG retriever not initialized"
        }
    return {
        "initialized": True,
        "message": "Qdrant-based RAG retriever ready"
    }

async def rebuild_rag_retriever() -> RAGRetriever:
    """
    Force rebuild the RAG retriever
    """
    logger.info("Force rebuilding Qdrant-based RAG retriever...")
    return await get_rag_retriever(force_rebuild=True)