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
        logger.info(f"Starting code optimization for question: {question[:100]}...")
        
        # Detect language
        language = detect_language(user_code)
        logger.info(f"Detected language: {language}")
        
        # Generate language-specific prompt
        prompt = get_language_specific_prompt(
            language, question, description, user_code, sample_input, sample_output
        )
        
        logger.info(f"Generated prompt for {language}. Prompt length: {len(prompt)} characters")
        
        if rag_context:
            prompt += f"\nRelevant context:\n{rag_context}\n"
            logger.info("Added RAG context to prompt")

        logger.info(f"Calling LLM with model: {model}")
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=1000,
            response_format={"type": "json_object"}
        )

        logger.info("LLM response received successfully")
        content = safe_strip(getattr(response.choices[0].message, 'content', None))

        if not content:
            logger.warning("Empty response from LLM, returning original code")
            return {"optimized_code": user_code}

        logger.info(f"LLM content length: {len(content)} characters")
        logger.info(f"LLM content preview: {content[:200]}...")

        try:
            parsed = json.loads(content)
            logger.info(f"Successfully parsed JSON response. Keys: {list(parsed.keys())}")
            
            optimized_code = parsed.get("optimized_code", "")
            logger.info(f"Extracted optimized code. Length: {len(optimized_code)} characters")
            
            if not optimized_code:
                logger.warning("No optimized_code in LLM response, returning original code")
                return {"optimized_code": user_code}
            
            # Return optimized code immediately - no validation for speed
            logger.info("LLM optimization successful, returning immediately for speed")
            return {"optimized_code": optimized_code}
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            logger.error(f"Raw content that failed to parse: {content[:500]}...")
            return {"optimized_code": user_code}

    except Exception as e:
        logger.error(f"Error optimizing code: {str(e)}", exc_info=True)
        return {"optimized_code": user_code}
