"""
Code Optimization Service

This module provides code optimization functionality for Python and SQL code.
Uses AI to analyze, optimize, and improve code while maintaining functionality.
"""

from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip, get_fallback_optimized_code
from typing import Union, Optional
import logging
import json
import ast
import re

logger = logging.getLogger(__name__)

def validate_python_syntax(code: str) -> bool:
    """
    Validate Python syntax using ast.parse.
    Returns True if syntax is valid, False otherwise.
    """
    try:
        ast.parse(code)
        return True
    except SyntaxError as e:
        logger.warning(f"Python syntax error: {str(e)}")
        return False
    except Exception as e:
        logger.warning(f"Python validation error: {str(e)}")
        return False

def validate_sql_syntax(code: str) -> bool:
    """
    Basic SQL syntax validation using regex patterns.
    Returns True if basic SQL structure is valid, False otherwise.
    """
    try:
        # Remove comments and normalize whitespace
        code_clean = re.sub(r'--.*$', '', code, flags=re.MULTILINE)  # Remove single-line comments
        code_clean = re.sub(r'/\*.*?\*/', '', code_clean, flags=re.DOTALL)  # Remove multi-line comments
        code_clean = re.sub(r'\s+', ' ', code_clean).strip()
        
        # Basic SQL validation patterns
        sql_patterns = [
            r'\bSELECT\b',  # Must have SELECT
            r'\bFROM\b',    # Must have FROM
            r'[;]?\s*$',    # Optional semicolon at end
        ]
        
        for pattern in sql_patterns:
            if not re.search(pattern, code_clean, re.IGNORECASE):
                logger.warning(f"SQL validation failed: missing pattern {pattern}")
                return False
        
        return True
    except Exception as e:
        logger.warning(f"SQL validation error: {str(e)}")
        return False

def validate_code_syntax(code: str, language: str = "python") -> bool:
    """
    Validate code syntax based on language.
    Returns True if syntax is valid, False otherwise.
    """
    if not code or not isinstance(code, str):
        return False
    
    if language.lower() == "python":
        return validate_python_syntax(code)
    elif language.lower() == "sql":
        return validate_sql_syntax(code)
    else:
        # For unknown languages, assume valid
        return True

def analyze_code_quality(original_code: str, optimized_code: str) -> dict:
    """
    Analyze the quality of optimization to ensure it's actually improving the code.
    Returns a dict with quality metrics and recommendations.
    """
    try:
        # Basic metrics
        original_lines = len(original_code.splitlines())
        optimized_lines = len(optimized_code.splitlines())
        
        # Check if we're just removing lines without optimization
        line_reduction = original_lines - optimized_lines
        line_reduction_ratio = line_reduction / original_lines if original_lines > 0 else 0
        
        # Check for important elements that should be preserved
        has_original_prints = 'print(' in original_code
        has_optimized_prints = 'print(' in optimized_code
        prints_preserved = has_original_prints == has_optimized_prints
        
        # Check for function/class definitions
        has_original_defs = 'def ' in original_code or 'class ' in original_code
        has_optimized_defs = 'def ' in optimized_code or 'class ' in optimized_code
        structure_preserved = has_original_defs == has_optimized_defs
        
        # Check if code is actually executable (has basic structure)
        is_executable = (
            optimized_code.strip() and 
            not optimized_code.startswith('#') and
            not optimized_code.startswith('"""') and
            not optimized_code.startswith("'''")
        )
        
        # Quality score (0-100)
        quality_score = 0
        if structure_preserved:
            quality_score += 30
        if prints_preserved:
            quality_score += 20
        if is_executable:
            quality_score += 30
        if line_reduction_ratio > 0.1:  # At least 10% reduction
            quality_score += 20
        
        return {
            "quality_score": quality_score,
            "line_reduction": line_reduction,
            "line_reduction_ratio": line_reduction_ratio,
            "prints_preserved": prints_preserved,
            "structure_preserved": structure_preserved,
            "is_executable": is_executable,
            "recommendation": "good" if quality_score >= 70 else "needs_improvement"
        }
    except Exception as e:
        logger.error(f"Error analyzing code quality: {str(e)}")
        return {
            "quality_score": 0,
            "recommendation": "error"
        }

@retry_with_backoff
async def generate_optimized_code(
    question: str,
    description: str,
    user_code: str,
    sample_input: str,
    sample_output: str,
    rag_context: Optional[str] = None,
    model: str = MODEL_NAME
) -> dict:
    """
    Generate optimized version of user's code (Python/MySQL).
    Always returns JSON with only 'optimized_code'.
    """
    try:
        prompt = f"""You are an expert code optimizer. Your task is to OPTIMIZE the given code while preserving its EXACT functionality and ensuring it's production-ready.

### CRITICAL REQUIREMENTS
- RETURN ONLY JSON FORMAT: {{"optimized_code": "complete optimized code"}}
- PRESERVE EXACT BEHAVIOR - same inputs must produce same outputs
- MAINTAIN ALL IMPORTANT OUTPUT STATEMENTS - keep print statements, return values, etc.
- OPTIMIZE FOR PERFORMANCE, READABILITY, AND BEST PRACTICES
- REMOVE ONLY unnecessary code, comments, and debug statements
- KEEP the core logic, functions, classes, and output statements
- ENSURE CODE IS COMPLETE AND EXECUTABLE
- DO NOT truncate or remove essential functionality

### OPTIMIZATION FOCUS AREAS
1. **Performance**: Use more efficient algorithms, reduce unnecessary operations
2. **Readability**: Improve variable names, structure, and formatting
3. **Best Practices**: Follow language conventions, remove redundant code
4. **Maintainability**: Simplify complex logic, improve error handling

### WHAT TO PRESERVE
- All function/class definitions
- All print statements that show results
- All return statements and output logic
- Core algorithm and business logic
- Error handling and edge case logic

### WHAT TO REMOVE/IMPROVE
- Unnecessary comments and docstrings
- Debug print statements (but keep result prints)
- Redundant variable assignments
- Inefficient loops or operations
- Unused imports or variables

### PROBLEM CONTEXT
Question: {question}
Description: {description}

### USER-SUBMITTED CODE
{user_code}

### REFERENCE BEHAVIOR
Sample Input: {sample_input}
Expected Output: {sample_output}

### OPTIMIZATION INSTRUCTIONS
1. Analyze the code for actual optimization opportunities
2. Focus on performance improvements, not just line reduction
3. Ensure the complete, executable code is returned
4. Maintain proper syntax and formatting
5. If no meaningful optimization is possible, return the original code
6. Preserve all output statements that show final results
7. Return the core function/class with complete functionality

Return the complete optimized code in JSON format. The code must be executable and produce the same results as the original.
"""

        if rag_context:
            prompt += f"\nRelevant context:\n{rag_context}\n"

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=3000,  # Increased token limit for better optimization
            temperature=0.1,  # Lower temperature for more consistent optimization
            response_format={"type": "json_object"}
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))

        if not content:
            logger.warning("Empty response from LLM, returning original code")
            return {"optimized_code": user_code}

        try:
            parsed = json.loads(content)
            optimized_code = parsed.get("optimized_code", "")
            
            if not optimized_code:
                logger.warning("No optimized_code in LLM response, returning original code")
                return {"optimized_code": user_code}
            
            # Detect language based on code content
            language = "python"  # Default to python
            if any(keyword in optimized_code.upper() for keyword in ["SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE"]):
                language = "sql"
            
            # Validate syntax
            if not validate_code_syntax(optimized_code, language):
                logger.warning(f"Syntax validation failed for {language} code, returning original code")
                return {"optimized_code": user_code}
            
            # Analyze optimization quality
            quality_analysis = analyze_code_quality(user_code, optimized_code)
            
            # If optimization quality is poor, return original code
            if quality_analysis["quality_score"] < 50:
                logger.warning(f"Poor optimization quality (score: {quality_analysis['quality_score']}), returning original code")
                logger.warning(f"Quality analysis: {quality_analysis}")
                return {"optimized_code": user_code}
            
            # Log successful optimization
            logger.info(f"Code optimization successful. Quality score: {quality_analysis['quality_score']}")
            logger.info(f"Quality analysis: {quality_analysis}")
            
            return {"optimized_code": optimized_code}
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return {"optimized_code": user_code}

    except Exception as e:
        logger.error(f"Error optimizing code: {str(e)}")
        return {"optimized_code": user_code}



@retry_with_backoff
async def generate_optimization_summary(
    original_code: str,
    optimized_code: str,
    question: str = ""
) -> str:
    """
    Generate summary of changes between original and optimized code.
    Provides bullet points of improvements and optimizations made.
    """
    try:
        prompt = f"""
You are a code reviewer. Given the original code and the optimized code, summarize in 3-5 bullet points what was changed, improved, or optimized. Be specific and concise. If possible, mention any bug fixes, performance improvements, or code style enhancements.

Question (if relevant): {question}

Original Code:
{original_code}

Optimized Code:
{optimized_code}

Return only a plain English summary, suitable for a multiline comment.
"""
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "No summary available."
    except Exception as e:
        logger.error(f"Error generating optimization summary: {str(e)}")
        return "No summary available."

@retry_with_backoff
async def generate_optimized_code_with_summary(
    question: str,
    user_code: str,
    sample_input: str,
    sample_output: str,
    rag_context: Optional[str] = None,
    model: str = MODEL_NAME
) -> dict:
    """
    Generate optimized code with detailed summary.
    Combines code optimization and explanation in single response.
    """
    try:
        optimized_json = await generate_optimized_code(
            question=question,
            user_code=user_code,
            sample_input=sample_input,
            sample_output=sample_output,
            rag_context=rag_context,
            model=model
        )
        
        # Parse the JSON response
        if isinstance(optimized_json, str):
            try:
                optimized_json = json.loads(optimized_json)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {str(e)}")
                logger.error(f"Raw response: {optimized_json}")
                return {
                    "optimized_code": user_code,  # Return original code as fallback
                    "optimization_summary": "Could not parse optimization result. Returning original code."
                }
        
        # Extract the required fields with validation
        optimized_code = optimized_json.get("optimized_code", "")
        optimization_summary = optimized_json.get("optimization_summary", "No summary available.")
        
        # Validate optimized_code
        if not optimized_code or not isinstance(optimized_code, str) or not optimized_code.strip():
            logger.warning("LLM returned empty or invalid optimized_code, using original code")
            optimized_code = user_code
            optimization_summary = "No optimization was possible. Original code returned."
        
        # Final validation - ensure we have actual code
        if optimized_code.strip() == "":
            logger.error("Final optimized_code is empty, using original code")
            optimized_code = user_code
            optimization_summary = "Error: Generated code was empty. Original code returned."
        
        return {
            "optimized_code": optimized_code,
            "optimization_summary": optimization_summary
        }
        
    except Exception as e:
        logger.error(f"Error in optimized code with summary: {str(e)}")
        return {
            "optimized_code": user_code,  # Return original code as fallback
            "optimization_summary": f"Error during optimization: {str(e)}. Original code returned."
        } 