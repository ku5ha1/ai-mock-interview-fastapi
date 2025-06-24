import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime

logger = logging.getLogger(__name__)

# Database connection
client = None
db = None

async def get_db():
    """Get database instance"""
    global db
    if db is None:
        await connect_to_db()
    return db

async def connect_to_db():
    """Connect to MongoDB"""
    global client, db
    try:
        mongodb_uri = os.getenv("MONGODB_URI")
        db_name = os.getenv("DB_NAME")
        
        if not mongodb_uri or not db_name:
            raise ValueError("MONGODB_URI and DB_NAME must be set in environment variables")
        
        client = AsyncIOMotorClient(mongodb_uri)
        db = client[db_name]
        
        # Test connection
        await db.command("ping")
        logger.info(f"Connected to MongoDB database: {db_name}")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        raise

async def create_indexes():
    """Create necessary database indexes"""
    try:
        db = await get_db()
        
        # Create indexes for user_ai_interactions collection
        await db.user_ai_interactions.create_index([("user_id", 1)])
        await db.user_ai_interactions.create_index([("session_id", 1)])
        await db.user_ai_interactions.create_index([("timestamp", -1)])
        await db.user_ai_interactions.create_index([("endpoint", 1)])
        
        # Create indexes for users collection
        await db.users.create_index([("_id", 1)])
        
        # Create indexes for interview_topics collection
        await db.interview_topics.create_index([("topic", 1)], unique=True)
        
        # Create indexes for mainquestionbanks collection
        await db.mainquestionbanks.create_index([("topicId", 1)])
        await db.mainquestionbanks.create_index([("isAvailableForMock", 1)])
        await db.mainquestionbanks.create_index([("isAvailableForMockInterview", 1)])
        await db.mainquestionbanks.create_index([("isDeleted", 1)])
        
        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating indexes: {str(e)}")
        raise

async def check_collections():
    """Check if required collections exist and have data"""
    try:
        db = await get_db()
        
        collections = await db.list_collection_names()
        logger.info(f"Available collections: {collections}")
        
        # Check required collections
        required_collections = ["users", "interview_topics", "mainquestionbanks", "user_ai_interactions"]
        
        for collection_name in required_collections:
            if collection_name in collections:
                count = await db[collection_name].count_documents({})
                logger.info(f"Collection '{collection_name}' exists with {count} documents")
            else:
                logger.warning(f"Collection '{collection_name}' not found")
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking collections: {str(e)}")
        return False

async def validate_user_id(user_id: str) -> bool:
    """Validate if user_id exists in the database"""
    try:
        db = await get_db()
        
        # Convert string user_id to ObjectId if it's a valid ObjectId format
        try:
            object_id = ObjectId(user_id)
            user = await db.users.find_one({"_id": object_id})
        except:
            user = await db.users.find_one({"_id": user_id})
        
        return user is not None
        
    except Exception as e:
        logger.error(f"Error validating user_id: {str(e)}")
        return False 