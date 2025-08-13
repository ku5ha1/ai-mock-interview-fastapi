"""
Approach Analysis Service

This module provides AI-powered analysis of user's problem-solving approaches.
Evaluates responses and provides personalized feedback based on user history.
"""

from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip, parse_json_response, get_fallback_analysis
from typing import Dict, Any
import logging
from services.rag.retriever_factory import get_rag_retriever
import asyncio

logger = logging.getLogger(__name__)

class ApproachAnalysisService:
    """
    Service for analyzing user's problem-solving approaches.
    Provides personalized feedback based on user history and patterns.
    """
    
    def __init__(self):
        self.client = client
        logger.info("ApproachAnalysisService using shared OpenAI client")

    async def _get_context(self, question: str, top_k: int = 2) -> str:
        """
        Retrieve relevant context from RAG system for question analysis.
        Optimized for performance with reduced top_k.
        """
        try:
            retriever = await get_rag_retriever()
            if retriever is None:
                logger.warning("RAGRetriever not initialized")
                return ""
            
            # Use smaller top_k for better performance
            context_chunks = await retriever.retrieve_context(question, top_k=top_k)
            
            # Limit context length for better performance
            context = "\n\n".join(context_chunks)
            if len(context) > 1000:  # Limit context to 1000 characters
                context = context[:1000] + "..."
            
            return context
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return ""

    @retry_with_backoff
    async def analyze_approach(self, question: str, user_answer: str, user_name: str = None, previous_attempt: dict = None, personalized_guidance: str = None, user_patterns: Any = None) -> Dict[str, Any]: # type: ignore
        """
        Analyze user's approach to a question and provide personalized feedback.
        Uses user history and patterns to tailor the analysis. 
        """
        try: 
            # Get relevant context from RAG system (reduced top_k for performance)
            context = await self._get_context(question, top_k=2)

            # Build personalized context from user history (optimized)
            extra_context = self._build_optimized_context(
                previous_attempt, personalized_guidance, user_patterns
            )

            # Build final prompt with personalized context (optimized)
            name_reference = f"{user_name}" if user_name else "the candidate"
            prompt = f"""
You are an expert data science and AI interviewer evaluating {name_reference}'s approach to a technical question.

{extra_context}

IMPORTANT: Use the personalization data above to tailor your feedback specifically to this candidate's demonstrated patterns, strengths, and weaknesses. Reference their performance history and learning patterns throughout your evaluation.

Your Evaluation Framework:

### 1. Structure & Clarity  
- Did they break down the problem logically and clearly?  
- Did they show a step-by-step approach or just brainstorm loosely?  

### 2. 🚫 What Was Missing  
- What critical step or concept was not covered?  
- Only include what would be considered a key miss in an actual interview.  

### 3. 👁️ Blind Spots  
- Subtle but important things they missed that top candidates usually catch.  
- These often cost candidates the offer.  

### 4. Historical Tracking  
- Based on past attempts, did they improve or repeat the same mistakes?  
- If none apply, say "N/A".  

### 5. Interview Variations  
- Suggest 1–2 variations and how their approach would need to adapt.  

### 6. Final Interview Tip  
- End with a crisp, interview-specific coaching insight they can apply to future questions.  

Current Question: {question}
Candidate's Response: {user_answer}

Context: {context}

Return ONLY valid JSON:
{{
    "feedback": "...",
    "strengths": [...],
    "areas_for_improvement": [...],
    "score": number
}}
"""

            # Generate analysis using AI (reduced max_tokens for performance)
            response = await self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": f"You are an expert interviewer providing intelligent, contextual feedback for {name_reference}. Use the provided personalization data to tailor your feedback. Reference their specific strengths, weaknesses, and performance patterns."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800  # Reduced from 1000 for better performance
            )

            content = safe_strip(getattr(response.choices[0].message, 'content', None))
            result = parse_json_response(content, get_fallback_analysis())

            # Log success
            logger.info(f"Successfully analyzed approach for question: {question[:50]}...")
            return result

        except Exception as e:
            logger.error(f"Error analyzing approach: {str(e)}")
            return get_fallback_analysis()
    
    def _build_optimized_context(self, previous_attempt: dict = None, personalized_guidance: str = None, user_patterns: Any = None) -> str:
        """
        Build optimized context string to reduce prompt length and improve performance.
        """
        extra_context = ""
        
        if previous_attempt:
            extra_context += f"Previous attempt: Answer: {previous_attempt.get('answer', '')[:100]}... Result: {previous_attempt.get('result', '')}. Output: {previous_attempt.get('output', '')[:100]}...\n"
        
        if user_patterns:
            patterns = user_patterns
            extra_context += f"Performance: Avg score {patterns.get('average_score', 'N/A')}/10, {patterns.get('completion_rate', 0)*100:.0f}% completion\n"
            extra_context += f"Recent topics: {', '.join(patterns.get('recent_topics', [])[:3])}\n"
            extra_context += f"Performance trend: {patterns.get('performance_trend', [])[-3:]}\n"
            
            if patterns.get('strengths'):
                extra_context += f"Strengths: {', '.join(patterns['strengths'][:2])}\n"
            
            if patterns.get('common_weaknesses'):
                extra_context += f"Areas for improvement: {', '.join(patterns['common_weaknesses'][:2])}\n"
        
        if personalized_guidance:
            guidance = personalized_guidance.replace("You often struggle with:", "Areas:").replace("Your strengths include:", "Strengths:").replace("Keep leveraging these in your answers.", "")
            extra_context += f"Guidance: {guidance[:200]}...\n"
        
        extra_context += "Use this data to tailor feedback. Connect current performance to past trends.\n\n"
        return extra_context