import logging
from datetime import datetime
from bson import ObjectId
from .database import get_db

logger = logging.getLogger(__name__)

def reconstruct_session_state(interactions):
    """
    Given a list of interactions (sorted by timestamp), reconstruct the session state:
    - questions: list of {question, answer}
    - clarifications: list of {clarification, response}
    - question_count, topic, etc.
    """
    session_data = {"questions": [], "clarifications": [], "question_count": 1, "topic": None}
    for inter in interactions:
        inp = inter.get("input", {})
        resp = inter.get("ai_response", {})
        meta = inter.get("meta", {})
        if meta.get("step") == "init":
            session_data["topic"] = inp.get("topic")
            session_data["questions"].append({"question": resp.get("base_question"), "answer": ""})
            session_data["question_count"] = 1
        elif meta.get("step") == "answer":
            if "clarification" in meta and meta["clarification"]:
                session_data["clarifications"].append({"clarification": inp.get("answer"), "response": resp.get("clarification")})
            else:
                if session_data["questions"]:
                    session_data["questions"][-1]["answer"] = inp.get("answer")
                if "question" in resp:
                    session_data["questions"].append({"question": resp["question"], "answer": ""})
                session_data["question_count"] = session_data.get("question_count", 1) + 1
    return session_data

async def create_interview_session(user_id: str, session_id: str, topic: str, user_name: str, base_question_data: dict, first_follow_up: str, base_question_id=None):
    """Create a new interview session document in user_ai_interactions collection"""
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            save_user_id = object_id
        except:
            save_user_id = user_id
        
        session_doc = {
            "user_id": save_user_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
            "endpoint": "mock_interview",
            "input": {
                "topic": topic,
                "user_name": user_name,
                "session_id": session_id
            },
            "ai_response": {
                "session_id": session_id,
                "base_question": base_question_data["question"],
                "difficulty": base_question_data["difficulty"],
                "example": base_question_data["example"],
                "code_stub": base_question_data["code_stub"],
                "tags": base_question_data["tags"],
                "language": base_question_data["language"],
                "first_follow_up": first_follow_up
            },
            "meta": {
                "step": "init",
                "session_type": "structured",
                "session_data": {
                    "topic": topic,
                    "user_name": user_name,
                    "status": "in_progress",
                    "current_phase": "questioning",
                    "base_question_id": base_question_id,
                    "total_questions": 1,
                    "questions": [
                        {
                            "question": base_question_data["question"],
                            "answer": "",
                            "timestamp": datetime.utcnow(),
                            "question_type": "base"
                        }
                    ],
                    "follow_up_questions": [
                        {
                            "question": first_follow_up,
                            "answer": "",
                            "timestamp": datetime.utcnow(),
                            "question_type": "follow_up"
                        }
                    ],
                    "clarifications": [],
                    "feedback": None
                }
            }
        }
        
        result = await db.user_ai_interactions.insert_one(session_doc)
        logger.info(f"Created interview session: {session_id} with _id: {result.inserted_id}")
        return result.inserted_id
    except Exception as e:
        logger.error(f"Error creating interview session: {str(e)}", exc_info=True)
        raise

async def get_interview_session(session_id: str):
    """Get a complete interview session by session_id"""
    try:
        db = await get_db()
        
        session = await db.user_ai_interactions.find_one({"session_id": session_id})
        return session
    except Exception as e:
        logger.error(f"Error getting interview session: {str(e)}", exc_info=True)
        raise

async def update_interview_session_answer(session_id: str, answer: str, is_clarification: bool = False):
    """Update the interview session with a new answer"""
    try:
        db = await get_db()
        
        # Get the current session
        session = await get_interview_session(session_id)
        if not session:
            raise Exception(f"Session not found: {session_id}")
        
        # Update the session data in the meta field
        session_data = session["meta"]["session_data"]
        
        if is_clarification:
            # Add clarification
            clarification = {
                "question": "Clarification request",
                "answer": answer,
                "timestamp": datetime.utcnow()
            }
            session_data["clarifications"].append(clarification)
        else:
            # Update the latest follow-up question's answer
            follow_up_questions = session_data.get("follow_up_questions", [])
            if not follow_up_questions:
                raise Exception("No follow-up questions found")
            
            # Find the first unanswered question
            for question in follow_up_questions:
                if not question.get("answer"):
                    question["answer"] = answer
                    break
            else:
                # If no unanswered question found, add answer to the last question
                if follow_up_questions:
                    follow_up_questions[-1]["answer"] = answer
        
        # Update the document
        await db.user_ai_interactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "meta.session_data": session_data,
                    "timestamp": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Updated interview session: {session_id} with answer")
    except Exception as e:
        logger.error(f"Error updating interview session: {str(e)}", exc_info=True)
        raise

async def add_follow_up_question(session_id: str, question: str):
    """Add a new follow-up question to the session"""
    try:
        db = await get_db()
        
        # Get the current session
        session = await get_interview_session(session_id)
        if not session:
            raise Exception(f"Session not found: {session_id}")
        
        # Update the session data
        session_data = session["meta"]["session_data"]
        
        new_question = {
            "question": question,
            "answer": "",
            "timestamp": datetime.utcnow(),
            "question_type": "follow_up"
        }
        
        session_data["follow_up_questions"].append(new_question)
        session_data["total_questions"] += 1
        
        # Update the document
        await db.user_ai_interactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "meta.session_data": session_data,
                    "timestamp": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Added follow-up question to session: {session_id}")
    except Exception as e:
        logger.error(f"Error adding follow-up question: {str(e)}", exc_info=True)
        raise

async def transition_to_coding_phase(session_id: str):
    """Transition the session to coding phase"""
    try:
        db = await get_db()
        
        # Get the current session
        session = await get_interview_session(session_id)
        if not session:
            raise Exception(f"Session not found: {session_id}")
        
        # Update the session data
        session_data = session["meta"]["session_data"]
        session_data["current_phase"] = "coding"
        
        # Update the document
        await db.user_ai_interactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "meta.session_data": session_data,
                    "timestamp": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Transitioned session {session_id} to coding phase")
    except Exception as e:
        logger.error(f"Error transitioning to coding phase: {str(e)}", exc_info=True)
        raise

async def save_interview_feedback(session_id: str, feedback_data: dict):
    """Save feedback for the completed interview session"""
    try:
        db = await get_db()
        
        # Get the current session
        session = await get_interview_session(session_id)
        if not session:
            raise Exception(f"Session not found: {session_id}")
        
        # Update the session data
        session_data = session["meta"]["session_data"]
        session_data["feedback"] = feedback_data
        session_data["status"] = "completed"
        session_data["current_phase"] = "completed"
        
        # Update the document
        await db.user_ai_interactions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "meta.session_data": session_data,
                    "timestamp": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Saved feedback for session: {session_id}")
    except Exception as e:
        logger.error(f"Error saving feedback: {str(e)}", exc_info=True)
        raise

async def get_user_interview_sessions(user_id: str, limit: int = 20):
    """Get all interview sessions for a user"""
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            query_user_id = object_id
        except:
            query_user_id = user_id
        
        sessions = await db.user_ai_interactions.find(
            {
                "user_id": query_user_id,
                "meta.session_type": "structured"
            }
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        return sessions
    except Exception as e:
        logger.error(f"Error getting user interview sessions: {str(e)}", exc_info=True)
        raise 