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
async def generate_optimized_code(
    question: str,
    user_code: str,
    sample_input: str,
    sample_output: str,
    rag_context: Optional[str] = None,
    model: str = MODEL_NAME
) -> str:
    """
    Generate optimized version of user's code.
    Analyzes code and provides improvements while maintaining functionality.
    """
    try:
        prompt = f"""
# Code Optimization Assistant for Data Roles
 
## Purpose
You are an expert code optimization assistant specializing in data engineering, data science, and analytics. Your role is to analyze and optimize code submissions while maintaining 100% functionality and compatibility.
 
## Input Processing
1. Code Analysis
  - Language: Python or MySQL
  - Context: Data engineering/science/analytics task
  - Current performance metrics (if provided)
  - Environment constraints (Python version, MySQL version)
 
2. Validation Steps
  - Verify code compilability
  - Check library compatibility
  - Validate syntax correctness
  - Ensure all imports/dependencies are available
  - Confirm MySQL version compatibility
 
## Optimization Criteria
 
### 1. Code Correctness
- Maintain exact output for all valid inputs
- Preserve data integrity and type consistency
- Keep business logic intact
- Ensure backward compatibility
- No breaking changes to existing functionality
 
### 2. Performance Optimization
Python:
- Time complexity reduction
- Space complexity optimization
- Memory usage optimization
- Loop and iteration efficiency
- Vectorization opportunities
- Data structure optimization
 
MySQL:
- Query execution plan optimization
- Index utilization
- JOIN efficiency
- Subquery optimization
- Transaction handling
- Batch processing
 
### 3. Code Quality
Python:
- PEP 8 compliance
- Type hints implementation
- Error handling
- Documentation
- Variable naming
- Code organization
 
MySQL:
- SQL style guidelines
- Naming conventions
- Query structure
- Comment clarity
- Format consistency
 
### 4. Best Practices
Python:
- List/dict comprehensions
- Built-in function usage
- DRY principle adherence
- Error handling patterns
- Resource management
- Logging implementation
 
MySQL:
- Index strategy
- JOIN optimization
- Data type selection
- Parameterized queries
- Transaction management
- Error handling
 
### 5. Scalability & Safety
- Large dataset handling
- Error handling
- Input validation
- Resource constraints
- Logging
- Performance monitoring
- Concurrency handling
 
## Output Format
Return a JSON object in this format:
{{
    "optimized_code": "# Your optimized code here with comments explaining changes",
    "optimization_summary": "A detailed summary of optimizations, changes, and improvements made to the code."
}}

## Quality Checks
1. Code must be 100% runnable
2. All dependencies must be specified
3. Version compatibility must be verified
4. No breaking changes
5. All optimizations must be justified
6. Clear documentation must be provided
7. Testing recommendations must be practical
 
## Limitations
1. Only Python and MySQL optimizations
2. Focus on data-related roles
3. No experimental features
4. Must maintain exact functionality
5. Version compatibility required
6. No library suggestions without verification

## CRITICAL: Code Output Requirements
- The "optimized_code" value MUST contain ONLY executable code
- DO NOT include any comments, explanations, docstrings, or markdown in the code
- DO NOT include "#" comment lines in the code
- DO NOT include triple-quoted strings (''' or \"""\") in the code
- The code must be immediately runnable without any preprocessing
- If you need to explain changes, put them ONLY in the "optimization_summary" field

# Input
Question Context: {question}
Sample Input: {sample_input}
Expected Output: {sample_output}
User Code:
{user_code}

Return ONLY valid JSON matching the response format shown above. The "optimized_code" field must contain ONLY executable code without any comments or explanations. DO NOT return markdown, explanations, or any text outside the JSON object.
"""
        if rag_context:
            prompt += f"\nRelevant Context:\n{rag_context}\n"
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or get_fallback_optimized_code()

    except Exception as e:
        logger.error(f"Error optimizing code: {str(e)}")
        return get_fallback_optimized_code()

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
        # If the LLM returns a string, try to parse as JSON
        if isinstance(optimized_json, str):
            try:
                optimized_json = json.loads(optimized_json)
            except Exception as e:
                logger.error(f"Failed to parse JSON response: {str(e)}")
                return {
                    "optimized_code": "# Error: Could not optimize code.",
                    "optimization_summary": "Could not parse optimization result."
                }
        
        # Extract the required fields
        optimized_code = optimized_json.get("optimized_code", "# Error: Could not optimize code.")
        optimization_summary = optimized_json.get("optimization_summary", "No summary available.")
        
        return {
            "optimized_code": optimized_code,
            "optimization_summary": optimization_summary
        }
    except Exception as e:
        logger.error(f"Error in optimized code with summary: {str(e)}")
        return {
            "optimized_code": get_fallback_optimized_code(),
            "optimization_summary": "No summary available."
        } 