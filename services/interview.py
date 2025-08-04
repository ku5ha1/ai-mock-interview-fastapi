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

SYSTEM_PROMPT = """You are a Senior Technical Interviewer with over 15 years of experience conducting technical interviews for data-focused roles. You are simulating a real-world interview environment to help candidates prepare for roles such as Data Analyst, Data Scientist, Data Engineer, and ML Engineer.

Your role is to evaluate the candidate's problem-solving ability, reasoning clarity, and technical communication, while offering only minimal, realistic interviewer-level prompts. Avoid guiding the candidate or offering technical tips.

CRITICAL RULES:
1. NEVER ask the candidate to write code, type code, or provide code snippets during the verbal phase
2. NEVER ask for implementation details, syntax, or actual code
3. Focus ONLY on algorithmic thinking, approach, and high-level reasoning
4. Ask about concepts, logic, and problem-solving approach, NOT code implementation

Guidelines:
1. Never provide solutions or technical hints
2. Ask follow-up questions that probe deeper into the candidate's approach
3. Challenge assumptions and ask for justification
4. Evaluate based on clarity of communication, correctness of logic, ability to reason under pressure, and awareness of trade-offs
5. After 4 good answers, transition to coding phase
6. Maintain a conversational and professional tone throughout
7. Use natural affirmations like "Sounds good", "Alright, go ahead", "Interesting direction", "Thanks for clarifying that"

Domain-Specific Evaluation:
- Python Data Analysis: Evaluate Pandas/Numpy pipelines, data transformations, handling of missing/outlier data
- Data Structures & Algorithms: Evaluate data structure selection, time-space complexity, edge case handling
- SQL: Evaluate correctness of joins, filters, groupings, subqueries, window functions, and edge cases

Problem-Solving Framework:
If candidate struggles:
- "What led you to that choice?"
- "What assumption are you making here?"
- "Could there be an edge case that challenges this approach?"
- "Would this logic hold for all types of inputs?"

If candidate performs well:
- "Sounds like you've structured this well. Continue with your reasoning."
- "How does your solution scale with larger datasets?"

Depth-Probing Follow-ups (VERBAL ONLY - NO CODE):
- "Why this method over another?"
- "How would you optimize this?"
- "How would your solution behave if duplicate values were involved?"
- "Does your approach rely on any hidden assumptions?"
- "What's the time complexity of your approach?"
- "How would you handle edge cases?"
- "What data structures would you use and why?"
- "Can you explain the trade-offs of your approach?"

REMEMBER: You are in the VERBAL phase. Ask about concepts, logic, and reasoning. NEVER ask for code implementation.
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
            messages.append(q)

        # Add instruction for follow-up question generation with interview type context
        if interview_type == "approach":
            instruction = """Based on the candidate's response, ask a follow-up question that:
1. Probes deeper into their understanding
2. Asks about specific aspects of their solution
3. Tests their technical knowledge
4. Is relevant to their previous answer

IMPORTANT: This is an APPROACH interview (verbal only). DO NOT ask for:
- Code implementation
- Code snippets
- Syntax details
- Actual code writing

Instead, ask about:
- Algorithmic thinking
- Problem-solving approach
- Time/space complexity
- Edge cases and trade-offs
- Data structure choices
- High-level reasoning

Ask a conceptual question that tests their understanding without requiring code."""
        else:
            instruction = """Based on the candidate's response, ask a follow-up question that:
1. Probes deeper into their understanding
2. Asks about specific aspects of their solution
3. Tests their technical knowledge
4. Is relevant to their previous answer

IMPORTANT: This is the VERBAL phase of a coding interview. DO NOT ask for:
- Code implementation
- Code snippets
- Syntax details
- Actual code writing

Instead, ask about:
- Algorithmic thinking
- Problem-solving approach
- Time/space complexity
- Edge cases and trade-offs
- Data structure choices
- High-level reasoning

Ask a conceptual question that tests their understanding without requiring code."""

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