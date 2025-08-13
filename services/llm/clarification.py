"""
Clarification Service

This module provides AI-powered clarification responses during coding interviews.
Helps candidates understand problems better without giving away solutions.
"""

from services.llm.utils import client, retry_with_backoff, safe_strip, get_fallback_clarification
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
import logging
from typing import Union

logger = logging.getLogger(__name__)

@retry_with_backoff
async def get_clarification(main_question: str, clarification_request: str) -> str:
    """
    Generate clarification response for coding interview questions.
    Provides helpful guidance on business requirements without revealing technical solutions.
    Focuses ONLY on clarifying problem understanding, NOT on implementation details.
    """
    try:
        # Build messages for clarification generation
        messages = [
            ChatCompletionSystemMessageParam(
                role="system",
                content="You are a senior technical interviewer providing clarification. Your role is to clarify business requirements and problem understanding ONLY. Do NOT provide any technical implementation details, code guidance, or algorithmic suggestions. Focus on helping the candidate understand what the problem is asking for, not how to solve it. Maintain a professional, conversational tone and be encouraging but maintain the interview atmosphere. Keep your responses natural and conversational, like a real interviewer would speak. Avoid formal business language or structured formatting."
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=f"""Main question: {main_question}
Clarification request: {clarification_request}

Provide clarification that focuses ONLY on:
1. Business requirements clarification
2. Problem scope and boundaries
3. Input/output expectations
4. Edge case considerations (business logic only)

Do NOT provide:
- Code examples or implementation details
- Algorithmic approaches or strategies
- Technical solutions or optimizations
- Step-by-step implementation guidance

Focus on helping the candidate understand WHAT the problem requires, not HOW to solve it.

Keep your response conversational and natural, like a real interviewer would speak."""
            )
        ]

        # Generate clarification using AI
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=150
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or get_fallback_clarification()

    except Exception as e:
        logger.error(f"Error generating clarification: {str(e)}")
        return get_fallback_clarification()