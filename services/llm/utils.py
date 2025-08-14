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
MODEL_NAME = "gpt-4o-mini-2024-07-18"

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
    Returns a valid JSON string with error information.
    """
    return json.dumps({
        "optimized_code": "# Error: Could not optimize code. Please try again.",
        "optimization_summary": "System error occurred during optimization. The original code has been returned unchanged.",
        "error_details": "The optimization service encountered an error. This could be due to temporary service issues or invalid input. Please verify your code and try again."
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
async def generate_clarification_feedback(question: str, answer: str, topic: str = None) -> str:
    """
    Generate clarification feedback for unclear, incomplete, or gibberish answers.
    Provides interviewer-style clarifications, not new questions.
    Focuses ONLY on business requirements, NOT on technical implementation.
    """
    # Detect if the answer appears to be gibberish or nonsensical
    answer_text = answer.strip().lower()
    is_gibberish = (
        len(answer_text) < 10 or
        answer_text in ['i don\'t know', 'idk', 'no idea', 'not sure'] or
        any(char * 3 in answer_text for char in 'abcdefghijklmnopqrstuvwxyz') or  # Repeated characters
        len(set(answer_text.split())) < 2  # Very few unique words
    )
    
    # Check if answer is actually quite good (common algorithmic patterns)
    good_patterns = [
        "create a function", "iterate through", "check if", "maintain a counter",
        "convert to", "handle case", "return the", "for each", "while loop",
        "if statement", "else", "algorithm", "approach", "strategy", "method",
        "step by step", "first", "then", "finally", "initialize", "declare"
    ]
    
    is_good_answer = any(pattern in answer_text for pattern in good_patterns)
    
    if is_good_answer:
        # The answer is actually good, provide encouraging feedback
        prompt = f"""
You are a technical interviewer. The candidate provided a good answer to this question, but you want to encourage them to elaborate further.

Question: {question}
Candidate's answer: "{answer}"
Topic: {topic or "technical interview"}

This answer shows good understanding and approach. Provide encouraging feedback that:
1. Acknowledges their good thinking
2. Asks them to elaborate on specific aspects
3. Encourages them to think deeper about edge cases or optimization
4. Maintains a positive, encouraging tone

IMPORTANT: Focus ONLY on business requirements and problem understanding. Do NOT provide any technical implementation details, code guidance, or algorithmic suggestions.

Example: "Good approach! I can see you understand the core problem. Could you walk me through what edge cases you're considering? What specific scenarios would you want to test?"

Keep your response encouraging and focused on business understanding only.
"""
    elif is_gibberish:
        prompt = f"""
You are a technical interviewer. The candidate provided a nonsensical or gibberish answer to this question.

Question: {question}
Candidate's answer: "{answer}"
Topic: {topic or "technical interview"}

This answer appears to be random characters, repeated text, or completely unrelated to the question.

Provide a professional but firm clarification that:
1. Acknowledges their answer was not meaningful
2. Clearly states what kind of response you're looking for
3. Encourages them to provide a genuine attempt at answering the question
4. Maintains a professional, encouraging tone

IMPORTANT: Focus ONLY on business requirements and problem understanding. Do NOT provide any technical implementation details, code guidance, or algorithmic suggestions.

Example: "I notice your response doesn't seem to address the question. For this technical question, I'm looking for your understanding of the problem requirements. Even if you're not completely sure, please share your thoughts on what you think the question is asking for."

Keep your response concise and professional.
"""
    else:
        # Answer is unclear, incomplete, or off-topic but not gibberish
        prompt = f"""
You are a technical interviewer. The candidate's answer to the following question was unclear, incomplete, or off-topic.

Question: {question}
Candidate's answer: {answer}
Topic: {topic or "technical interview"}

As an interviewer, provide a CLARIFICATION, not a new question. Your response should:

1. Briefly point out what was unclear or missing in their answer
2. Ask them to clarify or expand on the SAME topic/question
3. Do NOT introduce new concepts or ask follow-up questions about different aspects
4. Be specific about what you'd like them to elaborate on

IMPORTANT: Focus ONLY on business requirements and problem understanding. Do NOT provide any technical implementation details, code guidance, or algorithmic suggestions.

Keep your tone conversational and natural, like a real interviewer would speak. Avoid formal business language or structured formatting.

Examples of good clarifications:
- "Your answer was quite brief. Could you elaborate on what you think the problem is asking for?"
- "I didn't see you mention [specific requirement]. How would you define that requirement?"
- "Your response seems to miss the core requirement. Can you focus specifically on [the main question]?"
- "I see you mentioned [concept] but I'm not clear on how it relates to the problem. Could you explain the connection?"

Examples of what NOT to do:
- Don't ask about time complexity or implementation details
- Don't introduce new technical concepts not mentioned in the original question
- Don't ask follow-up questions about different topics
- Don't provide any code or algorithmic guidance
- Don't use formal business language or bullet points

Keep your tone professional but conversational. Your response should be a single clarification statement focused on business understanding only.
"""
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a technical interviewer. Focus ONLY on business requirements and problem understanding. Do NOT provide technical implementation details or code guidance."},
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

@retry_with_backoff
async def generate_quality_feedback(question: str, answer: str, topic: str = None) -> str:
    """
    Generate specific feedback for answers that failed quality validation.
    Provides targeted guidance to help candidates improve their responses.
    Focuses ONLY on business requirements, NOT on technical implementation.
    """
    try:
        prompt = f"""
You are a technical interviewer providing feedback to a candidate whose answer didn't meet the expected quality standards.

Question: {question}
Candidate's answer: "{answer}"
Topic: {topic or "technical interview"}

Your task is to provide constructive feedback that:
1. Briefly acknowledges their attempt
2. Specifically identifies what was missing or unclear
3. Gives clear guidance on what would make a better answer
4. Encourages them to try again with specific focus areas

IMPORTANT: Focus ONLY on business requirements and problem understanding. Do NOT provide any technical implementation details, code guidance, or algorithmic suggestions.

Focus on being helpful and specific, not critical. Your feedback should guide them to provide a better response.

Keep your tone conversational and natural, like a real interviewer would speak. Avoid formal business language or structured formatting.

Examples of good feedback:
- "I can see you're thinking about this problem, but your answer is quite brief. For this type of question, I'm looking for a clear understanding of the problem requirements. Could you explain what you think the question is asking for?"
- "You mentioned [concept] which is relevant, but I need to see more of your reasoning about the business requirements. What specific aspects of the problem are you considering?"
- "Your answer touches on the right area but needs more detail about the problem itself. Can you explain your understanding of the requirements more thoroughly?"

Keep your response encouraging and specific. Focus on helping them understand what makes a good answer about business requirements.
"""
        
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful technical interviewer providing constructive feedback. Focus ONLY on business requirements and problem understanding. Do NOT provide technical implementation details or code guidance."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "Your answer needs improvement. Please provide a more detailed and relevant response to the current question."
    except Exception as e:
        logger.error(f"Error generating quality feedback: {str(e)}")
        return "Your answer needs improvement. Please provide a more detailed and relevant response to the current question."

@retry_with_backoff
async def generate_limit_reached_feedback(question: str, topic: str = None) -> str:
    """
    Generate feedback when clarification limits are reached.
    Informs the user that they've reached the limit and will progress to the next phase.
    """
    try:
        prompt = f"""
You are a technical interviewer. The candidate has reached the maximum number of clarification attempts for a question and will now progress to the next phase.

Question: {question}
Topic: {topic or "technical interview"}

Provide encouraging feedback that:
1. Acknowledges their effort to understand the question
2. Explains that they've reached the clarification limit
3. Informs them they'll be moving forward
4. Encourages them to do their best with their current understanding
5. Maintains a positive, professional tone

Keep your tone conversational and natural, like a real interviewer would speak. Avoid formal business language or structured formatting.

Example: "I appreciate your effort to understand this question thoroughly. You've reached the maximum number of clarification attempts, so we'll move forward with your current understanding. Do your best with what you know, and remember that showing your thought process is often more valuable than having perfect clarity on every detail."

Keep your response encouraging and informative.
"""
        
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful technical interviewer providing encouraging feedback when clarification limits are reached."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "You've reached the maximum number of clarification attempts for this question. We'll move forward with your current understanding. Do your best with what you know!"
    except Exception as e:
        logger.error(f"Error generating limit reached feedback: {str(e)}")
        return "You've reached the maximum number of clarification attempts for this question. We'll move forward with your current understanding. Do your best with what you know!"

@retry_with_backoff
async def answer_clarification_question(question: str, clarification_request: str, topic: str = None) -> str:
    """
    Answer a candidate's clarification question about the problem.
    This function ANSWERS the candidate's questions, it doesn't ask them more questions.
    Focuses ONLY on business requirements, NOT on technical implementation.
    """
    try:
        prompt = f"""
You are a technical interviewer. The candidate has asked you a clarification question about the problem, and you need to ANSWER it professionally.

Original Question: {question}
Candidate's Clarification Request: {clarification_request}
Topic: {topic or "technical interview"}

Your task is to ANSWER their clarification question by:
1. Providing clear, direct answers to what they asked
2. Clarifying business requirements and problem boundaries
3. Explaining input/output expectations
4. Addressing edge cases and constraints they mentioned

IMPORTANT: 
- Focus ONLY on business requirements and problem understanding
- Do NOT provide any technical implementation details, code guidance, or algorithmic suggestions
- Do NOT ask them more questions - ANSWER their questions
- Be professional but conversational, like a real interviewer
- Avoid formal business language or structured formatting

Examples of good clarification answers:
- "Yes, the function should handle empty strings and return 0 for them. None values should be treated as invalid input and you can assume the function will receive valid strings."
- "For edge cases, consider what happens with empty strings, very long strings, and strings with only consonants. The function should handle these gracefully."
- "The input will always be a valid string, so you don't need to worry about None values. Focus on handling different string lengths and character types."

Keep your response direct and helpful. Answer their specific question without introducing new questions.
"""
        
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a technical interviewer providing direct answers to clarification questions. Focus ONLY on business requirements and problem understanding. Do NOT provide technical implementation details or code guidance. ANSWER their questions, don't ask more questions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "I'll clarify that for you. Please ask your specific question again if this doesn't address what you need."
    except Exception as e:
        logger.error(f"Error answering clarification question: {str(e)}")
        return "I'll clarify that for you. Please ask your specific question again if this doesn't address what you need."

@retry_with_backoff
async def generate_dynamic_feedback(question: str, answer: str, topic: str = None, feedback_type: str = "general") -> str:
    """
    Generate dynamic, concise feedback for interview answers.
    Uses focused prompts to create natural, interview-like responses.
    """
    try:
        # Different prompts based on feedback type
        if feedback_type == "gibberish":
            prompt = f"""You are a technical interviewer. The candidate gave this answer: "{answer}"

This answer appears to be random characters or doesn't address the question. Provide a brief, encouraging response (1-2 sentences max) asking them to explain what they think the problem is asking for.

Keep it conversational and natural, like a real interviewer would speak."""
        
        elif feedback_type == "brief":
            prompt = f"""You are a technical interviewer. The candidate gave this brief answer: "{answer}"

Provide a brief, encouraging response (1-2 sentences max) asking them to elaborate more on their understanding of the problem.

Keep it conversational and natural, like a real interviewer would speak."""
        
        elif feedback_type == "uncertain":
            prompt = f"""You are a technical interviewer. The candidate seems uncertain about: "{answer}"

Provide a brief, encouraging response (1-2 sentences max) that acknowledges their uncertainty but asks them to share their initial thoughts.

Keep it conversational and natural, like a real interviewer would speak."""
        
        elif feedback_type == "yes_no":
            prompt = f"""You are a technical interviewer. The candidate gave a simple yes/no answer: "{answer}"

Provide a brief, encouraging response (1-2 sentences max) asking them to explain their reasoning.

Keep it conversational and natural, like a real interviewer would speak."""
        
        else:  # general
            prompt = f"""You are a technical interviewer. The candidate's answer could be improved: "{answer}"

Provide a brief, encouraging response (1-2 sentences max) asking them to focus more on the specific question.

Keep it conversational and natural, like a real interviewer would speak."""

        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful technical interviewer providing brief, encouraging feedback. Keep responses to 1-2 sentences maximum."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100  # Keep it short
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "Could you elaborate more on your understanding of the problem?"
    except Exception as e:
        logger.error(f"Error generating dynamic feedback: {str(e)}")
        # Fallback messages
        fallbacks = {
            "gibberish": "I notice your response doesn't seem to address the question. Could you explain what you think the problem is asking for?",
            "brief": "Your answer is quite brief. Could you elaborate more on your understanding of the problem?",
            "uncertain": "It's okay to be uncertain, but try to share your initial thoughts on how you'd approach this problem.",
            "yes_no": "I need more than a simple yes/no answer. Can you explain your reasoning?",
            "general": "Your answer could be more focused on the specific question. Could you elaborate?"
        }
        return fallbacks.get(feedback_type, fallbacks["general"])