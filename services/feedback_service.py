"""
Feedback Service

This module handles interview feedback generation, including:
- Feedback retrieval and creation
- Personalized context integration
- Code assessment for coding interviews
- Feedback storage and retrieval
"""

import logging
from typing import Dict, Any, Optional
from services.db import get_user_name_from_id, get_enhanced_personalized_context, save_interview_feedback
from services.llm.feedback import get_feedback
from services.llm.utils import check_question_answered_by_id

logger = logging.getLogger(__name__)

class FeedbackService:
    """Handles interview feedback generation and management."""
    
    def __init__(self, session: Dict[str, Any]):
        self.session = session
        self.session_data = session["meta"]["session_data"]
        self.session_id = session["session_id"]
    
    async def get_interview_feedback(self, code_submission: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate comprehensive feedback for completed interview session."""
        # Return existing feedback if available
        if self.session_data.get("feedback"):
            return self._format_existing_feedback()
        
        # Get user name
        user_name = await self._get_user_name()
        
        # Check progress API for previous attempts
        progress_data = await self._get_progress_data()
        
        # Get personalized context
        personalized_context = await self._get_personalized_context(user_name)
        
        # Build conversation for feedback generation
        conversation = self._build_conversation()
        
        # Prepare code data for coding interviews
        code_data = self._prepare_code_data(code_submission)
        
        # Generate feedback
        feedback_data = await self._generate_feedback(conversation, user_name, personalized_context, code_data)
        
        # Add previous attempt info if available
        if progress_data:
            feedback_data["previous_attempt"] = self._format_previous_attempt(progress_data)
        
        # Save feedback to database
        await self._save_feedback(feedback_data, personalized_context)
        
        # Format and return response
        return self._format_feedback_response(feedback_data)
    
    def _format_existing_feedback(self) -> Dict[str, Any]:
        """Format existing feedback for response."""
        feedback = self.session_data["feedback"]
        if "base_question" not in feedback and self.session_data.get("questions"):
            feedback["base_question"] = self.session_data["questions"][0].get("question")
        
        return self._ensure_feedback_fields(feedback)
    
    async def _get_user_name(self) -> str:
        """Get user name from user ID."""
        user_name = await get_user_name_from_id(str(self.session["user_id"]))
        if not user_name:
            logger.warning(f"User name not found for user_id: {self.session['user_id']}, using default")
            user_name = "User"
        
        self.session_data["user_name"] = user_name
        return user_name
    
    async def _get_progress_data(self) -> Optional[Dict[str, Any]]:
        """Get progress data for previous attempts."""
        base_question_id = self.session_data.get("base_question_id")
        if base_question_id:
            return await check_question_answered_by_id(str(self.session["user_id"]), base_question_id)
        return None
    
    async def _get_personalized_context(self, user_name: str) -> Dict[str, Any]:
        """Get personalized context for enhanced feedback."""
        return await get_enhanced_personalized_context(
            self.session["user_id"], 
            self.session_data["topic"], 
            self.session_data.get("base_question_id"),
            user_name
        )
    
    def _build_conversation(self) -> list:
        """Build conversation for feedback generation."""
        conversation = []
        
        if self.session_data["questions"]:
            conversation.append({
                "question": self.session_data["questions"][0]["question"],
                "answer": self.session_data["questions"][0]["answer"]
            })
        
        for q in self.session_data["follow_up_questions"]:
            conversation.append({
                "question": q["question"],
                "answer": q["answer"]
            })
        
        for c in self.session_data["clarifications"]:
            conversation.append({
                "question": f"[Clarification] {c['question']}",
                "answer": c["answer"]
            })
        
        if not conversation:
            raise ValueError("No conversation found for this session")
        
        return conversation
    
    def _prepare_code_data(self, code_submission: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Prepare code data for coding interviews."""
        interview_type = self.session_data.get("interview_type", "approach")
        
        if interview_type == "coding" and code_submission:
            return {
                "code": code_submission.get("code", ""),
                "output": code_submission.get("output", ""),
                "solutionCode": self.session["ai_response"].get("solutionCode", ""),
                "expectedOutput": self.session["ai_response"].get("expectedOutput", "")
            }
        elif interview_type == "coding" and not code_submission:
            logger.warning(f"Coding interview but no code submission provided for session: {self.session_id}")
        
        return None
    
    async def _generate_feedback(self, conversation: list, user_name: str, 
                                personalized_context: Dict[str, Any], 
                                code_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate feedback using the LLM."""
        return await get_feedback(
            conversation,
            user_name,
            previous_attempt=None,
            personalized_guidance=personalized_context.get("personalized_guidance"),
            user_patterns=personalized_context.get("user_patterns"),
            code_data=code_data
        )
    
    def _format_previous_attempt(self, progress_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format previous attempt data."""
        if progress_data and progress_data.get("success"):
            return {
                "answer": progress_data["data"].get("answer", ""),
                "result": progress_data["data"].get("finalResult", None),
                "output": progress_data["data"].get("output", "")
            }
        return {}
    
    async def _save_feedback(self, feedback_data: Dict[str, Any], personalized_context: Dict[str, Any]):
        """Save feedback to the database."""
        full_feedback_data = feedback_data.copy()
        full_feedback_data["user_patterns"] = personalized_context.get("user_patterns", {})
        
        await save_interview_feedback(self.session_id, full_feedback_data)
    
    def _format_feedback_response(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format the final feedback response."""
        # Add base question to response
        if self.session_data.get("questions"):
            feedback_data["base_question"] = self.session_data["questions"][0].get("question")
        
        # Ensure all required fields are present
        return self._ensure_feedback_fields(feedback_data)
    
    def _ensure_feedback_fields(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure all required feedback fields are present with default values."""
        feedback['base_question'] = feedback.get('base_question') or "No base question available."
        feedback['summary'] = feedback.get('summary') or "No summary provided."
        feedback['positive_points'] = feedback.get('positive_points') or []
        feedback['areas_for_improvement'] = feedback.get('areas_for_improvement') or []
        feedback['overall_score'] = feedback.get('overall_score') or 0
        feedback['detailed_feedback'] = feedback.get('detailed_feedback') or "No detailed feedback available."
        feedback['recommendations'] = feedback.get('recommendations') or []
        
        return feedback
