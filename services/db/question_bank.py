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
    Randomly selects between coding questions (isAvailableForMockInterview=True) and approach questions (question_type="approach").
    Enhanced error logging for missing data.
    """
    try:
        db = await get_db()
        logger.info(f"Fetching question for module: {module_code}")
        
        # First, check available questions for both types
        coding_count = await db.mainquestionbanks.count_documents({
            "module_code": module_code,
            "isAvailableForMockInterview": True,
            "isDeleted": False
        })
        
        approach_count = await db.mainquestionbanks.count_documents({
            "module_code": module_code,
            "question_type": "approach",
            "isDeleted": False
        })
        
        logger.info(f"Found {coding_count} coding questions and {approach_count} approach questions for module '{module_code}'")
        
        if coding_count == 0 and approach_count == 0:
            logger.error(f"NO QUESTIONS FOUND: No questions found for module_code='{module_code}' (coding: isAvailableForMockInterview=True, approach: question_type='approach')")
            raise Exception(f"No questions found for module '{module_code}'")
        
        # Determine question type to fetch
        import random
        
        # If both types available, randomly choose (60% coding, 40% approach)
        if coding_count > 0 and approach_count > 0:
            question_type = "coding" if random.random() < 0.6 else "approach"
        elif coding_count > 0:
            question_type = "coding"
        else:
            question_type = "approach"
        
        logger.info(f"Selected question type: {question_type}")
        
        # Build aggregation pipeline based on selected type
        if question_type == "coding":
            pipeline = [
                {
                    "$match": {
                        "module_code": module_code,
                        "question_type": "coding",  # Explicitly check question_type
                        "isAvailableForMockInterview": True,
                        "isDeleted": False
                    }
                },
                {"$sample": {"size": 1}}
            ]
        else:  # approach
            pipeline = [
                {
                    "$match": {
                        "module_code": module_code,
                        "question_type": "approach",
                        "isDeleted": False
                    }
                },
                {"$sample": {"size": 1}}
            ]

        # Execute aggregation pipeline
        cursor = db.mainquestionbanks.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
            logger.error(f"NO QUESTIONS RETURNED: Aggregation pipeline returned no results for module_code='{module_code}', question_type='{question_type}'")
            raise Exception(f"No questions found for module '{module_code}' (aggregation returned no results)")

        question_doc = result[0]
        actual_question_type = question_doc.get("question_type", "unknown")
        
        logger.info(f"Fetched question: {question_doc.get('question', 'No question text')}")
        logger.info(f"Expected question_type: {question_type}, Actual question_type: {actual_question_type}")
        logger.info(f"isAvailableForMockInterview: {question_doc.get('isAvailableForMockInterview', False)}")
        
        # Verify we got the correct question type
        if question_type == "coding" and actual_question_type != "coding":
            logger.error(f"TYPE MISMATCH: Expected coding question but got {actual_question_type}")
            # Try to find a coding question manually
            coding_question = await db.mainquestionbanks.find_one({
                "module_code": module_code,
                "question_type": "coding",
                "isAvailableForMockInterview": True,
                "isDeleted": False
            })
            if coding_question:
                logger.info("Found coding question manually, using that instead")
                question_doc = coding_question
                actual_question_type = "coding"
            else:
                logger.error("No coding questions found, falling back to approach")
                question_type = "approach"
        
        # Return formatted question data with interview type
        formatted_question = {
            "_id": str(question_doc.get("_id")),
            "question": question_doc.get("question", ""),
            "difficulty": question_doc.get("level", ""),
            "example": question_doc.get("description", ""),
            "tags": [t["topic_name"] for t in question_doc.get("topics", [])],
            "module_code": question_doc.get("module_code", ""),
            "topic_code": question_doc.get("topic_code", ""),
            "interview_type": question_type
        }
        
        # Add coding-specific fields only for coding questions
        if question_type == "coding":
            formatted_question.update({
                "code_stub": question_doc.get("base_code", ""),
                "language": question_doc.get("programming_language", ""),
                "solutionCode": question_doc.get("solutionCode", ""),
                "expectedOutput": question_doc.get("output", "")
            })
        
        logger.info(f"Final interview_type: {formatted_question['interview_type']}")
        return formatted_question

    except Exception as e:
        logger.error(f"Error fetching question by module: {str(e)} | module_code={module_code}", exc_info=True)
        raise

async def get_available_modules():
    """
    Get list of available modules for mock interviews.
    Returns all unique module codes that have questions with isAvailableForMockInterview=True (coding) or question_type="approach".
    Enhanced error logging for missing data.
    """
    try:
        db = await get_db()
        
        # Get all unique module codes that have available questions (coding or approach)
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"isAvailableForMockInterview": True},  # Coding questions
                        {"question_type": "approach"}           # Approach questions
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
        
        logger.info(f"Found {len(module_list)} available modules (coding: isAvailableForMockInterview=True, approach: question_type='approach')")
        if not module_list:
            logger.error("NO MODULES FOUND: No modules found with isAvailableForMockInterview=True or question_type='approach' and isDeleted=False.\nCheck if the data exists and is correctly flagged in the database.")
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