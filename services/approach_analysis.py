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
    async def analyze_approach(self, question: str, user_answer: str, user_name: str = None) -> Dict[str, Any]:
        try:
            # Get relevant context from RAG
            context = await self._get_context(question)

            # Build final prompt with or without context
            name_reference = f"{user_name}" if user_name else "the candidate"
            prompt = f"""
You are an expert data science and AI interviewer. You specialize in conducting technical interviews for data science, analytics, and ML roles at companies like Meta, Google, Airbnb, and Stripe.

Your task is to evaluate a candidate's written approach to a data science interview-style question. This is NOT about writing perfect code, but about assessing the candidate's high-level thinking, clarity, structure, and analytical depth.

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

Candidate's Prior Feedback (Last 30 Days):  
Only refer to this if directly relevant to what the candidate said.

[Insert relevant prior feedback here if available]

---

Generate the 6 sections. Do not explain them. Keep it sharp, honest, and professional—like a real interviewer giving expert-level critique.

Context:
{context}
"""

            response = await self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": f"You are an expert interviewer providing intelligent, contextual feedback for {name_reference}. Focus on specific insights related to the current question and answer, avoiding generic or templated responses."},
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