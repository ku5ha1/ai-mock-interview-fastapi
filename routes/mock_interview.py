"""
Mock Interview API Routes

This module contains all the API endpoints for the AI-powered mock interview system.
It handles interview initialization, answer submission, feedback generation, and user session management.

ENHANCED ANSWER QUALITY VALIDATION:
- All answers are now validated using the enhanced check_single_answer_quality function
- Gibberish, nonsensical, or off-topic answers are rejected
- System prevents progression until meaningful answers are provided
- Maximum clarification limits prevent infinite loops
- Professional feedback guides users to provide better responses
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from services.db import (
    fetch_interactions_for_session, fetch_user_history, get_db, fetch_base_question, get_available_topics, 
    save_user_ai_interaction, validate_user_id, get_interview_session, update_interview_session_answer,
    get_available_modules
)
from services.interview_initialization import InterviewInitializer
from services.interview_flow import InterviewFlowManager
from services.feedback_service import FeedbackService
from services.user_session_service import UserSessionService
from models.schemas import InterviewInit, AnswerRequest, ClarificationRequest
import logging
from datetime import datetime
from services.rag.retriever_factory import get_rag_retriever

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Mock Interview"])

@router.post("/init")
async def init_interview(init_data: InterviewInit):
    """
    Initialize a new mock interview session.
    Creates session with base question, generates first follow-up, and stores in database.
    Uses module_code to fetch random questions.
    """
    try:
        initializer = InterviewInitializer(init_data.user_id, init_data.module_code)
        return await initializer.initialize_interview()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error initializing interview: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/answer")
async def submit_answer(answer_request: AnswerRequest = Body(...)):
    """
    Submit user's answer during interview session.
    Handles both questioning and coding phases, generates follow-up questions or transitions to coding.
    Supports both coding and approach interview types.
    """
    try:
        session_id = answer_request.session_id
        session = await get_interview_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        session_data = session["meta"]["session_data"]
        current_phase = session_data["current_phase"]
        
        # Handle coding phase
        if current_phase == "coding":
            return await _handle_coding_phase(answer_request, session, session_data)
        
        # Update session with user's answer
        await update_interview_session_answer(session_id, answer_request.answer, False)
        
        # Get RAG context
        rag_context = await _get_rag_context(session_data["topic"])
        
        # Process answer using flow manager
        flow_manager = InterviewFlowManager(session_data, session_id)
        result = await flow_manager.process_answer(answer_request.answer, rag_context)
        
        # Add language field for coding interviews if needed
        if session_data.get("interview_type") == "coding" and "language" not in result:
            result["language"] = session["ai_response"].get("language", "")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def _handle_coding_phase(answer_request: AnswerRequest, session: dict, session_data: dict) -> dict:
    """Handle coding phase logic."""
    if answer_request.clarification:
        # Handle clarification request
        flow_manager = InterviewFlowManager(session_data, answer_request.session_id)
        result = await flow_manager.handle_coding_phase(answer_request.answer, True)
        
        # Update session with clarification count
        if "clarification_count" in result:
            from services.db import get_db
            db = await get_db()
            await db.user_ai_interactions.update_one(
                {"session_id": answer_request.session_id},
                {"$set": {"meta.session_data.coding_clarification_count": result["clarification_count"]}}
            )
        
        # Update session with answer
        await update_interview_session_answer(answer_request.session_id, answer_request.answer, True)
        
        # Add language field
        result["language"] = session["ai_response"].get("language", "")
        
        return result
    else:
        # Handle final code submission
        await update_interview_session_answer(answer_request.session_id, answer_request.answer, False)
        
        # Mark session as completed
        session_data["status"] = "completed"
        session_data["current_phase"] = "completed"
        
        from services.db import get_db
        db = await get_db()
        await db.user_ai_interactions.update_one(
            {"session_id": answer_request.session_id},
            {
                "$set": {
                    "meta.session_data": session_data,
                    "timestamp": datetime.utcnow()
                }
            }
        )
        
        return {"message": "Code submitted successfully. You can now generate feedback."}

async def _get_rag_context(topic: str) -> str:
    """Get RAG context for the given topic."""
    try:
        retriever = await get_rag_retriever()
        if retriever:
            context_chunks = await retriever.retrieve_context(topic)
            return "\n\n".join(context_chunks)
    except Exception as e:
        logger.warning(f"Failed to get RAG context: {e}")
    
    return ""

@router.post("/feedback/{session_id}")
async def get_interview_feedback(session_id: str, code_submission: dict = Body(default=None)):
    """
    Generate comprehensive feedback for completed interview session.
    Analyzes conversation and provides personalized feedback with recommendations.
    Accepts code and output data for coding interviews.
    """
    try:
        session = await get_interview_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        feedback_service = FeedbackService(session)
        return await feedback_service.get_interview_feedback(code_submission)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting feedback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/topics")
async def get_topics():
    """
    Get all available interview topics.
    Returns list of topics users can select for mock interviews.
    """
    try:
        topics = await get_available_topics()
        return {"topics": topics}
    except Exception as e:
        logger.error(f"Error getting topics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/modules")
async def get_modules():
    """
    Get all available modules for mock interviews.
    Returns list of modules with question counts that users can select for mock interviews.
    """
    try:
        modules = await get_available_modules()
        return {"modules": modules}
    except Exception as e:
        logger.error(f"Error getting modules: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/interactions/{user_id}")
async def get_user_interactions(user_id: str, limit: int = 50):
    """
    Get user's AI interaction history.
    Returns past interactions including interviews, code optimization, and analysis sessions.
    """
    try:
        if not await validate_user_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        interactions = await fetch_user_history(user_id, limit)
        return {"interactions": interactions}
    except Exception as e:
        logger.error(f"Error fetching user interactions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching user interactions")

@router.get("/user/sessions/{user_id}")
async def get_user_sessions(user_id: str, limit: int = 20):
    """
    Get user's interview session history.
    Returns all mock interview sessions with metadata and status information.
    """
    try:
        user_session_service = UserSessionService(user_id)
        return await user_session_service.get_user_sessions(limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting user sessions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/session/{user_id}/{session_id}")
async def get_user_session_detail(user_id: str, session_id: str):
    """
    Get detailed information about specific interview session.
    Returns complete session data including questions, answers, and feedback.
    """
    try:
        user_session_service = UserSessionService(user_id)
        return await user_session_service.get_user_session_detail(session_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        elif "access denied" in str(e).lower():
            raise HTTPException(status_code=403, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting session detail: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/patterns/{user_id}")
async def get_user_patterns(user_id: str):
    """
    Get enhanced user patterns data for debugging and analysis.
    Returns personalized context and user behavior patterns.
    """
    try:
        user_session_service = UserSessionService(user_id)
        return await user_session_service.get_user_patterns()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting user patterns: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))