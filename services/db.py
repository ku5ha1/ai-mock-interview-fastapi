from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import logging
import random
from datetime import datetime
from bson import ObjectId
 
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
if not MONGO_URI:
    raise ValueError("MONGODB_URI environment variable is not set")
 
DB_NAME = os.getenv("DB_NAME", "test")
if not DB_NAME:
    raise ValueError("DB_NAME environment variable is not set")
 
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

async def get_db():
    """Get database instance"""
    return db
 
async def fetch_base_question(topic: str):
    """Fetch base question for a topic from mainquestionbanks"""
    try:
        logger.info(f"Fetching base question for topic: {topic}")
        
        topic_doc = await db.interview_topics.find_one({"topic": topic})
        if not topic_doc:
            raise Exception(f"Topic '{topic}' not found")
        
        topic_id = topic_doc["_id"]
        logger.info(f"Found topic ID: {topic_id}")

        pipeline = [
            {
                "$match": {
                    "topicId": topic_id,
                    "$or": [
                        {"isAvailableForMock": True},
                        {"isAvailableForMockInterview": True}
                    ],
                    "isDeleted": False
                }
            },
            {"$sample": {"size": 1}}
        ]

        count = await db.mainquestionbanks.count_documents({
            "topicId": topic_id,
            "$or": [
                {"isAvailableForMock": True},
                {"isAvailableForMockInterview": True}
            ],
            "isDeleted": False
        })
        logger.warning(f"Found {count} available questions for topic '{topic}' with topicId {topic_id}")

        cursor = db.mainquestionbanks.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            logger.warning(f"No questions found for topic '{topic}' (topicId: {topic_id})")
            raise Exception(f"No questions found for topic '{topic}' (topicId: {topic_id})")

        question_doc = result[0]
        logger.info(f"Fetched question: {question_doc.get('question', 'No question text')}")

        return {
            "question": question_doc.get("question", ""),
            "code_stub": question_doc.get("base_code", ""),
            "language": question_doc.get("programming_language", ""),
            "difficulty": question_doc.get("level", ""),
            "example": question_doc.get("description", ""),
            "tags": [t["topic_name"] for t in question_doc.get("topics", [])]
        }

    except Exception as e:
        logger.error(f"Error fetching base question: {str(e)}", exc_info=True)
        raise
    
async def create_indexes():
    """Create necessary indexes"""
    try:
        # Check if the index exists before trying to drop it
        existing_indexes = await db.interview_topics.index_information()
        if "topic_1" in existing_indexes:
            await db.interview_topics.drop_index("topic_1")
            logger.info("Dropped existing topic_1 index")
        
        await db.interview_topics.create_index("topic", unique=True)
        logger.info("Created new unique index on 'topic'")
    except Exception as e:
        logger.error(f"Error creating indexes: {str(e)}")
        raise
        
async def get_available_topics():
    """Get list of available topics"""
    try:
        # First check if the collection exists
        collections = await db.list_collection_names()
        logger.error(f"Available collections: {collections}")
       
        if "interview_topics" not in collections:
            logger.error("interview_topics collection does not exist")
            return []
       
        topics = await db.interview_topics.find({}).to_list(length=None)
        logger.error(f"Raw topics data: {topics}")
       
        available_topics = []
        for topic in topics:
            if "topic" in topic:
                available_topics.append(topic["topic"])
            else:
                logger.error(f"Topic document missing 'topic' field: {topic}")
               
        logger.error(f"Available topics: {available_topics}")
        return available_topics
    except Exception as e:
        logger.error(f"Error getting topics: {str(e)}", exc_info=True)
        raise
 
async def check_collections():
    """Check MongoDB collections and their contents (updated version)"""
    try:
        # List all collections
        collections = await db.list_collection_names()
        logger.info(f"Available collections: {collections}")

        if "interview_topics" in collections:
            topics = await db.interview_topics.find({}).to_list(length=10)
            logger.info(f"Topics in interview_topics collection: {topics}")
        else:
            logger.info("interview_topics collection does not exist")

        if "mainquestionbanks" in collections:
            sample = await db.mainquestionbanks.find(
                {}, 
                {"question": 1, "topicId": 1, "isAvailableForMock": 1}
            ).limit(5).to_list(length=5)
            logger.info(f"Sample from mainquestionbanks: {sample}")
        else:
            logger.info("mainquestionbanks collection does not exist")

    except Exception as e:
        logger.error(f"Error checking collections: {str(e)}", exc_info=True)
        raise

async def validate_user_id(user_id: str) -> bool:
    """Check if a user with the given user_id exists in the users collection."""
    try:
        db = await get_db()
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            user = await db.users.find_one({"_id": object_id})
        except:
            # If user_id is not a valid ObjectId format, try as string
            user = await db.users.find_one({"_id": user_id})
        return user is not None
    except Exception as e:
        logger.error(f"Error validating user_id {user_id}: {str(e)}")
        return False

async def save_user_ai_interaction(user_id: str, endpoint: str, input_data: dict, ai_response: dict, meta: dict = None):
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            save_user_id = object_id
        except:
            save_user_id = user_id
        
        doc = {
            "user_id": save_user_id,
            "timestamp": datetime.utcnow(),
            "endpoint": endpoint,
            "input": input_data,
            "ai_response": ai_response
        }
        if meta:
            doc["meta"] = meta
        
        logger.info(f"Attempting to save interaction document with user_id: {save_user_id}")
        result = await db.user_ai_interactions.insert_one(doc)
        logger.info(f"Successfully saved interaction with _id: {result.inserted_id}")
        return result
    except Exception as e:
        logger.error(f"Error saving user-AI interaction: {str(e)}", exc_info=True)
        raise

async def fetch_interactions_for_session(user_id: str, session_id: str):
    db = await get_db()
    # Convert string user_id to ObjectId if it's a valid ObjectId format
    try:
        object_id = ObjectId(user_id)
        query_user_id = object_id
    except:
        query_user_id = user_id
    
    logger.info(f"Looking for interactions with user_id: {query_user_id}, session_id: {session_id}")
    
    # First, let's see what interactions exist for this user
    all_user_interactions = await db.user_ai_interactions.find({"user_id": query_user_id}).to_list(length=None)
    logger.info(f"Found {len(all_user_interactions)} total interactions for user {user_id}")
    
    # Log the session_ids in the user's interactions
    for interaction in all_user_interactions:
        input_data = interaction.get("input", {})
        session_id_in_db = input_data.get("session_id")
        logger.info(f"Interaction session_id: {session_id_in_db}")
    
    interactions = await db.user_ai_interactions.find({
        "user_id": query_user_id,
        "input.session_id": session_id
    }).sort("timestamp", 1).to_list(length=None)
    
    logger.info(f"Found {len(interactions)} interactions for session {session_id}")
    return interactions

async def fetch_user_history(user_id: str, limit: int = 50):
    db = await get_db()
    # Convert string user_id to ObjectId if it's a valid ObjectId format
    try:
        object_id = ObjectId(user_id)
        query_user_id = object_id
    except:
        query_user_id = user_id
    
    interactions = await db.user_ai_interactions.find({
        "user_id": query_user_id
    }).sort("timestamp", -1).limit(limit).to_list(length=limit)
    return interactions

# Advanced session reconstruction

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

async def fetch_user_session_summaries(user_id: str, limit: int = 20):
    db = await get_db()
    # Convert string user_id to ObjectId if it's a valid ObjectId format
    try:
        object_id = ObjectId(user_id)
        query_user_id = object_id
    except:
        query_user_id = user_id
    
    # Aggregate sessions by session_id
    pipeline = [
        {"$match": {"user_id": query_user_id}},
        {"$group": {
            "_id": "$input.session_id",
            "first": {"$first": "$timestamp"},
            "last": {"$last": "$timestamp"},
            "topic": {"$first": "$input.topic"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"last": -1}},
        {"$limit": limit}
    ]
    summaries = await db.user_ai_interactions.aggregate(pipeline).to_list(length=limit)
    # Format output
    return [
        {
            "session_id": s["_id"],
            "topic": s.get("topic"),
            "start_time": s.get("first"),
            "end_time": s.get("last"),
            "interaction_count": s.get("count")
        }
        for s in summaries if s["_id"]
    ]

async def create_interview_session(user_id: str, session_id: str, topic: str, user_name: str, base_question_data: dict, first_follow_up: str):
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

async def get_interview_session(session_id: str):
    """Get a complete interview session by session_id"""
    try:
        db = await get_db()
        
        session = await db.user_ai_interactions.find_one({"session_id": session_id})
        return session
    except Exception as e:
        logger.error(f"Error getting interview session: {str(e)}", exc_info=True)
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

async def get_user_interaction_history(user_id: str, limit: int = 20):
    """Get user's interaction history for personalization"""
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            query_user_id = object_id
        except:
            query_user_id = user_id
        
        # Get recent interactions across all endpoints
        interactions = await db.user_ai_interactions.find(
            {"user_id": query_user_id}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        return interactions
    except Exception as e:
        logger.error(f"Error getting user interaction history: {str(e)}", exc_info=True)
        raise

async def analyze_user_patterns(user_id: str):
    """Analyze user patterns from previous interactions for personalization"""
    try:
        interactions = await get_user_interaction_history(user_id, limit=50)
        
        patterns = {
            "topics_attempted": [],
            "common_weaknesses": [],
            "strengths": [],
            "average_scores": [],
            "preferred_languages": [],
            "session_completion_rate": 0,
            "total_sessions": len(interactions)
        }
        
        completed_sessions = 0
        total_sessions = 0
        
        for interaction in interactions:
            endpoint = interaction.get("endpoint", "")
            
            if endpoint == "mock_interview":
                total_sessions += 1
                session_data = interaction.get("meta", {}).get("session_data", {})
                if session_data.get("status") == "completed":
                    completed_sessions += 1
                
                # Extract topic
                topic = session_data.get("topic")
                if topic and topic not in patterns["topics_attempted"]:
                    patterns["topics_attempted"].append(topic)
                
                # Extract language preference
                language = session_data.get("metadata", {}).get("language")
                if language and language not in patterns["preferred_languages"]:
                    patterns["preferred_languages"].append(language)
                
                # Extract feedback insights
                feedback = session_data.get("feedback")
                if feedback:
                    if "points_to_address" in feedback:
                        patterns["common_weaknesses"].extend(feedback["points_to_address"])
                    if "positive_points" in feedback:
                        patterns["strengths"].extend(feedback["positive_points"])
                    if "score" in feedback:
                        patterns["average_scores"].append(feedback["score"])
            
            elif endpoint == "approach_analysis":
                # Extract approach analysis insights
                ai_response = interaction.get("ai_response", {})
                if "areas_for_improvement" in ai_response:
                    patterns["common_weaknesses"].extend(ai_response["areas_for_improvement"])
                if "strengths" in ai_response:
                    patterns["strengths"].extend(ai_response["strengths"])
                if "score" in ai_response:
                    patterns["average_scores"].append(ai_response["score"])
            
            elif endpoint == "code_optimization":
                # Extract code optimization insights
                ai_response = interaction.get("ai_response", {})
                if "optimization_summary" in ai_response:
                    # Could extract patterns from optimization summaries
                    pass
        
        # Calculate completion rate
        if total_sessions > 0:
            patterns["session_completion_rate"] = completed_sessions / total_sessions
        
        # Get most common patterns (top 3)
        from collections import Counter
        patterns["common_weaknesses"] = [item for item, count in Counter(patterns["common_weaknesses"]).most_common(3)]
        patterns["strengths"] = [item for item, count in Counter(patterns["strengths"]).most_common(3)]
        
        # Calculate average score
        if patterns["average_scores"]:
            patterns["average_score"] = sum(patterns["average_scores"]) / len(patterns["average_scores"])
        else:
            patterns["average_score"] = None
        
        return patterns
    except Exception as e:
        logger.error(f"Error analyzing user patterns: {str(e)}", exc_info=True)
        return {}

async def get_personalized_context(user_id: str, current_topic: str = None, user_name: str = None):
    """Get personalized context based on user's previous interactions"""
    try:
        patterns = await analyze_user_patterns(user_id)
        
        personalized_context = {
            "user_patterns": patterns,
            "personalized_guidance": ""
        }
        
        # Generate intelligent, contextual guidance based on patterns
        guidance_parts = []
        
        # Use user's name naturally in personalized messages if available
        name_reference = f"{user_name}" if user_name else "You"
        
        # Provide topic-specific guidance if available
        if current_topic:
            if current_topic in patterns.get("topics_attempted", []):
                guidance_parts.append(f"Since you've worked on {current_topic} before, leverage that experience to refine your approach this time.")
            else:
                guidance_parts.append(f"This is your first time with {current_topic} - focus on understanding the core concepts and building a solid foundation.")
        
        # Provide intelligent performance-based guidance
        if patterns.get("average_score"):
            if patterns["average_score"] < 6:
                guidance_parts.append("Consider taking a bit more time to think through answers thoroughly - this often leads to more comprehensive responses.")
            elif patterns["average_score"] > 8:
                guidance_parts.append("You're performing well! Try to challenge yourself with more complex scenarios to push your skills further.")
        
        # Provide specific improvement areas if available
        if patterns.get("common_weaknesses"):
            weaknesses = ', '.join(patterns['common_weaknesses'][:2])
            guidance_parts.append(f"Based on your previous sessions, pay extra attention to: {weaknesses}")
        
        # Acknowledge strengths naturally
        if patterns.get("strengths"):
            strengths = ', '.join(patterns['strengths'][:2])
            guidance_parts.append(f"Your strong areas include: {strengths} - build on these in your responses.")
        
        # Session completion guidance
        if patterns.get("session_completion_rate") < 0.5:
            guidance_parts.append("Completing more interview sessions would help build consistency in your approach and confidence.")
        
        personalized_context["personalized_guidance"] = " ".join(guidance_parts)
        
        return personalized_context
    except Exception as e:
        logger.error(f"Error getting personalized context: {str(e)}", exc_info=True)
        return {"user_patterns": {}, "personalized_guidance": ""}

async def get_user_name_from_history(user_id: str) -> str:
    """Get user name from their most recent session"""
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            query_user_id = object_id
        except:
            query_user_id = user_id
        
        # Get the most recent session for this user
        session = await db.user_ai_interactions.find_one(
            {
                "user_id": query_user_id,
                "meta.session_type": "structured"
            },
            sort=[("timestamp", -1)]
        )
        
        if session and "meta" in session and "session_data" in session["meta"]:
            return session["meta"]["session_data"].get("user_name", "Candidate")
        
        return "Candidate"
    except Exception as e:
        logger.error(f"Error getting user name from history: {str(e)}", exc_info=True)
        return "Candidate"

async def get_user_name_from_id(user_id: str) -> str:
    db = await get_db()
    try:
        from bson import ObjectId
        try:
            object_id = ObjectId(user_id)
            user = await db.users.find_one({"_id": object_id})
        except:
            user = await db.users.find_one({"_id": user_id})
        if user and "name" in user:
            return user["name"]
        return ""
    except Exception:
        return ""
 