"""
Code Optimization API Routes

This module handles code optimization requests, providing improved code solutions
with explanations and performance enhancements.
"""

import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Body
from services.code_optimizer import generate_optimized_code, generate_optimized_code_with_summary
from models.schemas import CodeOptimizationRequest
from services.rag.retriever_factory import get_rag_retriever
from services.db import validate_user_id, save_user_ai_interaction

router = APIRouter(tags=["Code Optimization"])

# Utility to strip comments from code
_DEF_COMMENT_RE = re.compile(r"(^\s*#.*$|^\s*//.*$|/\*.*?\*/|'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\")", re.MULTILINE)
def strip_comments_from_code(code: str) -> str:
    # Remove block comments and docstrings
    code = re.sub(r"'''[\s\S]*?'''", '', code)
    code = re.sub(r'"""[\s\S]*?"""', '', code)
    # Remove /* ... */ comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # Remove single-line # and // comments
    code = re.sub(r'(^|\s)#.*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'(^|\s)//.*$', '', code, flags=re.MULTILINE)
    # Remove empty lines left by comment removal
    code = '\n'.join([line for line in code.splitlines() if line.strip()])
    return code

@router.post("/optimize-code")
async def optimize_code(request: CodeOptimizationRequest):
    """
    Optimize user's code with improvements and explanations.
    Uses RAG context to provide relevant optimization suggestions.
    Returns only the optimized code in the response, with all comments removed.
    Uses the 'o4-mini-2025-04-16' model for code optimization.
    """
    logger = logging.getLogger(__name__)
    # Validate user exists
    if not await validate_user_id(request.user_id):
        logger.error(f"User not found: user_id={request.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    try:
        # Get RAG context for relevant optimization suggestions
        retriever = await get_rag_retriever()
        rag_context = ""
        if retriever is not None:
            context_chunks = await retriever.retrieve_context(request.question)
            rag_context = "\n\n".join(context_chunks)
        
        # Generate optimized code with summary using the specified model
        result = await generate_optimized_code_with_summary(
            question=request.question,
            user_code=request.user_code,
            sample_input=request.sample_input,
            sample_output=request.sample_output,
            rag_context=rag_context,
            model="o4-mini-2025-04-16"
        )
        
        # Save interaction for analytics (non-blocking)
        try:
            await save_user_ai_interaction(
                user_id=request.user_id,
                endpoint="code_optimization",
                input_data=request.dict(),
                ai_response=result
            )
        except Exception as e:
            logger.error(f"Failed to save user-AI interaction for user_id={request.user_id}: {e}", exc_info=True)
            
        # Ensure only the optimized code is returned, and it is present
        optimized_code = result.get("optimized_code")
        if not optimized_code or not isinstance(optimized_code, str) or not optimized_code.strip():
            logger.error(f"No optimized_code returned from code optimizer for user_id={request.user_id}, question={request.question}. Full result: {result}")
            raise HTTPException(status_code=500, detail="No optimized code generated. Please try again or contact support.")
        # Strip all comments from the code
        code_no_comments = strip_comments_from_code(optimized_code)
        if not code_no_comments.strip():
            logger.error(f"Optimized code was entirely comments or empty after stripping for user_id={request.user_id}, question={request.question}. Original code: {optimized_code}")
            raise HTTPException(status_code=500, detail="Optimized code contained only comments or was empty.")
        return {"optimized_code": code_no_comments}
    except Exception as e:
        logger.error(f"Error optimizing code for user_id={request.user_id}, question={request.question}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error optimizing code: {str(e)}")