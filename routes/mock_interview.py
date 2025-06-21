from fastapi import APIRouter, Depends, HTTPException, Body
from services.db import (
    get_db, fetch_base_question, get_available_topics, validate_user_id, 
    create_interview_session, get_interview_session, update_interview_session_answer,
    add_follow_up_question, transition_to_coding_phase, save_interview_feedback,
    get_user_interview_sessions, get_personalized_context
)
from services.llm.interview import get_next_question
from services.llm.feedback import get_feedback
from services.llm.clarification import get_clarification
from services.llm.check_answer_quality import check_answer_quality, check_single_answer_quality
from models.schemas import InterviewInit, AnswerRequest, ClarificationRequest
import logging
from datetime import datetime
from services.rag.retriever_factory import get_rag_retriever
from bson import ObjectId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mock", tags=["Mock Interview"])

@router.post("/init")
async def init_interview(init_data: InterviewInit):
    # Validate user_id
    if not await validate_user_id(init_data.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    try:
        # Generate session ID
        session_id = f"{init_data.user_name}_{init_data.topic}_{datetime.now().timestamp()}"
        
        # Get base question
        base_question_data = await fetch_base_question(init_data.topic)
        
        # Retrieve RAG context for the topic
        retriever = await get_rag_retriever()
        rag_context = ""
        if retriever is not None:
            context_chunks = await retriever.retrieve_context(init_data.topic)
            rag_context = "\n\n".join(context_chunks)
        
        # Get first follow-up question
        try:
            first_follow_up = await get_next_question([], is_base_question=True, topic=init_data.topic, rag_context=rag_context)
        except Exception as e:
            logger.error(f"Error generating follow-up question: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error generating follow-up question: {str(e)}")

        # Create structured interview session
        try:
            await create_interview_session(
                user_id=init_data.user_id,
                session_id=session_id,
                topic=init_data.topic,
                user_name=init_data.user_name,
                base_question_data=base_question_data,
                first_follow_up=first_follow_up
            )
            logger.info(f"Successfully created interview session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to create interview session: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create interview session: {str(e)}")

        response = {
            "session_id": session_id,
            "base_question": base_question_data["question"],
            "difficulty": base_question_data["difficulty"],
            "example": base_question_data["example"],
            "code_stub": base_question_data["code_stub"],
            "tags": base_question_data["tags"],
            "language": base_question_data["language"],
            "first_follow_up": first_follow_up
        }
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error initializing interview: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/answer")
async def submit_answer(answer_request: AnswerRequest = Body(...)):
    # Validate user_id
    if not await validate_user_id(answer_request.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    try:
        session_id = answer_request.session_id
        user_id = answer_request.user_id
        
        # Get the complete interview session
        session = await get_interview_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        # Update the session with the user's answer
        await update_interview_session_answer(session_id, answer_request.answer, answer_request.clarification)
        
        # Get updated session data
        session = await get_interview_session(session_id)
        session_data = session["meta"]["session_data"]
        
        # Determine next action based on current phase and question count
        total_questions = session_data["total_questions"]
        current_phase = session_data["current_phase"]
        
        if current_phase == "questioning" and total_questions < 5:
            # Continue with follow-up questions
            retriever = await get_rag_retriever()
            rag_context = ""
            if retriever is not None:
                context_chunks = await retriever.retrieve_context(session_data["topic"])
                rag_context = "\n\n".join(context_chunks)
            
            # Prepare questions for LLM (base question + follow-up questions with answers)
            questions_for_llm = []
            # Add base question
            if session_data["questions"]:
                questions_for_llm.append({
                    "question": session_data["questions"][0]["question"],
                    "answer": session_data["questions"][0]["answer"]
                })
            # Add follow-up questions with answers
            for q in session_data["follow_up_questions"]:
                questions_for_llm.append({
                    "question": q["question"],
                    "answer": q["answer"]
                })
            
            try:
                next_question = await get_next_question(questions_for_llm, topic=session_data["topic"], rag_context=rag_context)
                await add_follow_up_question(session_id, next_question)
                
                ai_response = {
                    "question": next_question,
                    "ready_to_code": False,
                    "language": session["ai_response"]["language"]
                }
                return ai_response
            except Exception as e:
                logger.error(f"Error generating next question: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error generating next question: {str(e)}")
        
        elif current_phase == "questioning" and total_questions == 5:
            # Check answer quality and transition to coding if good
            questions_for_quality_check = []
            if session_data["questions"]:
                questions_for_quality_check.append({
                    "question": session_data["questions"][0]["question"],
                    "answer": session_data["questions"][0]["answer"]
                })
            for q in session_data["follow_up_questions"]:
                questions_for_quality_check.append({
                    "question": q["question"],
                    "answer": q["answer"]
                })
            
            quality = await check_answer_quality(questions_for_quality_check, session_data["topic"])
            if quality == "good":
                await transition_to_coding_phase(session_id)
                ai_response = {
                    "question": "You can start coding. Ask clarifications if needed.",
                    "clarification": True,
                    "ready_to_code": True,
                    "code_stub": session["ai_response"]["code_stub"],
                    "language": session["ai_response"]["language"],
                    "tags": session["ai_response"]["tags"]
                }
                return ai_response
            else:
                ai_response = {
                    "question": "Your answers so far seem unclear or incomplete. Please review and try again before proceeding.",
                    "ready_to_code": False,
                    "language": session["ai_response"]["language"]
                }
                return ai_response
        
        elif current_phase == "coding":
            # Handle clarification requests
            if answer_request.clarification:
                try:
                    base_question = session_data["questions"][0]["question"]
                    clarification_resp = await get_clarification(base_question, answer_request.answer)
                    
                    ai_response = {
                        "clarification": clarification_resp,
                        "ready_to_code": True,
                        "language": session["ai_response"]["language"]
                    }
                    return ai_response
                except Exception as e:
                    logger.error(f"Error generating clarification: {str(e)}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Error generating clarification: {str(e)}")
            else:
                return {
                    "question": "You can only ask clarifications after starting the coding phase.",
                    "ready_to_code": False,
                    "language": session["ai_response"]["language"]
                }
        
        else:
            raise HTTPException(status_code=400, detail="Invalid session state")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/{session_id}")
async def get_interview_feedback(session_id: str):
    try:
        # Get the complete interview session
        session = await get_interview_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        session_data = session["meta"]["session_data"]
        
        # Check if feedback already exists
        if session_data.get("feedback"):
            return session_data["feedback"]
        
        # Get personalized context based on user's previous interactions
        personalized_context = await get_personalized_context(session["user_id"], session_data["topic"], session_data["user_name"])
        
        # Prepare conversation for feedback generation
        conversation = []
        
        # Add base question and answer
        if session_data["questions"]:
            conversation.append({
                "question": session_data["questions"][0]["question"],
                "answer": session_data["questions"][0]["answer"]
            })
        
        # Add follow-up questions and answers
        for q in session_data["follow_up_questions"]:
            conversation.append({
                "question": q["question"],
                "answer": q["answer"]
            })
        
        # Add clarifications
        for c in session_data["clarifications"]:
            conversation.append({
                "question": f"[Clarification] {c['question']}",
                "answer": c["answer"]
            })
        
        if not conversation:
            logger.error(f"No conversation found for session: {session_id}")
            raise HTTPException(status_code=404, detail="No conversation found for this session")
        
        # Generate feedback with personalized context
        feedback_data = await get_feedback(conversation, session_data["user_name"])
        
        # Add personalized insights to feedback
        if personalized_context["personalized_guidance"]:
            if "summary" in feedback_data:
                feedback_data["summary"] += f"\n\nPersonalized Guidance: {personalized_context['personalized_guidance']}"
            else:
                feedback_data["personalized_guidance"] = personalized_context["personalized_guidance"]
        
        # Create full feedback data for database storage (includes user patterns)
        full_feedback_data = feedback_data.copy()
        full_feedback_data["user_patterns"] = personalized_context["user_patterns"]
        
        # Create documented response (only fields specified in API documentation)
        documented_response = {
            "summary": feedback_data.get("summary", ""),
            "positive_points": feedback_data.get("positive_points", []),
            "points_to_address": feedback_data.get("points_to_address", []),
            "areas_for_improvement": feedback_data.get("areas_for_improvement", [])
        }
        
        # Save full feedback data to session (includes user patterns)
        await save_interview_feedback(session_id, full_feedback_data)
        
        return documented_response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting feedback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topics")
async def get_topics():
    """Get list of available interview topics"""
    try:
        topics = await get_available_topics()
        return {"topics": topics}
    except Exception as e:
        logger.error(f"Error getting topics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clarify")
async def ask_clarification(clarification_request: ClarificationRequest):
    try:
        logger.info(f"Requesting clarification for session: {clarification_request.session_id}")
        # Find the user_id from the latest interaction for this session
        db = await get_db()
        last_interaction = await db.user_ai_interactions.find_one({"input.session_id": clarification_request.session_id}, sort=[("timestamp", -1)])
        if not last_interaction:
            logger.error(f"Session not found: {clarification_request.session_id}")
            raise HTTPException(status_code=404, detail="Interview session not found")
        user_id = last_interaction["user_id"]
        interactions = await fetch_interactions_for_session(user_id, clarification_request.session_id)
        if not interactions:
            logger.error(f"Session not found: {clarification_request.session_id}")
            raise HTTPException(status_code=404, detail="Interview session not found")
        # Rebuild session_data as needed for clarification
        # ... (similar to answer logic) ...
        # Use the latest question for clarification
        last_question = None
        for inter in reversed(interactions):
            resp = inter.get("ai_response", {})
            meta = inter.get("meta", {})
            if meta.get("step") == "answer" and not meta.get("clarification", False):
                last_question = resp.get("question")
                break
        if not last_question:
            raise HTTPException(status_code=404, detail="No main question found")
        clarification_resp = await get_clarification(last_question, clarification_request.question)
        # Save the clarification interaction
        try:
            await save_user_ai_interaction(
                user_id=user_id,
                endpoint="mock_interview",
                input_data=clarification_request.dict(),
                ai_response={"clarification": clarification_resp},
                meta={"step": "answer", "clarification": True}
            )
        except Exception as e:
            logger.warning(f"Failed to save user-AI interaction: {e}")
        return {"clarification": clarification_resp}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing clarification request: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/interactions/{user_id}")
async def get_user_interactions(user_id: str, limit: int = 50):
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
    """Get all interview sessions for a user"""
    try:
        # Validate user_id
        if not await validate_user_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        
        sessions = await get_user_interview_sessions(user_id, limit)
        
        # Format response
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
    """Get detailed information about a specific interview session"""
    try:
        # Validate user_id
        if not await validate_user_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        
        session = await get_interview_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify the session belongs to the user
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