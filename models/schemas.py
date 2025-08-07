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

class CodeExecutionRequest(BaseModel):
    """
    Request model for executing user code.
    Includes code, input data, and execution parameters.
    """
    session_id: str
    code: str
    input_data: str = ""
    language: str = "python"
    timeout_seconds: int = 10

class CodeAssessmentRequest(BaseModel):
    """
    Request model for comprehensive code assessment.
    Includes code, question context, and assessment parameters.
    """
    session_id: str
    code: str
    question: str
    sample_input: str = ""
    sample_output: str = ""
    language: str = "python"

class CodeExecutionResult(BaseModel):
    """
    Response model for code execution results.
    Includes output, errors, performance metrics.
    """
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    memory_usage: float = 0.0
    success: bool

class CodeAssessmentResult(BaseModel):
    """
    Response model for code assessment results.
    Includes performance analysis, quality metrics, and recommendations.
    """
    execution_result: CodeExecutionResult
    performance_analysis: dict
    code_quality_score: float
    complexity_analysis: dict
    optimization_suggestions: list
    best_practices_feedback: list
    overall_score: float

