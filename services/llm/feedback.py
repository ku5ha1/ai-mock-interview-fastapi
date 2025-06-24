from services.llm.utils import (
    MODEL_NAME, client, retry_with_backoff, safe_strip, parse_json_response, get_fallback_feedback
)
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

@retry_with_backoff
async def get_feedback(conversation: List[Dict[str, Any]], user_name: str, previous_attempt: dict = None, personalized_guidance: str = None, user_patterns: Any = None) -> dict:
    try:
        formatted = "\n".join([
            f"Interviewer: {turn.get('question', '')}\nCandidate: {turn.get('answer', '')}"
            for turn in conversation
        ])

        name_reference = f"{user_name}" if user_name else "the candidate"
        extra_context = ""
        
        if previous_attempt:
            extra_context += f"The candidate previously attempted this question. Their answer was: {previous_attempt.get('answer', '')}. The result was: {previous_attempt.get('result', '')}. The output was: {previous_attempt.get('output', '')}. Please naturally incorporate this information into your feedback, comparing the current and previous attempts if relevant.\n"
        
        # Enhanced personalization context
        if personalized_guidance or user_patterns:
            extra_context += "PERSONALIZATION CONTEXT - Use this to tailor your feedback specifically to this candidate:\n"
            
            if user_patterns:
                patterns = user_patterns
                extra_context += f"- Performance: Average score {patterns.get('average_score', 'N/A')}/10, {patterns.get('completion_rate', 0)*100:.0f}% session completion rate\n"
                extra_context += f"- Recent topics: {', '.join(patterns.get('recent_topics', []))}\n"
                extra_context += f"- Performance trend (last 5): {patterns.get('performance_trend', [])}\n"
                
                # Topic-specific performance
                if patterns.get('topic_specific_performance'):
                    topic_perf = patterns['topic_specific_performance']
                    if topic_perf.get('scores'):
                        avg_topic = sum(topic_perf['scores']) / len(topic_perf['scores'])
                        extra_context += f"- Topic-specific average: {avg_topic:.1f}/10\n"
                
                # Question-specific history
                if patterns.get('question_specific_history'):
                    q_history = patterns['question_specific_history']
                    extra_context += f"- Previous attempt at this question: Result {q_history.get('previous_result', 'N/A')}\n"
                
                if patterns.get('strengths'):
                    extra_context += f"- Demonstrated strengths: {', '.join(patterns['strengths'][:3])}\n"
                
                if patterns.get('common_weaknesses'):
                    extra_context += f"- Areas needing improvement: {', '.join(patterns['common_weaknesses'][:3])}\n"
                
                # Response patterns
                avg_length = patterns.get('avg_response_length', 0)
                if avg_length > 0:
                    extra_context += f"- Average response length: {avg_length:.0f} words\n"
            
            if personalized_guidance:
                # Clean up the personalized guidance to be more concise
                guidance = personalized_guidance.replace("You often struggle with:", "Areas for improvement:").replace("Your strengths include:", "Strengths:").replace("Keep leveraging these in your answers.", "")
                extra_context += f"- Personalized guidance: {guidance}\n"
            
            extra_context += "IMPORTANT: Reference these patterns in your feedback. Connect current performance to past trends. Be specific about how they're improving or repeating patterns. Use the performance trend and topic-specific data to provide targeted advice.\n\n"

        # Pre-check for gibberish or empty answers
        all_answers = [turn.get('answer', '').strip() for turn in conversation]
        if all(not ans or len(ans.split()) < 3 for ans in all_answers):
            return {
                "summary": f"{user_name}, your responses were unclear, incomplete, or did not address the questions. Please review the basics and try to provide more relevant, structured answers.",
                "positive_points": [],
                "points_to_address": ["Most answers were missing, irrelevant, or nonsensical."],
                "areas_for_improvement": ["Focus on understanding the question and providing clear, relevant responses."]
            }

        prompt = f"""
Based on the following interview conversation with {name_reference}, provide intelligent, contextual feedback in JSON format.

{extra_context}
When writing the feedback, naturally refer to the candidate by their name ("{user_name}") where appropriate (e.g., in the summary or advice), but do not include the name as a separate field in the JSON.

Be honest, direct, and critical while being constructive. If any answers are missing, incomplete, irrelevant, or appear to be gibberish or nonsensical, explicitly state this in the summary and do not list any positive points or strengths. Leave the positive_points array empty in such cases. Do NOT give positive feedback or mention strengths unless they are clearly demonstrated in the answers. If the candidate's responses are poor, unclear, or off-topic, do not sugarcoat or provide generic praise—be specific about what was lacking.

Provide intelligent, contextual feedback that:
1. Analyzes the specific interview topic and questions asked
2. Gives feedback directly related to the actual conversation content
3. Suggests improvements specific to the interview context, not generic advice
4. Feels like a knowledgeable mentor giving specific, actionable advice
5. Avoids repetitive name usage and templated language
6. Connects feedback directly to the user's specific answers and the interview flow
7. Considers the progression of questions and how answers build upon each other
8. References their personal learning patterns and performance history when relevant

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
                {"role": "system", "content": f"You are an expert interviewer providing intelligent, contextual feedback for {name_reference}. Focus on specific insights related to the interview conversation, avoiding generic or templated responses. Use personalization data to tailor feedback to the candidate's specific patterns and learning history."},
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