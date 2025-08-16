"""
Data Models and Schemas

This module contains Pydantic models for request/response validation
and data structure definitions used throughout the API.
"""

import asyncio
import numpy as np
from typing import List
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class InterviewInit(BaseModel):
    """
    Request model for initializing a new mock interview session.
    Contains module_code selection and user identification.
    """
    module_code: str  # Changed from 'topic' to 'module_code' for clarity
    user_id: str

class InterviewResponse(BaseModel):
    """
    Response model for interview questions and answers.
    Used for conversation tracking during interviews.
    """
    question: str
    answer: str = ""

class AnswerRequest(BaseModel):
    """
    Request model for submitting user answers during interviews.
    Includes clarification flag for coding phase interactions.
    """
    session_id: str
    answer: str
    clarification: bool = False

class ClarificationRequest(BaseModel):
    """
    Request model for seeking clarification during coding phase.
    Used when users need more information about the problem.
    """
    session_id: str
    question: str

class ApproachAnalysisRequest(BaseModel):
    """
    Request model for analyzing user's problem-solving approach.
    Includes optional question_id for progress tracking.
    """
    question: str
    user_answer: str
    user_id: str
    question_id: str = None  # type: ignore # Optional, for progress checks

class CodeOptimizationRequest(BaseModel):
    """
    Request model for code optimization requests.
    Includes sample input/output for testing optimized code.
    """
    question: str
    description: str
    user_code: str
    sample_input: str
    sample_output: str
    user_id: str

class FeedbackResponse(BaseModel):
    """
    Response model for structured feedback.
    Contains strengths, areas for improvement, and scoring.
    """
    feedback: str
    strengths: List[str]
    areas_for_improvement: List[str]
    score: int



