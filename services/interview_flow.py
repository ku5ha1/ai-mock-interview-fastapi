"""
Interview Flow Management Service

This module handles the core interview flow logic, including:
- Answer quality assessment and feedback generation
- Interview phase transitions
- Question progression logic
- Clarification management
"""

import logging
from typing import Dict, Any, Optional, Tuple
from services.llm.check_answer_quality import check_single_answer_quality
from services.llm.utils import generate_dynamic_feedback
from services.interview import get_next_question
from services.db import add_follow_up_question, transition_to_coding_phase

logger = logging.getLogger(__name__)

# Configuration for clarification limits
CLARIFICATION_LIMITS = {
    "max_per_question": 2,      # Maximum clarifications per individual question
    "max_per_session": 5,       # Maximum total clarifications for entire session
    "warn_at_percentage": 0.8   # Warn user when they reach 80% of limit
}

class InterviewFlowManager:
    """Manages interview flow logic and state transitions."""
    
    def __init__(self, session_data: Dict[str, Any], session_id: str):
        self.session_data = session_data
        self.session_id = session_id
        self.interview_type = session_data.get("interview_type", "approach")
        self.current_phase = session_data["current_phase"]
    
    async def handle_coding_phase(self, answer: str, is_clarification: bool) -> Dict[str, Any]:
        """Handle coding phase logic (clarifications or final code submission)."""
        if is_clarification:
            return await self._handle_coding_clarification(answer)
        else:
            return await self._handle_final_code_submission(answer)
    
    async def _handle_coding_clarification(self, answer: str) -> Dict[str, Any]:
        """Handle clarification requests during coding phase."""
        coding_clarification_count = self.session_data.get("coding_clarification_count", 0)
        max_coding_clarifications = CLARIFICATION_LIMITS["max_per_question"]
        
        if coding_clarification_count >= max_coding_clarifications:
            clarification_resp = "You've reached the maximum clarification attempts. Let's proceed with coding based on your current understanding."
        else:
            from services.llm.utils import answer_clarification_question
            base_question = self.session_data["questions"][0]["question"]
            clarification_resp = await answer_clarification_question(
                base_question, answer, self.session_data["topic"]
            )
            
            # Add clarification count information
            remaining_clarifications = max_coding_clarifications - coding_clarification_count
            if remaining_clarifications > 0:
                clarification_resp += f"\n\n[Note: You have {remaining_clarifications} more clarification attempt{'s' if remaining_clarifications > 1 else ''} before coding.]"
            else:
                clarification_resp += f"\n\n[Note: This is your final clarification attempt before coding.]"
        
        return {
            "question": clarification_resp,
            "clarification": True,
            "ready_to_code": True,
            "clarification_count": coding_clarification_count + 1,
            "max_clarifications": max_coding_clarifications
        }
    
    async def _handle_final_code_submission(self, answer: str) -> Dict[str, Any]:
        """Handle final code submission during coding phase."""
        return {"message": "Code submitted successfully. You can now generate feedback."}
    
    async def process_answer(self, answer: str, rag_context: str) -> Dict[str, Any]:
        """Process user answer and determine next action."""
        # Get last answered question
        last_answered_question = self._get_last_answered_question()
        
        # Check answer quality
        quality = await self._assess_answer_quality(last_answered_question, rag_context)
        
        # Handle clarification limits
        quality = await self._handle_clarification_limits(quality, last_answered_question)
        
        # Process based on interview type and quality
        if self.interview_type == "coding":
            return await self._handle_coding_interview_flow(quality, last_answered_question, rag_context)
        else:
            return await self._handle_approach_interview_flow(quality, last_answered_question, rag_context)
    
    def _get_last_answered_question(self) -> Dict[str, Any]:
        """Get the last question that was answered by the user."""
        for q in reversed(self.session_data["follow_up_questions"]):
            if q.get("answer"):
                return q
        return self.session_data["follow_up_questions"][-1]
    
    async def _assess_answer_quality(self, question_data: Dict[str, Any], rag_context: str) -> str:
        """Assess the quality of the user's answer."""
        quality = await check_single_answer_quality(
            question=question_data["question"],
            answer=question_data.get("answer", ""),
            topic=self.session_data["topic"],
            rag_context=rag_context
        )
        
        logger.info(f"Session {self.session_id}: Answer quality check - Question: '{question_data['question'][:100]}...' Answer: '{question_data.get('answer', '')[:100]}...' Quality: {quality}")
        
        return quality
    
    async def _handle_clarification_limits(self, quality: str, question_data: Dict[str, Any]) -> str:
        """Handle clarification limits and force progression if needed."""
        clarification_count = question_data.get("clarification_count", 0)
        total_clarifications = sum(q.get("clarification_count", 0) for q in self.session_data["follow_up_questions"])
        
        if clarification_count >= CLARIFICATION_LIMITS["max_per_question"]:
            logger.info(f"Session {self.session_id}: Reached maximum clarifications for current question")
            quality = "good"  # Override quality to allow progression
        elif total_clarifications >= CLARIFICATION_LIMITS["max_per_session"]:
            logger.info(f"Session {self.session_id}: Reached maximum total clarifications for entire session")
            quality = "good"  # Override quality to allow progression
        
        return quality
    
    async def _handle_coding_interview_flow(self, quality: str, question_data: Dict[str, Any], rag_context: str) -> Dict[str, Any]:
        """Handle coding interview flow logic."""
        if quality == "bad":
            return await self._generate_coding_feedback(question_data)
        
        # Count properly answered questions
        properly_answered_questions = self._count_properly_answered_questions()
        
        if properly_answered_questions < 5:
            return await self._generate_next_question(rag_context)
        else:
            await transition_to_coding_phase(self.session_id)
            return {
                "question": "Great! Now let's move to the coding phase. You can start coding",
                "clarification": True,
                "ready_to_code": True
            }
    
    async def _handle_approach_interview_flow(self, quality: str, question_data: Dict[str, Any], rag_context: str) -> Dict[str, Any]:
        """Handle approach interview flow logic."""
        if quality == "bad":
            return await self._generate_approach_feedback(question_data)
        
        # Count answered questions
        properly_answered_questions = sum(1 for q in self.session_data["follow_up_questions"] if q.get("answer"))
        
        if properly_answered_questions < 7:
            return await self._generate_next_question(rag_context)
        else:
            return {
                "question": "Great discussion! You can submit the session and check your feedback.",
                "session_complete": True
            }
    
    def _count_properly_answered_questions(self) -> int:
        """Count questions that were properly answered (not clarifications)."""
        return sum(1 for q in self.session_data["follow_up_questions"] 
                  if q.get("answer") and q.get("clarification_count", 0) == 0)
    
    async def _generate_next_question(self, rag_context: str) -> Dict[str, Any]:
        """Generate the next follow-up question."""
        conversation_history = self._build_conversation_history()
        
        next_question = await get_next_question(
            conversation_history, 
            topic=self.session_data["topic"], 
            rag_context=rag_context, 
            interview_type=self.interview_type
        )
        
        await add_follow_up_question(self.session_id, next_question)
        
        return {
            "question": next_question,
            "ready_to_code": False
        }
    
    def _build_conversation_history(self) -> list:
        """Build conversation history for next question generation."""
        conversation_history = []
        
        if self.session_data.get("questions"):
            base_question = self.session_data["questions"][0]
            conversation_history.append({"role": "assistant", "content": base_question["question"]})
        
        for q in self.session_data["follow_up_questions"]:
            conversation_history.append({"role": "assistant", "content": q["question"]})
            if q.get("answer"):
                conversation_history.append({"role": "user", "content": q["answer"]})
        
        return conversation_history
    
    async def _generate_coding_feedback(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate feedback for coding interview with bad answer quality."""
        feedback_message = await self._generate_dynamic_feedback(question_data)
        
        return {
            "question": feedback_message,
            "ready_to_code": False,
            "answer_rejected": True,
            "quality_feedback": feedback_message
        }
    
    async def _generate_approach_feedback(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate feedback for approach interview with bad answer quality."""
        feedback_message = await self._generate_dynamic_feedback(question_data)
        
        return {
            "question": feedback_message,
            "ready_to_code": False,
            "answer_rejected": False,
            "quality_feedback": feedback_message
        }
    
    async def _generate_dynamic_feedback(self, question_data: Dict[str, Any]) -> str:
        """Generate dynamic feedback based on answer characteristics."""
        answer_text = question_data.get("answer", "").strip().lower()
        
        # Check for gibberish patterns
        is_gibberish = (
            len(answer_text) < 10 or
            any(char * 3 in answer_text for char in 'abcdefghijklmnopqrstuvwxyz') or
            any(answer_text.count(char) > len(answer_text) * 0.4 for char in 'abcdefghijklmnopqrstuvwxyz') or
            len(set(answer_text.split())) < 2
        )
        
        # Determine feedback type
        if is_gibberish:
            feedback_type = "gibberish"
        elif len(answer_text) < 20:
            feedback_type = "brief"
        elif any(word in answer_text for word in ["idk", "don't know", "not sure", "unsure"]):
            feedback_type = "uncertain"
        elif any(word in answer_text for word in ["yes", "no", "maybe"]):
            feedback_type = "yes_no"
        else:
            feedback_type = "general"
        
        return await generate_dynamic_feedback(
            question_data["question"],
            question_data.get("answer", ""),
            self.session_data["topic"],
            feedback_type
        )
