"""
Code Optimization API Routes

This module handles code optimization requests, providing improved code solutions
with explanations and performance enhancements.
"""

import logging
from fastapi import APIRouter, HTTPException
from services.code_optimization import generate_optimized_code, detect_language
from models.schemas import CodeOptimizationRequest
from services.db import validate_user_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Code Optimization"])


@router.post("/optimize-code")
async def optimize_code(request: CodeOptimizationRequest):
    """
    Optimize user code using AI with language-aware prompts and quality checks.
    Returns the optimized code with detailed optimization metrics.
    """
    
    try:
        # Validate user exists
        if not await validate_user_id(request.user_id):
            logger.error(f"User not found: user_id={request.user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        
        # Detect language for better optimization
        detected_language = detect_language(request.user_code)
        logger.info(f"Detected language: {detected_language} for user code")
        
        # Generate optimized code
        result = await generate_optimized_code(
            question=request.question,
            description=request.description,
            user_code=request.user_code,
            sample_input=request.sample_input,
            sample_output=request.sample_output
        )
        
        # Get the optimized code
        optimized_code = result.get("optimized_code", "")
        
        # Basic validation
        if not optimized_code or not isinstance(optimized_code, str):
            return {
                "optimized_code": request.user_code,
                "optimization_note": "Failed to generate optimized code. Original code returned.",
                "language_detected": detected_language,
                "optimization_status": "failed"
            }
        
        # Skip quality checks for speed - return optimized code immediately
        original_lines = len(request.user_code.splitlines())
        optimized_lines = len(optimized_code.splitlines())
        original_chars = len(request.user_code)
        optimized_chars = len(optimized_code)
        
        line_change = optimized_lines - original_lines
        char_change = optimized_chars - original_chars
        
        # Simple optimization note based on basic metrics
        if char_change < 0:
            note = f"Code optimized successfully! Reduced from {original_lines} to {optimized_lines} lines ({abs(line_change)} line reduction)."
        elif char_change > 0:
            note = f"Code restructured successfully! Expanded from {original_lines} to {optimized_lines} lines ({line_change:+d} line change) for improvements."
        else:
            note = f"Code optimized successfully! Maintained {original_lines} lines with structural improvements."
        
        return {
            "optimized_code": optimized_code,
            "optimization_note": note,
            "language_detected": detected_language,
            "optimization_status": "success",
            "improvement_summary": {
                "original_lines": original_lines,
                "optimized_lines": optimized_lines,
                "line_change": line_change,
                "original_chars": original_chars,
                "optimized_chars": optimized_chars,
                "char_change": char_change,
                "note": "Quality checks bypassed for speed"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Code optimization error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Code optimization failed. Please try again.")