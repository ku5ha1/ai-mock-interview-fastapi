import asyncio
import numpy as np
from typing import List
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class InterviewInit(BaseModel):
    topic: str
    user_id: str

class InterviewResponse(BaseModel):
    question: str
    answer: str = ""

class AnswerRequest(BaseModel):
    session_id: str
    answer: str
    clarification: bool = False

class ClarificationRequest(BaseModel):
    session_id: str
    question: str

class ApproachAnalysisRequest(BaseModel):
    question: str
    user_answer: str
    user_id: str

class CodeOptimizationRequest(BaseModel):
    question: str
    user_code: str
    sample_input: str
    sample_output: str
    user_id: str

class FeedbackResponse(BaseModel):
    feedback: str
    strengths: List[str]
    areas_for_improvement: List[str]
    score: int

