"""
Approach Analysis API Routes

This module handles approach analysis requests, providing structured feedback
on user's problem-solving approaches with personalized recommendations.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from services.approach_analysis import ApproachAnalysisService
from models.schemas import ApproachAnalysisRequest
from services.db import validate_user_id, save_user_ai_interaction, get_personalized_context, get_user_name_from_history, get_enhanced_personalized_context
from services.llm.utils import check_question_answered_by_id
import logging

router = APIRouter(tags=["Approach Analysis"])

analysis_service = ApproachAnalysisService()

@router.post("/analyze-approach")
async def analyze_approach(request: ApproachAnalysisRequest):
    """
    Analyze user's approach to a question and provide structured feedback.
    Uses personalized context to give tailored recommendations.
    """
    logger = logging.getLogger(__name__)
    # Validate user exists
    if not await validate_user_id(request.user_id):
        logger.error(f"User not found: user_id={request.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    try:
        # Get user name for personalized feedback
        user_name = await get_user_name_from_history(request.user_id)
        
        # Check if user has previous attempts at this question
        progress_data = None
        if getattr(request, "question_id", None):
            progress_data = await check_question_answered_by_id(request.user_id, request.question_id)
        
        # Get personalized context based on user history
        personalized_context = await get_enhanced_personalized_context(
            request.user_id, 
            user_name=user_name,
            question_id=getattr(request, "question_id", None) # type: ignore
        )
        
        # Log context for debugging
        logger.info(f"personalized_guidance: {personalized_context['personalized_guidance']}")
        logger.info(f"user_patterns: {personalized_context['user_patterns']}")
        
        # Prepare previous attempt data if available
        previous_attempt = None
        if progress_data and progress_data.get("success"):
            previous_attempt = {
                "answer": progress_data["data"].get("answer", ""),
                "result": progress_data["data"].get("finalResult", None),
                "output": progress_data["data"].get("output", "")
            }
            
        # Get personalized guidance and user patterns
        personalized_guidance = personalized_context["personalized_guidance"] if personalized_context["personalized_guidance"] else None
        
        # Analyze approach with personalized context
        result = await analysis_service.analyze_approach(
            question=request.question,
            user_answer=request.user_answer,
            user_name=user_name,
            previous_attempt=previous_attempt,
            personalized_guidance=personalized_guidance,
            user_patterns=personalized_context["user_patterns"] if "user_patterns" in personalized_context else None
        )
        
        # Return only documented fields for API response
        documented_response = {
            "feedback": result.get("feedback", ""),
            "strengths": result.get("strengths", []),
            "areas_for_improvement": result.get("areas_for_improvement", []),
            "score": result.get("score", 0)
        }
        
        # Save full result with user patterns for internal use
        full_result = result.copy()
        full_result["user_patterns"] = personalized_context["user_patterns"]
        
        # Save interaction for analytics (non-blocking)
        try:
            await save_user_ai_interaction(
                user_id=request.user_id,
                endpoint="approach_analysis",
                input_data=request.dict(),
                ai_response=full_result  # Save full result with user_patterns
            )
        except Exception as e:
            logger.error(f"Failed to save user-AI interaction for user_id={request.user_id}: {e}", exc_info=True)
        
        return documented_response  # Return only documented fields
    except Exception as e:
        logger.error(f"Error analyzing approach for user_id={request.user_id}, question_id={getattr(request, 'question_id', None)}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing approach: {str(e)}")