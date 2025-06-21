from services.llm.utils import (
    MODEL_NAME, client, retry_with_backoff, safe_strip, parse_json_response, get_fallback_feedback
)
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

@retry_with_backoff
async def get_feedback(conversation: List[Dict[str, Any]], user_name: str) -> dict:
    try:
        formatted = "\n".join([
            f"Interviewer: {turn.get('question', '')}\nCandidate: {turn.get('answer', '')}"
            for turn in conversation
        ])

        name_reference = f"{user_name}" if user_name else "the candidate"
        prompt = f"""
Based on the following interview conversation with {name_reference}, provide intelligent, contextual feedback in JSON format.

Be honest and critical while being constructive. If any answers are missing, incomplete, or appear to be gibberish, explicitly call this out. Do NOT give positive feedback for unclear, irrelevant, or missing answers. Only praise clear, correct, and complete answers.

Provide intelligent, contextual feedback that:
1. Analyzes the specific interview topic and questions asked
2. Gives feedback directly related to the actual conversation content
3. Suggests improvements specific to the interview context, not generic advice
4. Feels like a knowledgeable mentor giving specific, actionable advice
5. Avoids repetitive name usage and templated language
6. Connects feedback directly to the user's specific answers and the interview flow
7. Considers the progression of questions and how answers build upon each other

The feedback should feel like a real conversation with an expert who understands the interview context and is giving specific, relevant guidance.

Include:
- Summary (2-3 lines analyzing the overall interview performance in context)
- Positive Points (specific strengths demonstrated in this interview, if any)
- Points to Address (specific areas from this interview that need improvement)
- Areas for Improvement (broader areas relevant to this interview topic)

Conversation:
{formatted}

Return only valid JSON with structure:
{{
    "summary": "...",
    "positive_points": [...],
    "points_to_address": [...],
    "areas_for_improvement": [...]
}}
"""

        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"You are an expert interviewer providing intelligent, contextual feedback for {name_reference}. Focus on specific insights related to the interview conversation, avoiding generic or templated responses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return parse_json_response(content, get_fallback_feedback(user_name))

    except Exception as e:
        logger.error(f"Error getting feedback: {str(e)}")
        return get_fallback_feedback(user_name)