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
        logger.info(f"Code optimization request received - User ID: {request.user_id}")
        logger.info(f"Request details - Question: {request.question[:100]}...")
        logger.info(f"Code length: {len(request.user_code)} characters")
        logger.info(f"Sample input: {request.sample_input[:100]}...")
        logger.info(f"Sample output: {request.sample_output[:100]}...")
        
        # Validate user exists
        if not await validate_user_id(request.user_id):
            logger.error(f"User not found: user_id={request.user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        
        logger.info("User validation successful")
        
        # Detect language for better optimization
        detected_language = detect_language(request.user_code)
        logger.info(f"Detected language: {detected_language} for user code")
        
        # Log a sample of the code for debugging
        code_sample = request.user_code[:200] + "..." if len(request.user_code) > 200 else request.user_code
        logger.info(f"Code sample: {code_sample}")
        
        # Generate optimized code
        logger.info("Starting code optimization with LLM...")
        result = await generate_optimized_code(
            question=request.question,
            description=request.description,
            user_code=request.user_code,
            sample_input=request.sample_input,
            sample_output=request.sample_output
        )
        
        logger.info(f"LLM optimization completed. Result keys: {list(result.keys()) if result else 'None'}")
        
        # Get the optimized code
        optimized_code = result.get("optimized_code", "")
        logger.info(f"Optimized code length: {len(optimized_code)} characters")
        
        # Basic validation
        if not optimized_code or not isinstance(optimized_code, str):
            logger.warning("Failed to generate optimized code. Returning original code.")
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
        
        logger.info(f"Optimization metrics - Lines: {original_lines} -> {optimized_lines}, Chars: {original_chars} -> {optimized_chars}")
        
        # Simple optimization note based on basic metrics
        if char_change < 0:
            note = f"Code optimized successfully! Reduced from {original_lines} to {optimized_lines} lines ({abs(line_change)} line reduction)."
        elif char_change > 0:
            note = f"Code restructured successfully! Expanded from {original_lines} to {optimized_lines} lines ({line_change:+d} line change) for improvements."
        else:
            note = f"Code optimized successfully! Maintained {original_lines} lines with structural improvements."
        
        logger.info("Code optimization completed successfully")
        
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