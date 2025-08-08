"""
Interview Service

This module handles interview question generation and conversation management.
Provides AI-powered follow-up questions based on candidate responses.
"""

from services.llm.utils import client, retry_with_backoff, safe_strip, get_fallback_interview_question
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam
)
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a Senior Technical Interviewer with 15+ years of experience conducting real-world interviews for data-focused roles, including Data Analyst, Data Scientist, Data Engineer, and ML Engineer.

You are simulating a live interview session focused on evaluating:
- Problem-solving ability
- High-level reasoning
- Conceptual clarity
- Communication under pressure

Your tone is professional and conversational. You ask only realistic follow-up questions based on the candidate’s responses. You never offer implementation guidance or solutions.
"""

@retry_with_backoff
async def get_next_question(
    questions: List[Dict[str, Any]],
    is_base_question: bool = False,
    topic: str = "",
    rag_context: Optional[str] = None,
    interview_type: str = "coding"
) -> str:
    """
    Generate next interview question based on conversation history.
    Uses AI to create contextually relevant follow-up questions.
    Supports both coding and approach interview types.
    """
    try:
        # Return standard first question for base questions
        if is_base_question:
            return "Can you walk me through your thought process on how you would approach this problem?"

        # Build conversation with system prompt and context
        messages: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT)
        ]

        # Add RAG context if available
        if rag_context:
            messages.append(ChatCompletionUserMessageParam(
                role="user",
                content=f"Reference Context for this topic/question:\n{rag_context}"
            ))
        
        # Add conversation history
        for q in questions:
            messages.append(q)  #type: ignore

        # Add instruction for follow-up question generation with interview type context
        if interview_type in ["multi-line", "case-study"]:
            instruction = """This is a NON-CODING interview (multi-line / case-study / verbal reasoning phase).

                            Ask a follow-up question that:
                            1. Probes deeper into the candidate’s reasoning, explanation, or application
                            2. Is open-ended, analytical, or scenario-driven
                            3. Focuses on high-level thinking, structured problem-solving, and communication
                            4. Builds naturally on their previous response

                            IMPORTANT:
                            - Do NOT ask for code, syntax, or implementation details
                            - Do NOT ask the candidate to solve or write anything

                            Instead, focus on:
                            - Conceptual reasoning and justification
                            - Real-world implications or trade-offs
                            - Structured thinking and analytical breakdowns
                            - Thought processes, frameworks, and lessons learned

                            Your follow-up should test understanding and clarity, not implementation skill.
                            """
        else:
            instruction = """This is the VERBAL PHASE of a CODING interview.

                            Ask a follow-up question that:
                            1. Digs deeper into the candidate’s logic, algorithmic thinking, or approach
                            2. Focuses on time-space complexity, edge cases, or trade-offs
                            3. Follows naturally from their previous answer

                            IMPORTANT:
                            - Do NOT ask for code, syntax, or implementation specifics
                            - Do NOT prompt the candidate to write or describe exact code

                            Instead, ask about:
                            - High-level algorithmic strategy
                            - Time and space efficiency
                            - Data structure choices and rationale
                            - Handling of edge cases or input variation
                            - Underlying assumptions and optimization strategies

                            The question should assess problem-solving depth—not programming fluency.
                            """


        messages.append(ChatCompletionUserMessageParam(role="user", content=instruction))

        # Generate next question using AI
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=150
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        
        # Post-process to ensure no code-related questions
        if content:
            content = _ensure_no_code_questions(content)
        
        return content or get_fallback_interview_question()

    except Exception as e:
        logger.error(f"Error generating next question: {str(e)}", exc_info=True)
        return get_fallback_interview_question()


def _ensure_no_code_questions(question: str) -> str:
    """
    Post-process question to ensure it doesn't ask for code.
    Replaces code-related questions with appropriate conceptual questions.
    """
    question_lower = question.lower()
    
    # Keywords that indicate code-related questions
    code_keywords = [
        "write code", "type code", "implement", "code snippet", "syntax",
        "write a function", "write the code", "show me the code",
        "provide code", "give me code", "write out", "code it",
        "implement this", "write the implementation", "show the code"
    ]
    
    # Check if question contains code-related keywords
    for keyword in code_keywords:
        if keyword in question_lower:
            logger.warning(f"Detected code-related question, replacing: {question}")
            # Replace with appropriate conceptual question
            if "time complexity" in question_lower or "complexity" in question_lower:
                replacement = "What's the time and space complexity of your approach?"
            elif "edge case" in question_lower or "edge" in question_lower:
                replacement = "What edge cases should we consider with this approach?"
            elif "optimize" in question_lower or "optimization" in question_lower:
                replacement = "How would you optimize this solution?"
            elif "data structure" in question_lower:
                replacement = "What data structures would you use and why?"
            elif "trade-off" in question_lower or "tradeoff" in question_lower:
                replacement = "What are the trade-offs of your approach?"
            else:
                replacement = "Can you explain your approach in more detail?"
            
            logger.info(f"Replaced with: {replacement}")
            return replacement
    
    return question 