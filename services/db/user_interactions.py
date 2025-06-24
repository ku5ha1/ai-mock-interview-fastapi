import logging
from datetime import datetime
from bson import ObjectId
from .database import get_db

logger = logging.getLogger(__name__)

async def save_user_ai_interaction(user_id: str, endpoint: str, input_data: dict, ai_response: dict, meta: dict = None):
    """Save user-AI interaction to database"""
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
    """Fetch interactions for a specific session"""
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
    """Fetch user's interaction history"""
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

async def fetch_user_session_summaries(user_id: str, limit: int = 20):
    """Fetch user session summaries"""
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