"""
User Session Service

This module handles user session management, including:
- User session retrieval and formatting
- User interaction history
- User patterns and personalized data
- Session metadata management
"""

import logging
from typing import Dict, Any, List
from services.db import (
    get_user_interview_sessions, 
    get_user_name_from_id, 
    get_enhanced_personalized_context,
    validate_user_id
)

logger = logging.getLogger(__name__)

class UserSessionService:
    """Handles user session management and retrieval."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
    
    async def get_user_sessions(self, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """Get user's interview session history."""
        if not await validate_user_id(self.user_id):
            raise ValueError("User not found")
        
        sessions = await get_user_interview_sessions(self.user_id, limit)
        
        # Format response with session metadata
        formatted_sessions = []
        for session in sessions:
            session_data = session["meta"]["session_data"]
            formatted_sessions.append({
                "session_id": session["session_id"],
                "topic": session_data["topic"],
                "user_name": session_data["user_name"],
                "status": session_data["status"],
                "current_phase": session_data["current_phase"],
                "total_questions": session_data["total_questions"],
                "created_at": session["timestamp"],
                "updated_at": session["timestamp"],
                "has_feedback": session_data.get("feedback") is not None
            })
        
        return {"sessions": formatted_sessions}
    
    async def get_user_session_detail(self, session_id: str) -> Dict[str, Any]:
        """Get detailed information about specific interview session."""
        if not await validate_user_id(self.user_id):
            raise ValueError("User not found")
        
        from services.db import get_interview_session
        
        session = await get_interview_session(session_id)
        if not session:
            raise ValueError("Session not found")
        
        # Verify session belongs to user
        if str(session["user_id"]) != self.user_id:
            raise ValueError("Access denied")
        
        session_data = session["meta"]["session_data"]
        
        return {
            "session_id": session["session_id"],
            "topic": session_data["topic"],
            "user_name": session_data["user_name"],
            "status": session_data["status"],
            "current_phase": session_data["current_phase"],
            "total_questions": session_data["total_questions"],
            "created_at": session["timestamp"],
            "updated_at": session["timestamp"],
            "metadata": session["ai_response"],
            "questions": session_data["questions"],
            "follow_up_questions": session_data["follow_up_questions"],
            "clarifications": session_data["clarifications"],
            "feedback": session_data.get("feedback")
        }
    
    async def get_user_patterns(self) -> Dict[str, Any]:
        """Get enhanced user patterns data for debugging and analysis."""
        if not await validate_user_id(self.user_id):
            raise ValueError("User not found")
        
        # Get enhanced personalized context
        user_name = await get_user_name_from_id(self.user_id)
        personalized_context = await get_enhanced_personalized_context(
            self.user_id, 
            user_name=user_name
        )
        
        return {
            "user_patterns": personalized_context["user_patterns"],
            "personalized_guidance": personalized_context["personalized_guidance"]
        }
