"""
LLM Utilities Module

This module provides utility functions for LLM interactions, including
client management, retry logic, JSON parsing, and fallback responses.
"""

import openai
import os
import logging
from logging import getLogger
from typing import List, Dict, Any, Union, Callable, Awaitable
from functools import wraps
import asyncio
import json
import tiktoken
from dotenv import load_dotenv
import httpx
load_dotenv()

TOKEN_LIMIT = 8192

logger = getLogger(__name__)

# === Configuration ===
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("OPENAI_API_KEY not found in environment variables")
    raise ValueError("OPENAI_API_KEY must be set")

# === Shared Async OpenAI Client ===
client = openai.AsyncOpenAI(api_key=openai_api_key)
logger.info("Shared OpenAI client initialized")

# === Model Name ===
MODEL_NAME = "gpt-4o-mini"

PROGRESS_API_BASE_URL = os.getenv("PROGRESS_API_BASE_URL")

def get_token_count(text: str, model: str = "cl100k_base") -> int:
    """
    Count tokens in text using tiktoken.
    """
    encoding = tiktoken.get_encoding(model)
    return len(encoding.encode(text))

def is_valid_for_embedding(text: str) -> bool:
    """
    Check if text is within token limit for embedding.
    """
    return get_token_count(text) < TOKEN_LIMIT

# === Retry Logic Wrapper ===
def retry_with_backoff(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """
    Decorator for retrying failed API calls with exponential backoff.
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        MAX_RETRIES = 3
        RETRY_DELAY = 1
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying...")
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

        logger.error(f"Failed after {MAX_RETRIES} attempts: {str(last_error)}")
        raise last_error or Exception("Unknown error during OpenAI call")
    return wrapper

# === Safe Strip Utility ===
def safe_strip(text: Union[str, None]) -> str:
    """
    Safely strip whitespace from text, handling None values.
    """
    return text.strip() if text else ""

# === JSON Parser with Fallback ===
def parse_json_response(content: Union[str, None], fallback: dict) -> dict:
    """
    Parse JSON response with fallback handling and markdown cleanup.
    """
    content = safe_strip(content)
    if not content:
        logger.warning("Empty content passed to JSON parser")
        return fallback

    try:
        # Remove markdown blocks
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]

        result = json.loads(content)
        logger.info("Successfully parsed JSON response")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}\nContent: {content[:500]}...")
        return fallback

# === Fallback Responses ===
def get_fallback_interview_question() -> str:
    """
    Return fallback question when AI generation fails.
    """
    return "Could you explain your approach again?"

def get_fallback_clarification() -> str:
    """
    Return fallback clarification when AI generation fails.
    """
    return "Please rephrase your question."

def get_fallback_optimized_code() -> str:
    """
    Return fallback code when optimization fails.
    Returns a valid JSON string instead of a comment.
    """
    return json.dumps({
        "optimized_code": "# Error: Could not optimize code. Please try again.",
        "optimization_summary": "System error occurred during optimization."
    })

def get_fallback_feedback(user_name: str = "Candidate") -> dict:
    """
    Return fallback feedback when generation fails.
    """
    return {
        "summary": f"{user_name}, we encountered an issue generating feedback.",
        "positive_points": [],
        "points_to_address": ["System error"],
        "areas_for_improvement": ["Try again later"],
        "metrics": {}
    }

def get_fallback_analysis() -> dict:
    """
    Return fallback analysis when generation fails.
    """
    return {
        "feedback": "Internal system error",
        "strengths": [],
        "areas_for_improvement": ["Could not analyze"],
        "score": 0
    }

async def check_question_answered_by_id(user_id: str, question_bank_id: str) -> dict:
    """
    Check if user has previously answered a specific question.
    Calls external progress API to get question history.
    """
    url = f"{PROGRESS_API_BASE_URL.rstrip('/')}/mainQuestionBankProgress/checkQuestionAnsweredbyId"
    
    # Convert ObjectId to string if needed
    if hasattr(question_bank_id, '__str__'):
        question_bank_id = str(question_bank_id)
    if hasattr(user_id, '__str__'):
        user_id = str(user_id)
    
    payload = {"userId": user_id, "questionBankId": question_bank_id}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Progress API call failed: {e}")
        return {"success": False, "error": str(e)}

@retry_with_backoff
async def generate_clarification_feedback(question: str, answer: str) -> str:
    """
    Generate clarification feedback for unclear or incomplete answers.
    Provides interviewer-style clarifications, not new questions.
    """
    prompt = f"""
You are a technical interviewer. The candidate's answer to the following question was unclear, incomplete, or off-topic.

Question: {question}
Candidate's answer: {answer}

As an interviewer, provide a CLARIFICATION, not a new question. Your response should:

1. Briefly point out what was unclear or missing in their answer
2. Ask them to clarify or expand on the SAME topic/question
3. Do NOT introduce new concepts or ask follow-up questions about different aspects

Examples of good clarifications:
- "Your answer was quite brief. Could you elaborate on how you would approach this step by step?"
- "I didn't see you mention [specific aspect]. How would you handle that part?"
- "Your response seems to miss the core requirement. Can you focus specifically on [the main question]?"

Examples of what NOT to do:
- Don't ask about time complexity if the original question was about basic implementation
- Don't introduce new concepts not mentioned in the original question
- Don't ask follow-up questions about different topics

Keep your tone professional and neutral. Your response should be a single clarification statement.
"""
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a technical interviewer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "Your previous answer did not address the question clearly. Please try again, focusing on the specifics asked."
    except Exception as e:
        logger.error(f"Error generating clarification feedback: {str(e)}")
        return "Your previous answer did not address the question clearly. Please try again, focusing on the specifics asked."