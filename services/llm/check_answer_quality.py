"""
Answer Quality Assessment Service

This module provides AI-powered assessment of answer quality during interviews.
Evaluates responses based on clarity, correctness, and technical knowledge.
"""

from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

@retry_with_backoff
async def check_answer_quality(questions: List[Dict[str, Any]], topic: str) -> str:
    """
    Assess quality of multiple interview answers.
    Returns 'good' or 'bad' based on overall answer quality.
    """
    try:
        # Format questions and answers for assessment
        answers_text = "\n".join([
            f"Q{i+1}: {q['question']}\nA{i+1}: {q['answer']}"
            for i, q in enumerate(questions)
        ])

        prompt = f"""
Review these answers to {topic} interview questions.
Respond with only 'good' or 'bad'.

Answers:
{answers_text}

Quality:"""

        # Generate quality assessment using AI
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10
        )

        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return "good" if content and "good" in content.lower() else "bad"

    except Exception as e:
        logger.error(f"Error checking answer quality: {str(e)}")
        return "bad"

@retry_with_backoff
async def check_single_answer_quality(question: str, answer: str, topic: str, rag_context: Optional[str] = None) -> str:
    """
    Assess quality of a single interview answer.
    Uses RAG context for domain-specific evaluation.
    More lenient for approach interviews: Accepts reasonable algorithmic thinking as 'good'.
    Only marks 'bad' if answer is empty, irrelevant, or completely nonsensical.
    """
    try:
        prompt = f"""
You are an interviewer evaluating a candidate's answer.  
Your output must be exactly one word: either "good" or "bad" (lowercase, no extra text).

Strict evaluation rules:
1. First, check if the answer is meaningfully related to the given question.  
   - If it is unrelated, random, nonsensical, or gibberish → mark as "bad".
2. If related, check if the answer shows at least minimal understanding or effort.  
   - For algorithmic/problem-solving questions, even a basic or partial approach counts as "good".
3. Be lenient about completeness and correctness — only reject if:
   - Answer is empty or under 10 words without value.
   - Answer is "I don't know" or equivalent, without any attempt.
   - Answer is completely off-topic or meaningless.

Focus on relevance first — unrelated answers are always "bad".

Question: {question}  
Answer: {answer}
"""

        # Add RAG context if available for better evaluation
        if rag_context:
            prompt += f"\nReference Context:\n{rag_context}\n"
        prompt += "\nQuality:"
        
        # Generate quality assessment using AI
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        
        # More lenient parsing - default to 'good' unless explicitly marked 'bad'
        if content and "bad" in content.lower():
            return "bad"
        else:
            return "good"
            
    except Exception as e:
        logger.error(f"Error checking single answer quality: {str(e)}")
        return "good"  # Default to good on error to avoid blocking interviews