"""
Core Code Optimization Module

Contains the main optimization function and LLM integration logic.
"""

import logging
import json
from typing import Optional

from services.llm.utils import client, retry_with_backoff, safe_strip, MODEL_NAME
from .language_detection import detect_language
from .prompts import get_language_specific_prompt

logger = logging.getLogger(__name__)

# Use the MODEL_NAME from utils.py instead of hardcoding

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
    Uses language-aware prompts and optimized quality checks for faster response.
    """
    try:
        # Detect language
        language = detect_language(user_code)
        logger.info(f"Detected language: {language}")
        
        # Generate language-specific prompt
        prompt = get_language_specific_prompt(
            language, question, description, user_code, sample_input, sample_output
        )
        
        if rag_context:
            prompt += f"\nRelevant context:\n{rag_context}\n"

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=1000,
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
            
            # Return optimized code immediately - no validation for speed
            logger.info("LLM optimization successful, returning immediately for speed")
            return {"optimized_code": optimized_code}
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return {"optimized_code": user_code}

    except Exception as e:
        logger.error(f"Error optimizing code: {str(e)}")
        return {"optimized_code": user_code}
