from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip, parse_json_response, get_fallback_analysis
from typing import Dict, Any
import logging
from services.rag.retriever_factory import get_rag_retriever
import asyncio

logger = logging.getLogger(__name__)

class ApproachAnalysisService:
    def __init__(self):
        self.client = client
        logger.info("ApproachAnalysisService using shared OpenAI client")

    async def _get_context(self, question: str, top_k: int = 2) -> str:
        """Retrieve and format relevant context from RAG system"""
        try:
            retriever = await get_rag_retriever()
            if retriever is None:
                logger.warning("RAGRetriever not initialized")
                return ""
            context_chunks = await retriever.retrieve_context(question, top_k=top_k)
            return "\n\n".join(context_chunks)
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return ""

    @retry_with_backoff
    async def analyze_approach(self, question: str, user_answer: str, user_name: str = None, previous_attempt: dict = None, personalized_guidance: str = None, user_patterns: Any = None) -> Dict[str, Any]:
        try:
            # Get relevant context from RAG
            context = await self._get_context(question)

            # Enhanced personalization context
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

            # Build final prompt with or without context
            name_reference = f"{user_name}" if user_name else "the candidate"
            prompt = f"""
You are an expert data science and AI interviewer evaluating {name_reference}'s approach to a technical question.

{extra_context}

IMPORTANT: Use the personalization data above to tailor your feedback specifically to this candidate's demonstrated patterns, strengths, and weaknesses. Reference their performance history and learning patterns throughout your evaluation.

The goal is to simulate the feedback they'd get from a top-tier interviewer. Your feedback should reflect how they would be judged in a real technical interview.

---

Your Evaluation Framework:

Assess the candidate's response using these 6 structured feedback sections:

### 1. Structure & Clarity  
- Did they break down the problem logically and clearly?  
- Did they show a step-by-step approach or just brainstorm loosely?  
- Interviewers want clarity of thought, not speed.

### 2. 🚫 What Was Missing  
- What critical step or concept was not covered?  
- Only include what would be considered a key miss in an actual interview.  
- For example: missing evaluation metric in ML, not defining business metric in product sense, not checking nulls in SQL.

### 3. 👁️ Blind Spots  
- Subtle but important things they missed that top candidates usually catch.  
- For example: ignoring baseline model in ML, ignoring tie behavior in SQL, ignoring acquisition in product sense.  
- These often cost candidates the offer.

### 4. Historical Tracking  
- Based on past attempts, did they improve or repeat the same mistakes?  
- Pull in relevant feedback only. If none apply, say "N/A".

### 5. Interview Variations / Scenario Extensions  
- Suggest how the question could be modified in real interviews.  
- Offer 1–2 variations and how their approach would need to adapt.

### 6.  Final Interview Tip  
- End with a crisp, interview-specific coaching insight they can apply to future questions.  
- It should be tactical and relevant to this module (ML, SQL, Product, Guesstimate, etc.)

---

Current Question Info:
**Module:** [e.g., SQL / ML / Product Sense / Guesstimate]  
**Topic:** [e.g., Model Evaluation]  
**Subtopic:** [e.g., Precision Drop]  
**Question:**  
{question}

**Candidate's Response:**  
{user_answer}

---

Generate the 6 sections. Do not explain them. Keep it sharp, honest, and professional—like a real interviewer giving expert-level critique.

Context:
{context}

---

Return ONLY valid JSON in the following format:
{{
    "feedback": "...",
    "strengths": [...],
    "areas_for_improvement": [...],
    "score": number
}}
DO NOT return markdown, explanations, or any text outside the JSON object.
"""

            response = await self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": f"You are an expert interviewer providing intelligent, contextual feedback for {name_reference}. CRITICAL: You must use the provided personalization data to tailor your feedback. Reference their specific strengths, weaknesses, and performance patterns throughout your evaluation. Connect current performance to their learning history. This is not optional - it's essential for providing truly personalized feedback."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            content = safe_strip(getattr(response.choices[0].message, 'content', None))
            result = parse_json_response(content, get_fallback_analysis())

            # Log success
            logger.info(f"Successfully analyzed approach for question: {question[:50]}...")
            return result

        except Exception as e:
            logger.error(f"Error analyzing approach: {str(e)}")
            return get_fallback_analysis()