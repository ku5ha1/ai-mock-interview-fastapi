"""
Code Optimization Service

This module provides code optimization functionality for Python and SQL code.
Uses AI to analyze, optimize, and improve code while maintaining functionality.
"""

from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip, get_fallback_optimized_code
from typing import Union, Optional
import logging
import json

logger = logging.getLogger(__name__)

@retry_with_backoff
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
    Generate optimized version of user's code (Python/SQL).
    Always returns JSON with only 'optimized_code'.
    """
    try:
        prompt = f"""
You are a code optimizer. Your task is to optimize the given code while preserving its EXACT functionality and structure.

### CRITICAL RULES
- RETURN ONLY JSON FORMAT: {{"optimized_code": "complete optimized code"}}
- PRESERVE EXACT BEHAVIOR - same inputs must produce same outputs
- MAINTAIN CODE STRUCTURE - keep functions, classes, logic flow intact
- PRESERVE READABILITY - keep proper indentation and formatting
- REMOVE test cases, sample usage code, and debug prints
- KEEP output statements that show final results (e.g., print statements showing learned parameters)
- REMOVE unnecessary comments, docstrings, debug prints, and trailing whitespace
- DO NOT TRUNCATE CODE - return the complete optimized function/class
- DO NOT CHANGE variable names, function names, or logic flow unless it improves performance
- IF code is already optimal, return the ORIGINAL code unchanged
- ENSURE CODE IS EXECUTABLE and complete
- RETURN THE CORE FUNCTION/CLASS WITH FINAL OUTPUT - keep result display statements

### PROBLEM CONTEXT
Question: {question}
Description: {description}

### USER-SUBMITTED CODE
{user_code}

### REFERENCE BEHAVIOR
Sample Input: {sample_input}
Expected Output: {sample_output}

### OPTIMIZATION INSTRUCTIONS
1. Keep the exact same function signature and logic
2. Optimize only for performance, readability, or best practices
3. Ensure the complete code is returned (no truncation)
4. Maintain proper Python/SQL syntax and formatting
5. If no meaningful optimization is possible, return the original code
6. REMOVE test cases and sample usage code
7. KEEP output statements that show final computation results
8. Return the core function/class with result display

Return the complete optimized code in JSON format.
"""

        if rag_context:
            prompt += f"\nRelevant context:\n{rag_context}\n"

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000,  # Increased token limit
            response_format={"type": "json_object"}
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))

        if not content:
            return {"optimized_code": user_code}

        try:
            parsed = json.loads(content)
            if not parsed.get("optimized_code"):
                return {"optimized_code": user_code}
            return {"optimized_code": parsed["optimized_code"]}
        except json.JSONDecodeError:
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