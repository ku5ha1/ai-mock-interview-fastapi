import logging
from bson import ObjectId
from .database import get_db

logger = logging.getLogger(__name__)

async def fetch_base_question(topic: str):
    """Fetch base question for a topic from mainquestionbanks"""
    try:
        db = await get_db()
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
            "_id": str(question_doc.get("_id")),
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

async def get_available_topics():
    """Get list of available interview topics"""
    try:
        db = await get_db()
        
        # Get all topics from interview_topics collection
        topics = await db.interview_topics.find({}).to_list(length=None)
        
        # Extract topic names
        topic_names = [topic["topic"] for topic in topics if "topic" in topic]
        
        logger.info(f"Found {len(topic_names)} available topics")
        return topic_names
        
    except Exception as e:
        logger.error(f"Error getting available topics: {str(e)}", exc_info=True)
        return []

async def get_user_name_from_id(user_id: str) -> str:
    """Get user name from user ID"""
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            user = await db.users.find_one({"_id": object_id})
        except:
            user = await db.users.find_one({"_id": user_id})
        if user and "user_name" in user:
            return user["user_name"]
        return ""
    except Exception:
        return "" 