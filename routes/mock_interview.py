"""
Mock Interview API Routes

This module contains all the API endpoints for the AI-powered mock interview system.
It handles interview initialization, answer submission, feedback generation, and user session management.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from services.db import (
    fetch_interactions_for_session, fetch_user_history, get_db, fetch_base_question, get_available_topics, save_user_ai_interaction, validate_user_id, 
    create_interview_session, get_interview_session, update_interview_session_answer,
    add_follow_up_question, transition_to_coding_phase, save_interview_feedback,
    get_user_interview_sessions, get_personalized_context, get_user_name_from_id, get_enhanced_personalized_context,
    fetch_question_by_module, get_available_modules  # Add these new imports
)
from services.interview import get_next_question
from services.llm.feedback import get_feedback
from services.llm.clarification import get_clarification
from services.llm.check_answer_quality import check_answer_quality, check_single_answer_quality
from models.schemas import InterviewInit, AnswerRequest, ClarificationRequest
import logging
from datetime import datetime
from services.rag.retriever_factory import get_rag_retriever
from bson import ObjectId
from services.llm.utils import check_question_answered_by_id, generate_clarification_feedback

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Mock Interview"])

@router.post("/init")
async def init_interview(init_data: InterviewInit):
    """
    Initialize a new mock interview session.
    Creates session with base question, generates first follow-up, and stores in database.
    Uses module_code to fetch random questions.
    """
    if not await validate_user_id(init_data.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    try:
        # Create unique session ID
        session_id = f"{init_data.user_id}_{init_data.module_code}_{datetime.now().timestamp()}"
        
        # Fetch question by module code
        base_question_data = await fetch_question_by_module(init_data.module_code)
        
        # Get RAG context for better question generation
        retriever = await get_rag_retriever()
        rag_context = ""
        if retriever is not None:
            context_chunks = await retriever.retrieve_context(init_data.module_code)
            rag_context = "\n\n".join(context_chunks)
        
        # Generate first follow-up question
        try:
            first_follow_up = await get_next_question([], is_base_question=True, topic=init_data.module_code, rag_context=rag_context, interview_type=base_question_data.get("interview_type", "coding"))
        except Exception as e:
            logger.error(f"Error generating follow-up question: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error generating follow-up question: {str(e)}")
        
        # Create interview session in database
        try:
            user_name = await get_user_name_from_id(init_data.user_id)
            await create_interview_session(
                user_id=init_data.user_id,
                session_id=session_id,
                topic=init_data.module_code,  # Store module_code as topic for backward compatibility
                user_name=user_name,
                base_question_data=base_question_data,
                first_follow_up=first_follow_up,
                base_question_id=str(base_question_data["_id"])
            )
            logger.info(f"Successfully created interview session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to create interview session: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create interview session: {str(e)}")
        
        # Return session details
        response = {
            "session_id": session_id,
            "base_question": base_question_data["question"],
            "difficulty": base_question_data["difficulty"],
            "example": base_question_data["example"],
            "tags": base_question_data["tags"],
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
                "sample_input": base_question_data.get("expectedOutput", ""),  # Using expectedOutput as sample input
                "sample_output": base_question_data.get("expectedOutput", "")
            })
        
        return response
    except HTTPException:
        raise
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
        interview_type = session_data.get("interview_type", "approach")
        current_phase = session_data["current_phase"]
        
        # Handle coding phase (clarifications or final code submission)
        if current_phase == "coding":
            if answer_request.clarification:
                try:
                    base_question = session["meta"]["session_data"]["questions"][0]["question"]
                    clarification_resp = await get_clarification(base_question, answer_request.answer)
                    await update_interview_session_answer(session_id, answer_request.answer, True)
                    return {
                        "question": clarification_resp,
                        "clarification": True,
                        "ready_to_code": True,
                        "language": session["ai_response"].get("language", "")
                    }
                except Exception as e:
                    logger.error(f"Error generating clarification: {str(e)}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Error generating clarification: {str(e)}")
            else:
                # Final code submission - just mark session as ready for feedback
                await update_interview_session_answer(session_id, answer_request.answer, False)
                
                # Mark session as completed (code will be submitted via POST /feedback)
                session = await get_interview_session(session_id)
                session_data = session["meta"]["session_data"]
                session_data["status"] = "completed"
                session_data["current_phase"] = "completed"
                
                # Update session
                db = await get_db()
                await db.user_ai_interactions.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "meta.session_data": session_data,
                            "timestamp": datetime.utcnow()
                        }
                    }
                )
                
                return {"message": "Code submitted successfully. You can now generate feedback."}

        # Update session with user's answer
        await update_interview_session_answer(session_id, answer_request.answer, False)
        session = await get_interview_session(session_id)
        session_data = session["meta"]["session_data"]
        
        # Get RAG context for quality check and next question
        retriever = await get_rag_retriever()
        rag_context = ""
        if retriever:
            context_chunks = await retriever.retrieve_context(session_data["topic"])
            rag_context = "\n\n".join(context_chunks)

        # Check answer quality - more lenient for approach interviews
        last_answered_question = None
        for q in reversed(session_data["follow_up_questions"]):
            if q.get("answer"):
                last_answered_question = q
                break
        if not last_answered_question:
            last_answered_question = session_data["follow_up_questions"][-1]
        
        # Get clarification count for this question to prevent infinite loops
        clarification_count = last_answered_question.get("clarification_count", 0)
        max_clarifications = 2  # Maximum clarifications per question
        
        # Get total clarifications across all questions to prevent overall stalling
        total_clarifications = sum(q.get("clarification_count", 0) for q in session_data["follow_up_questions"])
        max_total_clarifications = 5  # Maximum total clarifications for entire session
        
        # For approach interviews, be more lenient with answer quality
        if interview_type == "approach":
            # Only check quality if answer is very short or empty
            answer_text = last_answered_question.get("answer", "").strip()
            if len(answer_text) < 10:  # Very short answers
                quality = "bad"
            else:
                quality = "good"  # Assume good for approach interviews with reasonable length
        else:
            # For coding interviews, use the quality check
            quality = await check_single_answer_quality(
                question=last_answered_question["question"],
                answer=last_answered_question.get("answer", ""),
                topic=session_data["topic"],
                rag_context=rag_context
            )
            
        # Provide feedback for poor quality answers (with clarification limits)
        if quality == "bad" and clarification_count < max_clarifications and total_clarifications < max_total_clarifications:
            # Increment clarification count
            clarification_count += 1
            
            # Update the question with clarification count
            db = await get_db()
            await db.user_ai_interactions.update_one(
                {"session_id": session_id, "meta.session_data.follow_up_questions.question": last_answered_question["question"]},
                {"$set": {"meta.session_data.follow_up_questions.$.clarification_count": clarification_count}}
            )
            
            feedback_message = await generate_clarification_feedback(
                last_answered_question["question"],
                last_answered_question.get("answer", "")
            )
            return {
                "question": feedback_message,
                "ready_to_code": False,
                "language": session["ai_response"].get("language", "")
            }
        
        # If we've reached max clarifications or quality is good, proceed to next question
        # Reset clarification count and mark this question as properly answered
        if clarification_count > 0:
            db = await get_db()
            await db.user_ai_interactions.update_one(
                {"session_id": session_id, "meta.session_data.follow_up_questions.question": last_answered_question["question"]},
                {"$set": {"meta.session_data.follow_up_questions.$.clarification_count": 0}}
            )
        
        # If we've reached maximum total clarifications, force progression
        if total_clarifications >= max_total_clarifications:
            logger.info(f"Session {session_id} reached maximum clarifications ({total_clarifications}), forcing progression")
            # Mark current question as answered to prevent further clarifications
            db = await get_db()
            await db.user_ai_interactions.update_one(
                {"session_id": session_id, "meta.session_data.follow_up_questions.question": last_answered_question["question"]},
                {"$set": {"meta.session_data.follow_up_questions.$.clarification_count": 0}}
            )

        total_questions = session_data["total_questions"]
        
        # Different logic for coding vs approach interviews
        if interview_type == "coding":
            # Generate next question if less than 5 questions for coding interviews
            if total_questions < 5:
                conversation_history = []
                if session_data.get("questions"):
                    base_question = session_data["questions"][0]
                    conversation_history.append({"role": "assistant", "content": base_question["question"]})

                for q in session_data["follow_up_questions"]:
                    conversation_history.append({"role": "assistant", "content": q["question"]})
                    if q.get("answer"):
                        conversation_history.append({"role": "user", "content": q["answer"]})
                
                try:
                    next_question = await get_next_question(conversation_history, topic=session_data["topic"], rag_context=rag_context, interview_type=interview_type)
                    await add_follow_up_question(session_id, next_question)
                    
                    return {
                        "question": next_question,
                        "ready_to_code": False,
                        "language": session["ai_response"].get("language", "")
                    }
                except Exception as e:
                    logger.error(f"Error generating next question: {str(e)}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Error generating next question: {str(e)}")
            
            # Transition to coding phase after 5 questions for coding interviews
            else:
                await transition_to_coding_phase(session_id)
                return {
                    "question": "Great! Now let's move to the coding phase. You can start coding below.",
                    "clarification": True,
                    "ready_to_code": True,
                    "code_stub": session["ai_response"].get("code_stub", ""),
                    "language": session["ai_response"].get("language", ""),
                    "tags": session["ai_response"].get("tags", [])
                }
        
        else:  # approach interview
            # Generate next question if less than 7 questions for approach interviews
            if total_questions < 7:
                conversation_history = []
                if session_data.get("questions"):
                    base_question = session_data["questions"][0]
                    conversation_history.append({"role": "assistant", "content": base_question["question"]})

                for q in session_data["follow_up_questions"]:
                    conversation_history.append({"role": "assistant", "content": q["question"]})
                    if q.get("answer"):
                        conversation_history.append({"role": "user", "content": q["answer"]})
                
                try:
                    next_question = await get_next_question(conversation_history, topic=session_data["topic"], rag_context=rag_context, interview_type=interview_type)
                    await add_follow_up_question(session_id, next_question)
                    
                    return {
                        "question": next_question,
                        "ready_to_code": False
                    }
                except Exception as e:
                    logger.error(f"Error generating next question: {str(e)}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Error generating next question: {str(e)}")
            
            # End approach interview after 7 questions
            else:
                return {
                    "question": "Great discussion! You can submit the session and check your feedback.",
                    "session_complete": True
                }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def ensure_feedback_fields(feedback, base_question):
    """
    Ensure all required feedback fields are present with default values.
    """
    feedback['base_question'] = base_question or "No base question available."
    feedback['summary'] = feedback.get('summary') or "No summary provided."
    feedback['positive_points'] = feedback.get('positive_points') or []
    feedback['areas_for_improvement'] = feedback.get('areas_for_improvement') or []
    feedback['overall_score'] = feedback.get('overall_score') or 0
    feedback['detailed_feedback'] = feedback.get('detailed_feedback') or "No detailed feedback available."
    feedback['recommendations'] = feedback.get('recommendations') or []
    
    return feedback

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
        
        session_data = session["meta"]["session_data"]

        user_name = await get_user_name_from_id(str(session["user_id"]))
        if not user_name:
            logger.warning(f"User name not found for user_id: {session['user_id']}, using default")
            user_name = "User"
        session_data["user_name"] = user_name
        
        # Return existing feedback if available
        if session_data.get("feedback"):
            feedback = session_data["feedback"]
            if "base_question" not in feedback and session_data.get("questions"):
                feedback["base_question"] = session_data["questions"][0].get("question")
            feedback = ensure_feedback_fields(feedback, session_data["questions"][0].get("question") if session_data.get("questions") else None)
            return feedback
        
        # Check progress API for previous attempts
        base_question_id = session_data.get("base_question_id")
        progress_data = None
        if base_question_id:
            progress_data = await check_question_answered_by_id(str(session["user_id"]), base_question_id)
        
        # Get personalized context for enhanced feedback
        personalized_context = await get_enhanced_personalized_context(
            session["user_id"], 
            session_data["topic"], 
            session_data.get("base_question_id"),
            session_data["user_name"]
        )
        
        logger.info(f"personalized_guidance: {personalized_context['personalized_guidance']}")
        logger.info(f"user_patterns: {personalized_context['user_patterns']}")
        
        # Build conversation for feedback generation
        conversation = []
        
        if session_data["questions"]:
            conversation.append({
                "question": session_data["questions"][0]["question"],
                "answer": session_data["questions"][0]["answer"]
            })
        
        for q in session_data["follow_up_questions"]:
            conversation.append({
                "question": q["question"],
                "answer": q["answer"]
            })
        
        for c in session_data["clarifications"]:
            conversation.append({
                "question": f"[Clarification] {c['question']}",
                "answer": c["answer"]
            })
        
        if not conversation:
            logger.error(f"No conversation found for session: {session_id}")
            raise HTTPException(status_code=404, detail="No conversation found for this session")
        
        # Check if this is a coding interview with code submission
        interview_type = session_data.get("interview_type", "approach")
        code_data = None
        
        if interview_type == "coding" and code_submission:
            # Get code data from POST request body
            code_data = {
                "code": code_submission.get("code", ""),
                "output": code_submission.get("output", ""),
                "solutionCode": session["ai_response"].get("solutionCode", ""),
                "expectedOutput": session["ai_response"].get("expectedOutput", "")
            }
            logger.info(f"Including code assessment for coding interview. Code length: {len(code_data['code'])}")
        elif interview_type == "coding" and not code_submission:
            logger.warning(f"Coding interview but no code submission provided for session: {session_id}")
        
        # Generate feedback with personalized context and code data if available
        feedback_data = await get_feedback(
            conversation,
            session_data["user_name"],
            previous_attempt=None,
            personalized_guidance=personalized_context["personalized_guidance"] if personalized_context["personalized_guidance"] else None,
            user_patterns=personalized_context["user_patterns"] if "user_patterns" in personalized_context else None,
            code_data=code_data  # Pass code data for coding interviews
        )
        
        # Add previous attempt info if available
        previous_attempt = None
        if progress_data and progress_data.get("success"):
            previous_attempt = {
                "answer": progress_data["data"].get("answer", ""),
                "result": progress_data["data"].get("finalResult", None),
                "output": progress_data["data"].get("output", "")
            }
        
        # Save full feedback data to database
        full_feedback_data = feedback_data.copy()
        full_feedback_data["user_patterns"] = personalized_context["user_patterns"]
        
        # Create documented response
        documented_response = {
            "summary": feedback_data.get("summary", ""),
            "positive_points": feedback_data.get("positive_points", []),
            "points_to_address": feedback_data.get("points_to_address", []),
            "areas_for_improvement": feedback_data.get("areas_for_improvement", [])
        }
        if previous_attempt:
            documented_response["previous_attempt"] = previous_attempt
        
        # Save feedback to session
        await save_interview_feedback(session_id, full_feedback_data)
        
        # Add base question to response
        if session_data.get("questions"):
            full_feedback_data["base_question"] = session_data["questions"][0].get("question")
        
        # Ensure all required fields are present
        full_feedback_data = ensure_feedback_fields(full_feedback_data, session_data["questions"][0].get("question") if session_data.get("questions") else None)
        
        return full_feedback_data
    except HTTPException:
        raise
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
        if not await validate_user_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        
        sessions = await get_user_interview_sessions(user_id, limit)
        
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
    except HTTPException:
        raise
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
        if not await validate_user_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        
        session = await get_interview_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify session belongs to user
        if str(session["user_id"]) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
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
    except HTTPException:
        raise
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
        if not await validate_user_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get enhanced personalized context
        user_name = await get_user_name_from_id(user_id)
        personalized_context = await get_enhanced_personalized_context(
            user_id, 
            user_name=user_name
        )
        
        return {
            "user_patterns": personalized_context["user_patterns"],
            "personalized_guidance": personalized_context["personalized_guidance"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user patterns: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))