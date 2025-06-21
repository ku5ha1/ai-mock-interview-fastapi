from fastapi import APIRouter, Depends, HTTPException, Body
from services.approach_analysis import ApproachAnalysisService
from models.schemas import ApproachAnalysisRequest
from services.db import validate_user_id, save_user_ai_interaction, get_personalized_context, get_user_name_from_history

router = APIRouter(prefix="/approach", tags=["Approach Analysis"])

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
        
        # Get personalized context based on user's previous interactions
        personalized_context = await get_personalized_context(request.user_id, user_name=user_name)
        
        result = await analysis_service.analyze_approach(
            question=request.question,
            user_answer=request.user_answer,
            user_name=user_name
        )
        
        # Add personalized insights to the feedback field only (as per API documentation)
        if personalized_context["personalized_guidance"]:
            if "feedback" in result:
                result["feedback"] += f"\n\nPersonalized Guidance: {personalized_context['personalized_guidance']}"
        
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