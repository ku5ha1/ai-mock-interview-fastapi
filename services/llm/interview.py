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

SYSTEM_PROMPT = """You are a senior technical interviewer conducting mock interviews.
Guidelines:
1. Never provide solutions
2. Ask follow-up questions that probe deeper into the candidate's approach
3. Challenge assumptions and ask for justification
4. After 4 good answers, transition to coding phase"""

@retry_with_backoff
async def get_next_question(
    questions: List[Dict[str, Any]],
    is_base_question: bool = False,
    topic: str = "",
    rag_context: Optional[str] = None
) -> str:
    try:
        if is_base_question:
            return "Can you walk me through your thought process on how you would approach this problem?"

        # Build conversation using full message types
        messages: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT)
        ]

        if rag_context:
            messages.append(ChatCompletionUserMessageParam(
                role="user",
                content=f"Reference Context for this topic/question:\n{rag_context}"
            ))

        for q in questions:
            if "question" in q and "answer" in q:
                # User asks question → use "user"
                messages.append(ChatCompletionUserMessageParam(
                    role="user",
                    content=q["question"]
                ))
                # Assistant responds → use "assistant"
                if q["answer"]:
                    messages.append(ChatCompletionAssistantMessageParam(
                        role="assistant",
                        content=q["answer"]
                    ))

        # Add final instruction
        messages.append(ChatCompletionUserMessageParam(
            role="user",
            content="""Based on the candidate's response, ask a follow-up question that:
1. Probes deeper into their understanding
2. Asks about specific aspects of their solution
3. Tests their technical knowledge
4. Is relevant to their previous answer"""
        ))

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=150
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or get_fallback_interview_question()

    except Exception as e:
        logger.error(f"Error generating next question: {str(e)}", exc_info=True)
        return get_fallback_interview_question()