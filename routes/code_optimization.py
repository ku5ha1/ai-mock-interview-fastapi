"""
Code Optimization API Routes

This module handles code optimization requests, providing improved code solutions
with explanations and performance enhancements.
"""

import logging
from fastapi import APIRouter, HTTPException
from services.code_optimizer import generate_optimized_code
from models.schemas import CodeOptimizationRequest
from services.db import validate_user_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Code Optimization"])



def strip_comments_from_code(code: str) -> str:
    """
    Simple comment stripping that preserves code structure.
    """
    if not code or not isinstance(code, str):
        return code
    
    lines = code.splitlines()
    cleaned_lines = []
    
    for line in lines:
        stripped_line = line.strip()
        
        # Skip empty lines and comment-only lines
        if not stripped_line or stripped_line.startswith('#'):
            continue
            
        # Keep lines with actual code
        cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines)
    return result if result.strip() else code





@router.post("/optimize-code")
async def optimize_code(request: CodeOptimizationRequest):
    """
    Optimize user code using AI.
    Returns the optimized code with basic validation.
    """
    
    try:
        # Validate user exists
        if not await validate_user_id(request.user_id):
            logger.error(f"User not found: user_id={request.user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        
        # Generate optimized code
        result = await generate_optimized_code(
            question=request.question,
            description=request.description,
            user_code=request.user_code,
            sample_input=request.sample_input,
            sample_output=request.sample_output,
            model="gpt-5-mini-2025-08-07"
        )
        
        # Get the optimized code
        optimized_code = result.get("optimized_code", "")
        
        # Basic validation
        if not optimized_code or not isinstance(optimized_code, str):
            return {
                "optimized_code": request.user_code,
                "optimization_note": "Failed to generate optimized code. Original code returned."
            }
        
        # Strip comments
        code_no_comments = strip_comments_from_code(optimized_code)
        
        # Calculate basic metrics
        original_length = len(request.user_code)
        optimized_length = len(code_no_comments)
        reduction_percentage = ((original_length - optimized_length) / original_length) * 100 if original_length > 0 else 0
        
        optimization_note = f"Code optimized successfully. Reduced from {original_length} to {optimized_length} characters ({reduction_percentage:.1f}% reduction)."
        
        return {
            "optimized_code": code_no_comments,
            "optimization_note": optimization_note
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Code optimization error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Code optimization failed. Please try again.")

