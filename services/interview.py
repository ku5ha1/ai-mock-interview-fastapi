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
        
        # Add conversation history - properly format the messages
        for q in questions:
            if isinstance(q, dict) and "role" in q and "content" in q:
                # Already properly formatted
                messages.append(q)
                logger.info(f"Added message to conversation: role={q['role']}, content={q['content'][:100]}...")
            else:
                # Handle legacy format or malformed messages
                logger.warning(f"Skipping malformed message: {q}")
                continue

        logger.info(f"Total messages in conversation: {len(messages)}")
        logger.info(f"Messages: {[{'role': m.get('role'), 'content': m.get('content', '')[:50]} for m in messages]}")

        # Add instruction for follow-up question generation with interview type context
        if interview_type in ["multi-line", "case-study", "approach"]:
            instruction = """This is a NON-CODING interview (multi-line / case-study / approach / verbal reasoning phase).

                            Ask a follow-up question that:
                            1. Probes deeper into the candidate's reasoning, explanation, or application
                            2. Is open-ended, analytical, or scenario-driven
                            3. Focuses on high-level thinking, structured problem-solving, and communication
                            4. Builds naturally on their previous response

                            IMPORTANT:
                            - Do NOT ask for code, syntax, or implementation details
                            - Do NOT ask the candidate to solve or write anything
                            - Do NOT ask about algorithmic strategies or technical approaches

                            Instead, focus on:
                            - Conceptual reasoning and justification
                            - Real-world implications or trade-offs
                            - Structured thinking and analytical breakdowns
                            - Thought processes, frameworks, and lessons learned
                            - Business logic and problem understanding
                            - Scenario analysis and case study exploration

                            Your follow-up should test understanding and clarity, not implementation skill.
                            """
        else:
            instruction = """This is the VERBAL PHASE of a CODING interview.

                            Ask a follow-up question that:
                            1. Digs deeper into the candidate's understanding of the problem requirements
                            2. Focuses on business logic, edge cases, and problem scope
                            3. Follows naturally from their previous answer

                            IMPORTANT:
                            - Do NOT ask for code, syntax, or implementation specifics
                            - Do NOT prompt the candidate to write or describe exact code
                            - Do NOT ask about algorithmic strategies or technical approaches

                            Instead, ask about:
                            - Problem understanding and requirements clarification
                            - Business logic and edge case considerations
                            - Input/output expectations and constraints
                            - Real-world scenarios and variations
                            - Problem scope and boundary conditions

                            The question should assess problem understanding and business logic—not technical implementation or programming skills.
                            """

        messages.append(ChatCompletionUserMessageParam(role="user", content=instruction))
        logger.info(f"Added instruction for {interview_type} interview type")

        # Generate next question using AI
        logger.info(f"Calling OpenAI API with {len(messages)} messages")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=150
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        logger.info(f"OpenAI API response: {content[:200] if content else 'None'}...")
        
        # Post-process to ensure no code-related questions
        if content:
            content = _ensure_no_code_questions(content)
            logger.info(f"Post-processed content: {content[:200]}...")
        
        final_content = content or get_fallback_interview_question()
        logger.info(f"Final question: {final_content[:200]}...")
        return final_content

    except Exception as e:
        logger.error(f"Error generating next question: {str(e)}", exc_info=True)
        return get_fallback_interview_question()


def _ensure_no_code_questions(question: str) -> str:
    """
    Post-process question to ensure it doesn't ask for code.
    Replaces code-related questions with appropriate business-focused questions.
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
            # Replace with appropriate business-focused question
            if "time complexity" in question_lower or "complexity" in question_lower:
                replacement = "What factors would affect the performance of this solution in real-world scenarios?"
            elif "edge case" in question_lower or "edge" in question_lower:
                replacement = "What edge cases or unusual scenarios should we consider for this problem?"
            elif "optimize" in question_lower or "optimization" in question_lower:
                replacement = "What aspects of this solution could be improved for better user experience?"
            elif "data structure" in question_lower:
                replacement = "What types of data would this solution need to handle?"
            elif "trade-off" in question_lower or "tradeoff" in question_lower:
                replacement = "What are the trade-offs between different approaches to this problem?"
            else:
                replacement = "Can you explain your understanding of the problem requirements in more detail?"
            
            logger.info(f"Replaced with: {replacement}")
            return replacement
    
    return question 