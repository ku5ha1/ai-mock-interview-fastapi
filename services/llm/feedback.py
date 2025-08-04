"""
Feedback Generation Service

This module provides AI-powered feedback generation for interview sessions.
Analyzes conversation history and provides personalized feedback with recommendations.
"""

from services.llm.utils import (
    MODEL_NAME, client, retry_with_backoff, safe_strip, parse_json_response, get_fallback_feedback
)
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

@retry_with_backoff
async def get_feedback(conversation: List[Dict[str, Any]], user_name: str, previous_attempt: dict = None, personalized_guidance: str = None, user_patterns: Any = None, code_data: dict = None) -> dict:
    """
    Generate comprehensive feedback for interview session.
    Uses conversation history and user patterns for personalized feedback.
    Includes code assessment for coding interviews.
    """
    try:
        # Format conversation for analysis
        formatted = "\n".join([
            f"Interviewer: {turn.get('question', '')}\nCandidate: {turn.get('answer', '')}"
            for turn in conversation
        ])

        name_reference = f"{user_name}" if user_name else "the candidate"
        extra_context = ""
        
        # Add code assessment context if available
        if code_data:
            extra_context += f"""
CODE ASSESSMENT:
User Code: {code_data.get('code', '')}
User Output: {code_data.get('output', '')}
Expected Solution: {code_data.get('solutionCode', '')}
Expected Output: {code_data.get('expectedOutput', '')}

Analyze the code for:
- Correctness and functionality
- Code quality and best practices
- Performance and optimization
- Integration with verbal interview performance
- Specific technical issues (missing imports, incorrect syntax, wrong calculations)
- Partial understanding and correct elements
- Specific suggestions for improvement

IMPORTANT: Be specific about technical issues while recognizing any correct elements or partial understanding. Identify exact problems like missing imports, incorrect calculations, or syntax errors.

"""
        
        # Add previous attempt context if available
        if previous_attempt:
            extra_context += f"The candidate previously attempted this question. Their answer was: {previous_attempt.get('answer', '')}. The result was: {previous_attempt.get('result', '')}. The output was: {previous_attempt.get('output', '')}. Please naturally incorporate this information into your feedback, comparing the current and previous attempts if relevant.\n"
        
        # Build personalized context from user patterns
        if personalized_guidance or user_patterns:
            extra_context += "PERSONALIZATION CONTEXT - Use this to tailor your feedback specifically to this candidate:\n"
            
            if user_patterns:
                patterns = user_patterns
                extra_context += f"- Performance: Average score {patterns.get('average_score', 'N/A')}/10, {patterns.get('completion_rate', 0)*100:.0f}% session completion rate\n"
                extra_context += f"- Recent topics: {', '.join(patterns.get('recent_topics', []))}\n"
                extra_context += f"- Performance trend (last 5): {patterns.get('performance_trend', [])}\n"
                
                # Add topic-specific performance data
                if patterns.get('topic_specific_performance'):
                    topic_perf = patterns['topic_specific_performance']
                    if topic_perf.get('scores'):
                        avg_topic = sum(topic_perf['scores']) / len(topic_perf['scores'])
                        extra_context += f"- Topic-specific average: {avg_topic:.1f}/10\n"
                
                # Add question-specific history
                if patterns.get('question_specific_history'):
                    q_history = patterns['question_specific_history']
                    extra_context += f"- Previous attempt at this question: Result {q_history.get('previous_result', 'N/A')}\n"
                
                if patterns.get('strengths'):
                    extra_context += f"- Demonstrated strengths: {', '.join(patterns['strengths'][:3])}\n"
                
                if patterns.get('common_weaknesses'):
                    extra_context += f"- Areas needing improvement: {', '.join(patterns['common_weaknesses'][:3])}\n"
                
                # Add response pattern analysis
                avg_length = patterns.get('avg_response_length', 0)
                if avg_length > 0:
                    extra_context += f"- Average response length: {avg_length:.0f} words\n"
            
            if personalized_guidance:
                # Clean up the personalized guidance to be more concise
                guidance = personalized_guidance.replace("You often struggle with:", "Areas for improvement:").replace("Your strengths include:", "Strengths:").replace("Keep leveraging these in your answers.", "")
                extra_context += f"- Personalized guidance: {guidance}\n"
            
            extra_context += "IMPORTANT: Reference these patterns in your feedback. Connect current performance to past trends. Be specific about how they're improving or repeating patterns. Use the performance trend and topic-specific data to provide targeted advice.\n\n"

        # Check for poor quality answers and return early feedback
        all_answers = [turn.get('answer', '').strip() for turn in conversation]
        if all(not ans or len(ans.split()) < 3 for ans in all_answers):
            return {
                "summary": f"{user_name}, your responses were unclear, incomplete, or did not address the questions. Please review the basics and try to provide more relevant, structured answers.",
                "positive_points": [],
                "points_to_address": ["Most answers were missing, irrelevant, or nonsensical."],
                "areas_for_improvement": ["Focus on understanding the question and providing clear, relevant responses."],
                "metrics": {}
            }

        # Build comprehensive feedback prompt
        prompt = f"""
Based on the following interview conversation with {name_reference}, provide intelligent, contextual feedback in JSON format.

{extra_context}
When writing the feedback, naturally refer to the candidate by their name ("{user_name}") where appropriate (e.g., in the summary or advice), but do not include the name as a separate field in the JSON.

Be honest, direct, and critical while being constructive. Provide balanced feedback that:
1. Recognizes partial understanding and effort, even if incomplete
2. Identifies specific technical issues and areas for improvement
3. Gives credit for demonstrated knowledge while pointing out gaps
4. Provides specific, actionable suggestions for improvement

IMPORTANT GUIDELINES:
- If the candidate shows ANY understanding or effort, include positive points
- Be specific about what was done correctly vs. what needs improvement
- For coding interviews: Analyze the actual code structure, syntax, and logic
- Provide constructive criticism that helps the candidate improve
- Avoid overly harsh assessments that don't recognize partial understanding

Provide intelligent, contextual feedback that:
1. Analyzes the specific interview topic and questions asked
2. Gives feedback directly related to the actual conversation content
3. Suggests improvements specific to the interview context, not generic advice
4. Feels like a knowledgeable mentor giving specific, actionable advice
5. Avoids repetitive name usage and templated language
6. Connects feedback directly to the user's specific answers and the interview flow
7. Considers the progression of questions and how answers build upon each other
8. References their personal learning patterns and performance history when relevant
9. Evaluates problem-solving ability, reasoning clarity, and technical communication
10. Assesses awareness of trade-offs and edge case handling
11. Considers domain-specific evaluation criteria (Python data analysis, SQL, algorithms, etc.)
"""

        # Add code assessment instructions if code data is available
        if code_data:
            prompt += f"""
12. Evaluates code implementation quality, correctness, and best practices
13. Integrates verbal interview performance with code implementation
14. Provides specific feedback on code structure, efficiency, and readability
15. Assesses whether the code matches the approach discussed in the verbal phase
16. Identifies specific technical issues (missing imports, incorrect calculations, etc.)
17. Recognizes partial understanding and correct elements in the code
18. Provides specific suggestions for fixing identified issues

IMPORTANT: For coding interviews, provide comprehensive feedback that covers both verbal reasoning and code implementation. Connect the code quality to the verbal discussion and provide specific suggestions for improvement. Be specific about technical issues while recognizing any correct elements or partial understanding.
"""

        prompt += f"""

The feedback should feel like a real conversation with an expert who understands the interview context and is giving specific, relevant guidance.

Evaluation Criteria:
- Clarity of communication and reasoning
- Correctness of logic and approach
- Ability to reason under pressure
- Awareness of trade-offs and edge cases
- Domain-specific technical knowledge
- Problem-solving methodology"""

        # Add code evaluation criteria if code data is available
        if code_data:
            prompt += f"""
- Code correctness and functionality
- Code quality and best practices
- Performance and optimization
- Integration of verbal reasoning with code implementation
- Specific technical accuracy (syntax, imports, calculations)
- Partial understanding recognition"""

        prompt += f"""

Include:
- Summary (2-3 lines analyzing the overall interview performance in context)
- Positive Points (specific strengths demonstrated in this interview, even if partial)
- Points to Address (specific areas from this interview that need improvement)
- Areas for Improvement (broader areas relevant to this interview topic)
- Metrics (a dictionary of key performance indicators, comparing to past performance if available. For example: {{"technical_skills": "improved by 15%", "communication": "consistent"}})

Conversation:
{formatted}

Return only valid JSON with structure:
{{
    "summary": "...",
    "positive_points": [...],
    "points_to_address": [...],
    "areas_for_improvement": [...],
    "metrics": {{...}}
}}
"""

        # Generate feedback using AI
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
        
        # Parse and validate response
        parsed_response = parse_json_response(content, get_fallback_feedback(user_name))
        
        # Ensure 'metrics' field is always present
        if 'metrics' not in parsed_response:
            parsed_response['metrics'] = {}
            
        return parsed_response

    except Exception as e:
        logger.error(f"Error getting feedback: {str(e)}")
        return get_fallback_feedback(user_name)