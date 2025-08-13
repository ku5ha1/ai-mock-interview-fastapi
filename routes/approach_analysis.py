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
import asyncio
import time

router = APIRouter(tags=["Approach Analysis"])

analysis_service = ApproachAnalysisService()

@router.post("/analyze-approach")
async def analyze_approach(request: ApproachAnalysisRequest):
    """
    Analyze user's approach to a question and provide structured feedback.
    Uses personalized context to give tailored recommendations.
    """
    start_time = time.time()
    logger = logging.getLogger(__name__)
    
    # Validate user exists
    if not await validate_user_id(request.user_id):
        logger.error(f"User not found: user_id={request.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Parallelize database calls for better performance
        user_name_task = get_user_name_from_history(request.user_id)
        progress_data_task = None
        if getattr(request, "question_id", None):
            progress_data_task = check_question_answered_by_id(request.user_id, request.question_id)
        
        # Execute database calls in parallel
        db_start = time.time()
        if progress_data_task:
            user_name, progress_data = await asyncio.gather(
                user_name_task, 
                progress_data_task
            )
        else:
            user_name = await user_name_task
            progress_data = None
        
        db_time = time.time() - db_start
        logger.info(f"Database calls completed in {db_time:.2f}s")
        
        # Get personalized context (this includes its own database calls)
        context_start = time.time()
        personalized_context = await get_enhanced_personalized_context(
            request.user_id, 
            user_name=user_name,
            question_id=getattr(request, "question_id", None)
        )
        context_time = time.time() - context_start
        logger.info(f"Personalization context completed in {context_time:.2f}s")
        
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
        analysis_start = time.time()
        result = await analysis_service.analyze_approach(
            question=request.question,
            user_answer=request.user_answer,
            user_name=user_name,
            previous_attempt=previous_attempt,
            personalized_guidance=personalized_guidance,
            user_patterns=personalized_context["user_patterns"] if "user_patterns" in personalized_context else None
        )
        analysis_time = time.time() - analysis_start
        logger.info(f"AI analysis completed in {analysis_time:.2f}s")
        
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
            # Use asyncio.create_task to make this non-blocking
            asyncio.create_task(
                save_user_ai_interaction(
                    user_id=request.user_id,
                    endpoint="approach_analysis",
                    input_data=request.dict(),
                    ai_response=full_result
                )
            )
        except Exception as e:
            logger.error(f"Failed to save user-AI interaction for user_id={request.user_id}: {e}", exc_info=True)
        
        total_time = time.time() - start_time
        logger.info(f"Total approach analysis completed in {total_time:.2f}s (DB: {db_time:.2f}s, Context: {context_time:.2f}s, AI: {analysis_time:.2f}s)")
        
        return documented_response
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"Error analyzing approach for user_id={request.user_id}, question_id={getattr(request, 'question_id', None)}: {e} (took {total_time:.2f}s)", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing approach: {str(e)}")