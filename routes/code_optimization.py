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

# Improved comment stripping that preserves actual code
def strip_comments_from_code(code: str) -> str:
    """
    Strip comments from code while preserving actual executable code.
    More conservative approach to avoid removing all content.
    """
    if not code or not isinstance(code, str):
        return ""
    
    # Remove docstrings (triple quotes)
    code = re.sub(r"'''[\s\S]*?'''", '', code)
    code = re.sub(r'"""[\s\S]*?"""', '', code)
    
    # Remove /* ... */ comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Remove single-line comments (# and //) but be more careful
    lines = code.splitlines()
    cleaned_lines = []
    
    for line in lines:
        stripped_line = line.strip()
        # Skip empty lines
        if not stripped_line:
            continue
        # Skip lines that are only comments
        if stripped_line.startswith('#') or stripped_line.startswith('//'):
            continue
        # For lines with inline comments, keep the code part
        if '#' in line:
            # Find the first # that's not in a string
            parts = line.split('#')
            if parts[0].strip():  # If there's code before the comment
                cleaned_lines.append(parts[0].rstrip())
        elif '//' in line:
            # Find the first // that's not in a string
            parts = line.split('//')
            if parts[0].strip():  # If there's code before the comment
                cleaned_lines.append(parts[0].rstrip())
        else:
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines)
    
    # If we ended up with no content, return the original code
    if not result.strip():
        logger.warning("Comment stripping removed all content, returning original code")
        return code
    
    return result

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
        
        # Enhanced validation of optimized code
        optimized_code = result.get("optimized_code")
        
        # Check if optimized_code exists and is valid
        if not optimized_code:
            logger.error(f"No optimized_code field in result for user_id={request.user_id}, question={request.question}. Full result: {result}")
            raise HTTPException(status_code=500, detail="No optimized code generated. Please try again.")
        
        if not isinstance(optimized_code, str):
            logger.error(f"optimized_code is not a string for user_id={request.user_id}. Type: {type(optimized_code)}, Value: {optimized_code}")
            raise HTTPException(status_code=500, detail="Invalid optimized code format. Please try again.")
        
        if not optimized_code.strip():
            logger.error(f"optimized_code is empty for user_id={request.user_id}, question={request.question}")
            raise HTTPException(status_code=500, detail="Generated code is empty. Please try again.")
        
        # Strip comments from the code
        code_no_comments = strip_comments_from_code(optimized_code)
        
        # Enhanced validation after comment stripping
        if not code_no_comments.strip():
            logger.error(f"Code became empty after comment stripping for user_id={request.user_id}. Original: {optimized_code[:200]}...")
            # Return the original code if stripping removed everything
            return {"optimized_code": request.user_code}
        
        # Log success for debugging
        logger.info(f"Successfully optimized code for user_id={request.user_id}. Original length: {len(request.user_code)}, Optimized length: {len(code_no_comments)}")
        
        return {"optimized_code": code_no_comments}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing code for user_id={request.user_id}, question={request.question}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error optimizing code: {str(e)}")