"""
Question Bank Database Module

This module handles question bank operations and topic management.
Provides functions for fetching questions, topics, and user information.
"""

import logging
from bson import ObjectId
from .database import get_db

logger = logging.getLogger(__name__)

async def fetch_base_question(topic: str):
    """
    Fetch base question for a topic from mainquestionbanks.
    Returns randomly selected question with metadata for interviews.
    """
    try:
        db = await get_db()
        logger.info(f"Fetching base question for topic: {topic}")
        
        # Find topic document
        topic_doc = await db.interview_topics.find_one({"topic": topic})
        if not topic_doc:
            raise Exception(f"Topic '{topic}' not found")
        
        topic_id = topic_doc["_id"]
        logger.info(f"Found topic ID: {topic_id}")

        # Build aggregation pipeline for random question selection
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

        # Check available question count
        count = await db.mainquestionbanks.count_documents({
            "topicId": topic_id,
            "$or": [
                {"isAvailableForMock": True},
                {"isAvailableForMockInterview": True}
            ],
            "isDeleted": False
        })
        logger.warning(f"Found {count} available questions for topic '{topic}' with topicId {topic_id}")

        # Execute aggregation pipeline
        cursor = db.mainquestionbanks.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            logger.warning(f"No questions found for topic '{topic}' (topicId: {topic_id})")
            raise Exception(f"No questions found for topic '{topic}' (topicId: {topic_id})")

        question_doc = result[0]
        logger.info(f"Fetched question: {question_doc.get('question', 'No question text')}")

        # Return formatted question data
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
    """
    Get list of available interview topics.
    Returns all topics from interview_topics collection.
    """
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

async def fetch_question_by_module(module_code: str):
    """
    Fetch a random question for a specific module from mainquestionbanks.
    Returns randomly selected question with metadata for interviews.
    Filters by module_code and isAvailableForMock = True or isAvailableForMockInterview = True.
    Enhanced error logging for missing data.
    """
    try:
        db = await get_db()
        logger.info(f"Fetching question for module: {module_code}")
        
        # Build aggregation pipeline for random question selection
        pipeline = [
            {
                "$match": {
                    "module_code": module_code,
                    "$or": [
                        {"isAvailableForMock": True},
                        {"isAvailableForMockInterview": True}
                    ],
                    "isDeleted": False
                }
            },
            {"$sample": {"size": 1}}
        ]

        # Check available question count
        count = await db.mainquestionbanks.count_documents({
            "module_code": module_code,
            "$or": [
                {"isAvailableForMock": True},
                {"isAvailableForMockInterview": True}
            ],
            "isDeleted": False
        })
        logger.info(f"Found {count} available questions for module '{module_code}' (isAvailableForMock/Interview, isDeleted=False)")

        if count == 0:
            logger.error(f"NO QUESTIONS FOUND: No questions found for module_code='{module_code}' with isAvailableForMock=True or isAvailableForMockInterview=True and isDeleted=False.\nCheck if the data exists and is correctly flagged in the database.")
            raise Exception(f"No questions found for module '{module_code}' with isAvailableForMock=True or isAvailableForMockInterview=True")

        # Execute aggregation pipeline
        cursor = db.mainquestionbanks.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            logger.error(f"NO QUESTIONS RETURNED: Aggregation pipeline returned no results for module_code='{module_code}'. Pipeline: {pipeline}")
            raise Exception(f"No questions found for module '{module_code}' (aggregation returned no results)")

        question_doc = result[0]
        logger.info(f"Fetched question: {question_doc.get('question', 'No question text')}")

        # Return formatted question data
        return {
            "_id": str(question_doc.get("_id")),
            "question": question_doc.get("question", ""),
            "code_stub": question_doc.get("base_code", ""),
            "language": question_doc.get("programming_language", ""),
            "difficulty": question_doc.get("level", ""),
            "example": question_doc.get("description", ""),
            "tags": [t["topic_name"] for t in question_doc.get("topics", [])],
            "module_code": question_doc.get("module_code", ""),
            "topic_code": question_doc.get("topic_code", "")
        }

    except Exception as e:
        logger.error(f"Error fetching question by module: {str(e)} | module_code={module_code}", exc_info=True)
        raise

async def get_available_modules():
    """
    Get list of available modules for mock interviews.
    Returns all unique module codes that have questions with isAvailableForMock=True or isAvailableForMockInterview=True.
    Enhanced error logging for missing data.
    """
    try:
        db = await get_db()
        
        # Get all unique module codes that have available questions
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"isAvailableForMock": True},
                        {"isAvailableForMockInterview": True}
                    ],
                    "isDeleted": False
                }
            },
            {
                "$group": {
                    "_id": "$module_code",
                    "question_count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        modules = await db.mainquestionbanks.aggregate(pipeline).to_list(length=None)
        
        # Format the response
        module_list = [
            {
                "module_code": module["_id"],
                "question_count": module["question_count"]
            }
            for module in modules if module["_id"]
        ]
        
        logger.info(f"Found {len(module_list)} available modules (isAvailableForMock/Interview, isDeleted=False)")
        if not module_list:
            logger.error("NO MODULES FOUND: No modules found with isAvailableForMock=True or isAvailableForMockInterview=True and isDeleted=False.\nCheck if the data exists and is correctly flagged in the database.")
        return module_list
        
    except Exception as e:
        logger.error(f"Error getting available modules: {str(e)}", exc_info=True)
        return []

async def get_user_name_from_id(user_id: str) -> str:
    """
    Get user name from user ID.
    Handles both ObjectId and string user IDs.
    """
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