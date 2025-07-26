"""
RAG (Retrieval-Augmented Generation) API Routes

This module provides endpoints for testing and monitoring the RAG system,
including context retrieval and system status checks.
"""

from fastapi import APIRouter, HTTPException
from services.rag.retriever_factory import get_rag_retriever, get_retriever_status
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])

@router.post("/retrieve")
async def retrieve_context(question: str):
    """
    Test endpoint to retrieve context for a given question.
    Returns relevant context chunks from the vector database.
    """
    try:
        retriever = await get_rag_retriever()
        context = await retriever.retrieve_context(question)
        return {
            "question": question,
            "context": context,
            "context_count": len(context)
        }
    except Exception as e:
        logger.error(f"Error retrieving context for question='{question}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving context: {str(e)}")

@router.get("/status")
async def get_rag_status():
    """
    Get the status of the RAG system.
    Returns initialization status and configuration information.
    """
    return get_retriever_status()