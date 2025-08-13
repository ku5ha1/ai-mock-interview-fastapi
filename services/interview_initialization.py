"""
Interview Initialization Service

This module handles interview session initialization, including:
- Session creation
- Base question fetching
- First follow-up question generation
- Session storage
"""

import logging
from datetime import datetime
from typing import Dict, Any
from services.db import create_interview_session, get_user_name_from_id, validate_user_id
from services.interview import get_next_question
from services.rag.retriever_factory import get_rag_retriever
from services.db import fetch_question_by_module

logger = logging.getLogger(__name__)

class InterviewInitializer:
    """Handles interview session initialization."""
    
    def __init__(self, user_id: str, module_code: str):
        self.user_id = user_id
        self.module_code = module_code
    
    async def initialize_interview(self) -> Dict[str, Any]:
        """Initialize a new mock interview session."""
        # Validate user
        if not await validate_user_id(self.user_id):
            raise ValueError("User not found")
        
        # Create unique session ID
        session_id = f"{self.user_id}_{self.module_code}_{datetime.now().timestamp()}"
        
        # Fetch question by module code
        base_question_data = await fetch_question_by_module(self.module_code, attempted_questions=[])
        
        # Get RAG context for better question generation
        rag_context = await self._get_rag_context()
        
        # Generate first follow-up question
        first_follow_up = await self._generate_first_follow_up(base_question_data, rag_context)
        
        # Create interview session in database
        await self._create_session(session_id, base_question_data, first_follow_up)
        
        # Build response
        return self._build_response(session_id, base_question_data, first_follow_up)
    
    async def _get_rag_context(self) -> str:
        """Get RAG context for the module."""
        try:
            retriever = await get_rag_retriever()
            if retriever is not None:
                context_chunks = await retriever.retrieve_context(self.module_code)
                return "\n\n".join(context_chunks)
        except Exception as e:
            logger.warning(f"Failed to get RAG context: {e}")
        
        return ""
    
    async def _generate_first_follow_up(self, base_question_data: Dict[str, Any], rag_context: str) -> str:
        """Generate the first follow-up question."""
        try:
            return await get_next_question(
                [], 
                is_base_question=True, 
                topic=self.module_code, 
                rag_context=rag_context, 
                interview_type=base_question_data.get("interview_type", "coding")
            )
        except Exception as e:
            logger.error(f"Error generating follow-up question: {str(e)}", exc_info=True)
            raise RuntimeError(f"Error generating follow-up question: {str(e)}")
    
    async def _create_session(self, session_id: str, base_question_data: Dict[str, Any], first_follow_up: str):
        """Create the interview session in the database."""
        try:
            user_name = await get_user_name_from_id(self.user_id)
            
            # Debug logging for interview type
            logger.info(f"Creating session with interview_type: {base_question_data.get('interview_type')}")
            logger.info(f"Base question data keys: {list(base_question_data.keys())}")
            
            await create_interview_session(
                user_id=self.user_id,
                session_id=session_id,
                topic=self.module_code,
                user_name=user_name,
                base_question_data=base_question_data,
                first_follow_up=first_follow_up,
                base_question_id=str(base_question_data["_id"])
            )
            logger.info(f"Successfully created interview session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to create interview session: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create interview session: {str(e)}")
    
    def _build_response(self, session_id: str, base_question_data: Dict[str, Any], first_follow_up: str) -> Dict[str, Any]:
        """Build the response object for the initialized interview."""
        # Debug logging for interview type
        logger.info(f"Building response with interview_type: {base_question_data.get('interview_type')}")
        logger.info(f"Base question data keys: {list(base_question_data.keys())}")
        
        response = {
            "session_id": session_id,
            "base_question": base_question_data["question"],
            "description": base_question_data.get("description", ""),
            "level": base_question_data.get("level", ""),
            "question_type": base_question_data.get("question_type", ""),
            "programming_language": base_question_data.get("programming_language", ""),
            "base_code": base_question_data.get("base_code", ""),
            "tags": base_question_data.get("tags", []),
            "example": base_question_data.get("example", ""),
            "dbSetupCommands": base_question_data.get("dbSetupCommands", ""),
            "difficulty": base_question_data.get("difficulty", ""),
            "first_follow_up": first_follow_up,
            "base_question_id": str(base_question_data["_id"]),
            "module_code": base_question_data.get("module_code", ""),
            "topic_code": base_question_data.get("topic_code", ""),
            "interview_type": base_question_data.get("interview_type", "approach")
        }
        
        # Add coding-specific fields only for coding interviews
        if base_question_data.get("interview_type") == "coding":
            response.update({
                "code_stub": base_question_data.get("code_stub", ""),
                "language": base_question_data.get("language", ""),
                "sample_input": base_question_data.get("expectedOutput", ""),
                "sample_output": base_question_data.get("expectedOutput", "")
            })
        
        logger.info(f"Final response interview_type: {response['interview_type']}")
        return response
