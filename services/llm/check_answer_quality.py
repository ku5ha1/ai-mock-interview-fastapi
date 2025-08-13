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
        # Pre-filter obviously good answers to avoid unnecessary AI calls
        answer_text = answer.strip().lower()
        
        # If answer is too short, check if it's meaningful
        if len(answer_text) < 15:
            # Check if it's a meaningful short answer
            meaningful_short_answers = [
                "use a hash table", "binary search", "dynamic programming", 
                "two pointers", "sliding window", "dfs", "bfs", "recursion",
                "sort first", "use a stack", "use a queue", "greedy approach"
            ]
            if any(phrase in answer_text for phrase in meaningful_short_answers):
                return "good"
        
        # Check for common good answer patterns
        good_patterns = [
            "create a function", "iterate through", "check if", "maintain a counter",
            "convert to", "handle case", "return the", "for each", "while loop",
            "if statement", "else", "algorithm", "approach", "strategy", "method",
            "step by step", "first", "then", "finally", "initialize", "declare"
        ]
        
        if any(pattern in answer_text for pattern in good_patterns):
            return "good"
        
        # Check for obviously bad answers
        bad_patterns = [
            "i don't know", "idk", "no idea", "not sure", "random", "gibberish",
            "asdf", "qwerty", "test", "hello world", "lorem ipsum"
        ]
        
        if any(pattern in answer_text for pattern in bad_patterns):
            return "bad"
        
        # If answer is very long (>200 words), it's likely good
        if len(answer_text) > 200:
            return "good"
        
        # Check for gibberish patterns (before AI assessment)
        if len(answer_text) < 10:
            # Very short answers are likely gibberish unless they contain meaningful content
            # Check if it's just random characters without meaningful patterns
            meaningful_short_words = ["ok", "yes", "no", "okay", "sure", "fine", "maybe", "idk", "idc"]
            if not any(word in answer_text for word in meaningful_short_words):
                # Check for random character patterns
                if len(answer_text) < 5:  # Very short answers are suspicious
                    # Check if it's just random letters (no vowels, no meaningful patterns)
                    vowels = "aeiou"
                    if not any(vowel in answer_text for vowel in vowels):
                        return "bad"
                    # Check if it's just repeated patterns
                    if len(set(answer_text)) < len(answer_text) * 0.6:  # Too many repeated characters
                        return "bad"
        
        # For algorithmic questions, be very lenient
        algorithmic_keywords = [
            "algorithm", "function", "loop", "iterate", "check", "count", "find",
            "solve", "approach", "method", "strategy", "step", "process"
        ]
        
        if any(keyword in answer_text for keyword in algorithmic_keywords):
            return "good"
        
        # If we reach here, use AI for final assessment with a more lenient prompt
        prompt = f"""
You are an interviewer evaluating a candidate's answer to a technical question.
Your output must be exactly one word: either "good" or "bad" (lowercase, no extra text).

Evaluation guidelines - be GENEROUS and lenient:
- Mark as "good" if the answer shows ANY understanding or effort
- For algorithmic questions, even basic approaches are "good"
- For problem-solving, any logical thinking is "good"
- Only mark as "bad" if completely nonsensical, off-topic, or empty

Question: {question}
Answer: {answer}

Quality:"""

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
        
        # Very lenient parsing - default to 'good' unless explicitly marked 'bad'
        if content and "bad" in content.lower():
            return "bad"
        else:
            return "good"
            
    except Exception as e:
        logger.error(f"Error checking single answer quality: {str(e)}")
        return "good"  # Default to good on error to avoid blocking interviews