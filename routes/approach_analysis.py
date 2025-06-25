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
    Analyze a user's approach to a question and provide structured feedback.
    """
    # Validate user_id
    if not await validate_user_id(request.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    try:
        # Get user name from their history
        user_name = await get_user_name_from_history(request.user_id)
        
        # --- Progress API check ---
        progress_data = None
        if getattr(request, "question_id", None):
            progress_data = await check_question_answered_by_id(request.user_id, request.question_id)
        
        # Get enhanced personalized context based on user's previous interactions and progress data
        personalized_context = await get_enhanced_personalized_context(
            request.user_id, 
            user_name=user_name,
            question_id=getattr(request, "question_id", None) # type: ignore
        )
        
        # Log personalized context for debugging
        logger = logging.getLogger(__name__)
        logger.info(f"personalized_guidance: {personalized_context['personalized_guidance']}")
        logger.info(f"user_patterns: {personalized_context['user_patterns']}")
        
        previous_attempt = None
        if progress_data and progress_data.get("success"):
            previous_attempt = {
                "answer": progress_data["data"].get("answer", ""),
                "result": progress_data["data"].get("finalResult", None),
                "output": progress_data["data"].get("output", "")
            }
        personalized_guidance = personalized_context["personalized_guidance"] if personalized_context["personalized_guidance"] else None
        result = await analysis_service.analyze_approach(
            question=request.question,
            user_answer=request.user_answer,
            user_name=user_name,
            previous_attempt=previous_attempt,
            personalized_guidance=personalized_guidance,
            user_patterns=personalized_context["user_patterns"] if "user_patterns" in personalized_context else None
        )
        
        # Remove any fields not documented in the API specification
        # Keep only: feedback, strengths, areas_for_improvement, score
        documented_response = {
            "feedback": result.get("feedback", ""),
            "strengths": result.get("strengths", []),
            "areas_for_improvement": result.get("areas_for_improvement", []),
            "score": result.get("score", 0)
        }
        
        # Save the full result (including user_patterns) to database for internal use
        full_result = result.copy()
        full_result["user_patterns"] = personalized_context["user_patterns"]
        
        # Save interaction (do not block response)
        try:
            await save_user_ai_interaction(
                user_id=request.user_id,
                endpoint="approach_analysis",
                input_data=request.dict(),
                ai_response=full_result  # Save full result with user_patterns
            )
        except Exception as e:
            print(f"Failed to save user-AI interaction: {e}")
        
        return documented_response  # Return only documented fields
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing approach: {str(e)}")