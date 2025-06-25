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
    encoding = tiktoken.get_encoding(model)
    return len(encoding.encode(text))

def is_valid_for_embedding(text: str) -> bool:
    return get_token_count(text) < TOKEN_LIMIT

# === Retry Logic Wrapper ===
def retry_with_backoff(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
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
    return text.strip() if text else ""

# === JSON Parser with Fallback ===
def parse_json_response(content: Union[str, None], fallback: dict) -> dict:
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
    return "Could you explain your approach again?"

def get_fallback_clarification() -> str:
    return "Please rephrase your question."

def get_fallback_optimized_code() -> str:
    return "# Error: Could not optimize code."

def get_fallback_feedback(user_name: str = "Candidate") -> dict:
    return {
        "summary": f"{user_name}, we encountered an issue generating feedback.",
        "positive_points": [],
        "points_to_address": ["System error"],
        "areas_for_improvement": ["Try again later"],
        "metrics": {}
    }

def get_fallback_analysis() -> dict:
    return {
        "feedback": "Internal system error",
        "strengths": [],
        "areas_for_improvement": ["Could not analyze"],
        "score": 0
    }

async def check_question_answered_by_id(user_id: str, question_bank_id: str) -> dict:
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
    Generate a clarification or follow-up prompt in the style of an interviewer, not a helper or tutor.
    """
    prompt = f"""
You are a technical interviewer. The candidate's answer to the following question was unclear, incomplete, or off-topic.

Question: {question}
Candidate's answer: {answer}

As an interviewer, point out what was missing or unclear in the answer and ask a direct, probing follow-up question. Do not thank the candidate, do not encourage them to try again, and do not use phrases like 'I encourage you' or 'Thank you for your response.' Keep your tone professional, neutral, and focused on clarifying or probing further. Respond as you would in a real interview.

Your response should be a single, direct follow-up or clarification question or statement.
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