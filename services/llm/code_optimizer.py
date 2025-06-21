from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip, get_fallback_optimized_code
from typing import Union, Optional
import logging

logger = logging.getLogger(__name__)

@retry_with_backoff
async def generate_optimized_code(
    question: str,
    user_code: str,
    sample_input: str,
    sample_output: str,
    rag_context: Optional[str] = None
) -> str:
    try:
        prompt = f"""
Question Context: {question}
Sample Input: {sample_input}
Expected Output: {sample_output}
User Code:
{user_code}
"""
        if rag_context:
            prompt += f"\nRelevant Context:\n{rag_context}\n"
        prompt += "\nImprove the code to work correctly and efficiently.\nOnly return the optimized code — no explanation needed.\n"

        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000
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
    Use the LLM to summarize what was changed and optimized between the original and optimized code.
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
    rag_context: Optional[str] = None
) -> dict:
    try:
        optimized_code = await generate_optimized_code(
            question=question,
            user_code=user_code,
            sample_input=sample_input,
            sample_output=sample_output,
            rag_context=rag_context
        )
        summary = await generate_optimization_summary(user_code, optimized_code, question)
        return {"optimized_code": optimized_code, "optimization_summary": summary}
    except Exception as e:
        logger.error(f"Error in optimized code with summary: {str(e)}")
        return {"optimized_code": get_fallback_optimized_code(), "optimization_summary": "No summary available."}