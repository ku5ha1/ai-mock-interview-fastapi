from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from routes.mock_interview import router as mock_interview_router
from routes.code_optimization import router as code_optimization_router
from routes.approach_analysis import router as approach_analysis_router
from routes.rag import router as rag_router
from services.db import create_indexes, get_db, check_collections
import logging
import asyncio
import time
from fastapi.responses import JSONResponse
import os
import traceback
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout  
)
logger = logging.getLogger(__name__)

IS_LAMBDA = bool(os.getenv('AWS_LAMBDA_FUNCTION_NAME'))

app = FastAPI(title="Mock Interview API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_retriever = None

@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        logger.info(f"Incoming request - Path: {request.url.path}, Method: {request.method}")
        env_vars = {k: v for k, v in os.environ.items() if k in ['MONGODB_URI', 'DB_NAME']}
        logger.info(f"Environment variables present: {list(env_vars.keys())}")
        response = await call_next(request)
        if response.status_code >= 400:
            logger.error(f"Error Response - Status: {response.status_code}, Path: {request.url.path}, Method: {request.method}")
        return response
    except Exception as e:
        error_msg = f"Request Error - Path: {request.url.path}, Method: {request.method}, Error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "message": "Internal server error",
                "detail": str(e),
                "path": request.url.path,
                "method": request.method,
                "traceback": traceback.format_exc() if IS_LAMBDA else None
            }
        )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP Error - Status: {exc.status_code}, Path: {request.url.path}, Detail: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail}
    )

@app.on_event("startup")
async def startup_event():
    try:
        # Log startup attempt
        logger.info("Starting application initialization...")
        
        # Check environment variables
        if not os.getenv("MONGODB_URI"):
            raise ValueError("MONGODB_URI environment variable is not set")
        if not os.getenv("DB_NAME"):
            raise ValueError("DB_NAME environment variable is not set")
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        logger.info("Environment variables validated")
        
        logger.info("Attempting to connect to database...")
        db = await get_db()
        logger.info("Database connection successful")
        
        logger.info("Creating database indexes...")
        await create_indexes()
        logger.info("Database indexes created successfully")
        
        logger.info("Checking database collections...")
        await check_collections()
        logger.info("Database collections verified")
        
        try:
            logger.info("Initializing RAG retriever...")
            from services.rag.retriever_factory import get_rag_retriever
            global rag_retriever
            rag_retriever = await get_rag_retriever()
            logger.info("RAGRetriever initialized during startup")
        except Exception as e:
            logger.warning(f"Failed to initialize RAGRetriever: {str(e)}")
            
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        error_msg = f"Startup Error: {str(e)}\n{traceback.format_exc()}"
        logger.warning(f"Failed to initialize RAGRetriever: {str(e)}")
        logger.error(error_msg)
        if IS_LAMBDA:
            raise

app.include_router(mock_interview_router, prefix="/mock")
app.include_router(code_optimization_router, prefix="/code")
app.include_router(approach_analysis_router, prefix="/approach")
app.include_router(rag_router)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring
    """
    try:
        db = await get_db()
        await db.command("ping") # type: ignore
        
        try:
            from services.rag.retriever_factory import get_retriever_status
            rag_status = get_retriever_status()
        except Exception as e:
            rag_status = {"initialized": False, "error": str(e)}
        
        return {
            "status": "healthy",
            "database": "connected",
            "rag_system": rag_status,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)