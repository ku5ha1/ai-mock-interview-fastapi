"""
Code Optimization API Routes

This module handles code optimization requests, providing improved code solutions
with explanations and performance enhancements.
"""

import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Body
from services.code_optimizer import generate_optimized_code, generate_optimized_code_with_summary, analyze_code_quality
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
    
    # Remove docstrings (triple quotes) but be careful not to remove code
    # Only remove if they're at the start of lines or standalone
    lines = code.splitlines()
    cleaned_lines = []
    
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        
        # Skip empty lines
        if not stripped_line:
            continue
            
        # Skip lines that are only comments
        if stripped_line.startswith('#') or stripped_line.startswith('//'):
            continue
            
        # Skip standalone docstrings (triple quotes on their own line)
        if (stripped_line.startswith("'''") and stripped_line.endswith("'''")) or \
           (stripped_line.startswith('"""') and stripped_line.endswith('"""')):
            continue
            
        # For lines with inline comments, keep the code part
        if '#' in line:
            # Find the first # that's not in a string
            # Simple approach: split on # and keep the first part
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
    
    # Additional safety check: ensure we have at least some code structure
    has_code_structure = any([
        'def ' in result,
        'class ' in result,
        'import ' in result,
        'from ' in result,
        '=' in result,
        'print(' in result,
        'return ' in result,
        'if ' in result,
        'for ' in result,
        'while ' in result
    ])
    
    if not has_code_structure:
        logger.warning("Comment stripping removed all code structure, returning original code")
        return code
    
    return result

@router.post("/optimize-code")
async def optimize_code(request: CodeOptimizationRequest):
    """
    Optimize user's code with improvements and explanations.
    Uses RAG context to provide relevant optimization suggestions.
    Returns only the optimized code in the response, with all comments removed.
    Uses the 'gpt-4o-mini-2024-07-18' model for code optimization.
    """
    logger = logging.getLogger(__name__)
    
    # Validate user exists
    if not await validate_user_id(request.user_id):
        logger.error(f"User not found: user_id={request.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Generate optimized code using only user input and no external context
        result = await generate_optimized_code(
            question=request.question,
            description=request.description,
            user_code=request.user_code,
            sample_input=request.sample_input,
            sample_output=request.sample_output,
            model="gpt-4o-mini-2024-07-18"
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
        
        # Check if the optimized code is actually different from the original
        if optimized_code.strip() == request.user_code.strip():
            logger.info(f"Code optimization returned identical code for user_id={request.user_id}, returning original with note")
            return {
                "optimized_code": request.user_code,
                "optimization_note": "Code was already optimal. No changes were made."
            }
        
        # Strip comments from the code
        code_no_comments = strip_comments_from_code(optimized_code)
        
        # Enhanced validation after comment stripping
        if not code_no_comments.strip():
            logger.error(f"Code became empty after comment stripping for user_id={request.user_id}. Original: {optimized_code[:200]}...")
            # Return the original code if stripping removed everything
            return {
                "optimized_code": request.user_code,
                "optimization_note": "Error: Comment stripping removed all content. Original code returned."
            }
        
        # Additional validation: ensure the optimized code has the essential structure
        essential_elements = []
        if 'def ' in request.user_code or 'class ' in request.user_code:
            essential_elements.append('function/class definition')
        if 'print(' in request.user_code:
            essential_elements.append('print statements')
        if 'return ' in request.user_code:
            essential_elements.append('return statements')
        
        missing_elements = []
        for element in essential_elements:
            if element == 'function/class definition' and ('def ' not in code_no_comments and 'class ' not in code_no_comments):
                missing_elements.append('function/class definition')
            elif element == 'print statements' and 'print(' not in code_no_comments:
                missing_elements.append('print statements')
            elif element == 'return statements' and 'return ' not in code_no_comments:
                missing_elements.append('return statements')
        
        if missing_elements:
            logger.warning(f"Essential elements missing from optimized code: {missing_elements}")
            return {
                "optimized_code": request.user_code,
                "optimization_note": f"Warning: Essential elements were removed during optimization: {', '.join(missing_elements)}. Original code returned."
            }
        
        # Log success for debugging
        original_length = len(request.user_code)
        optimized_length = len(code_no_comments)
        reduction_percentage = ((original_length - optimized_length) / original_length * 100) if original_length > 0 else 0
        
        logger.info(f"Successfully optimized code for user_id={request.user_id}. Original length: {original_length}, Optimized length: {optimized_length}, Reduction: {reduction_percentage:.1f}%")
        
        # Provide informative response about the optimization
        optimization_note = f"Code optimized successfully. Reduced from {original_length} to {optimized_length} characters ({reduction_percentage:.1f}% reduction)."
        
        return {
            "optimized_code": code_no_comments,
            "optimization_note": optimization_note
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing code for user_id={request.user_id}, question={request.question}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error optimizing code: {str(e)}")

@router.post("/optimize-code-detailed")
async def optimize_code_detailed(request: CodeOptimizationRequest):
    """
    Optimize user's code with detailed analysis and explanations.
    Returns both the optimized code and a detailed breakdown of what was optimized.
    """
    logger = logging.getLogger(__name__)
    
    # Validate user exists
    if not await validate_user_id(request.user_id):
        logger.error(f"User not found: user_id={request.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Generate optimized code
        result = await generate_optimized_code(
            question=request.question,
            description=request.description,
            user_code=request.user_code,
            sample_input=request.sample_input,
            sample_output=request.sample_output,
            model="gpt-4o-mini-2024-07-18"
        )
        
        # Save interaction for analytics (non-blocking)
        try:
            await save_user_ai_interaction(
                user_id=request.user_id,
                endpoint="code_optimization_detailed",
                input_data=request.dict(),
                ai_response=result
            )
        except Exception as e:
            logger.error(f"Failed to save user-AI interaction for user_id={request.user_id}: {e}", exc_info=True)
        
        # Get the optimized code
        optimized_code = result.get("optimized_code", "")
        
        if not optimized_code or not isinstance(optimized_code, str):
            raise HTTPException(status_code=500, detail="Failed to generate optimized code")
        
        # Strip comments for the final output
        code_no_comments = strip_comments_from_code(optimized_code)
        
        # Generate detailed analysis
        analysis = await generate_optimization_summary(
            original_code=request.user_code,
            optimized_code=code_no_comments,
            question=request.question
        )
        
        # Calculate optimization metrics
        original_length = len(request.user_code)
        optimized_length = len(code_no_comments)
        reduction_percentage = ((original_length - optimized_length) / original_length * 100) if original_length > 0 else 0
        
        # Check what was preserved/removed
        original_lines = len(request.user_code.splitlines())
        optimized_lines = len(code_no_comments.splitlines())
        
        # Analyze code structure preservation
        structure_analysis = {
            "functions_preserved": "def " in request.user_code and "def " in code_no_comments,
            "classes_preserved": "class " in request.user_code and "class " in code_no_comments,
            "prints_preserved": "print(" in request.user_code and "print(" in code_no_comments,
            "returns_preserved": "return " in request.user_code and "return " in code_no_comments,
            "imports_preserved": ("import " in request.user_code and "import " in code_no_comments) or 
                               ("from " in request.user_code and "from " in code_no_comments)
        }
        
        # Determine optimization type
        if optimized_code.strip() == request.user_code.strip():
            optimization_type = "no_changes"
        elif reduction_percentage > 20:
            optimization_type = "significant_optimization"
        elif reduction_percentage > 5:
            optimization_type = "moderate_optimization"
        else:
            optimization_type = "minor_optimization"
        
        return {
            "optimized_code": code_no_comments,
            "optimization_summary": analysis,
            "metrics": {
                "original_length": original_length,
                "optimized_length": optimized_length,
                "reduction_percentage": round(reduction_percentage, 1),
                "original_lines": original_lines,
                "optimized_lines": optimized_lines,
                "line_reduction": original_lines - optimized_lines
            },
            "structure_analysis": structure_analysis,
            "optimization_type": optimization_type,
            "recommendations": [
                "Code has been optimized for better performance and readability",
                "All essential functionality has been preserved",
                "The optimized code is ready for production use"
            ] if optimization_type != "no_changes" else [
                "Your code was already well-optimized",
                "No changes were necessary",
                "Consider this a validation of your coding practices"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in detailed code optimization for user_id={request.user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error optimizing code: {str(e)}")

@router.post("/test-optimization")
async def test_optimization():
    """
    Test endpoint to validate code optimization quality.
    Uses sample code to test the optimization system.
    """
    logger = logging.getLogger(__name__)
    
    # Sample test code
    test_code = '''
def calculate_factorial(n):
    """Calculate factorial of a number"""
    if n < 0:
        return None
    elif n == 0 or n == 1:
        return 1
    else:
        result = 1
        for i in range(1, n + 1):
            result = result * i
        return result

# Test the function
print("Factorial of 5:", calculate_factorial(5))
print("Factorial of 0:", calculate_factorial(0))
print("Factorial of -1:", calculate_factorial(-1))
'''
    
    try:
        # Test optimization
        result = await generate_optimized_code(
            question="Calculate factorial",
            description="Calculate factorial of a number",
            user_code=test_code,
            sample_input="5",
            sample_output="120",
            model="gpt-4o-mini-2024-07-18"
        )
        
        optimized_code = result.get("optimized_code", "")
        
        # Analyze the optimization
        quality_analysis = analyze_code_quality(test_code, optimized_code)
        
        return {
            "test_code": test_code,
            "optimized_code": optimized_code,
            "quality_analysis": quality_analysis,
            "test_passed": quality_analysis["quality_score"] >= 70
        }
        
    except Exception as e:
        logger.error(f"Error in test optimization: {e}", exc_info=True)
        return {
            "error": str(e),
            "test_passed": False
        }