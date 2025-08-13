"""
Personalization Database Module

This module handles user personalization and pattern analysis.
Provides functions for analyzing user behavior and generating personalized guidance.
"""

import logging
from collections import Counter
from .database import get_db
from .user_interactions import get_user_interaction_history

logger = logging.getLogger(__name__)

async def get_enhanced_personalized_context(user_id: str, current_topic: str = None, question_id: str = None, user_name: str = None):
    """
    Get enhanced personalized context using user interaction history.
    Analyzes patterns and generates personalized guidance for interviews.
    """
    try:
        # Get recent interactions (reduced from 15 to 10 for better performance)
        recent_interactions = await get_user_interaction_history(user_id, limit=10)
        
        # Get progress data if question_id provided
        progress_data = None
        if question_id:
            from services.llm.utils import check_question_answered_by_id
            progress_data = await check_question_answered_by_id(user_id, question_id)
        
        # Extract patterns from interactions
        patterns = await extract_interaction_patterns(recent_interactions, current_topic)
        
        # Add progress data if available
        if progress_data and progress_data.get("success"):
            patterns["question_specific_history"] = {
                "previous_answer": progress_data["data"].get("answer", ""),
                "previous_result": progress_data["data"].get("finalResult", None),
                "previous_output": progress_data["data"].get("output", "")
            }
        
        # Generate personalized guidance
        personalized_guidance = generate_enhanced_guidance(patterns, user_name)
        
        return {
            "user_patterns": patterns,
            "personalized_guidance": personalized_guidance
        }
    except Exception as e:
        logger.error(f"Error getting enhanced personalized context: {str(e)}", exc_info=True)
        return {"user_patterns": {}, "personalized_guidance": ""}

async def extract_interaction_patterns(interactions: list, current_topic: str = None):
    """
    Extract patterns from user interactions efficiently.
    Analyzes performance trends, weaknesses, strengths, and usage patterns.
    """
    try:
        patterns = {
            "recent_topics": [],
            "performance_trend": [],
            "common_weaknesses": [],
            "strengths": [],
            "completion_rate": 0,
            "avg_response_length": 0,
            "topic_specific_performance": {"scores": [], "weaknesses": [], "strengths": []},
            "endpoint_usage": {},
            "recent_scores": []
        }
        
        completed_sessions = 0
        total_sessions = 0
        response_lengths = []
        
        # Analyze each interaction (optimized for performance)
        for interaction in interactions[:8]:  # Limit to 8 interactions for better performance
            endpoint = interaction.get("endpoint", "")
            patterns["endpoint_usage"][endpoint] = patterns["endpoint_usage"].get(endpoint, 0) + 1
            
            if endpoint == "mock_interview":
                total_sessions += 1
                session_data = interaction.get("meta", {}).get("session_data", {})
                
                # Track completion
                if session_data.get("status") == "completed":
                    completed_sessions += 1
                
                # Extract topic (limit to avoid excessive processing)
                topic = session_data.get("topic")
                if topic and topic not in patterns["recent_topics"] and len(patterns["recent_topics"]) < 5:
                    patterns["recent_topics"].append(topic)
                
                # Extract feedback insights (limit data for performance)
                feedback = session_data.get("feedback")
                if feedback:
                    if "points_to_address" in feedback:
                        patterns["common_weaknesses"].extend(feedback["points_to_address"][:1])  # Reduced from 2 to 1
                    if "positive_points" in feedback:
                        patterns["strengths"].extend(feedback["positive_points"][:1])  # Reduced from 2 to 1
                    if "score" in feedback:
                        patterns["recent_scores"].append(feedback["score"])
                
                # Track topic-specific performance (only if current topic matches)
                if topic and topic == current_topic:
                    if feedback:
                        if "score" in feedback:
                            patterns["topic_specific_performance"]["scores"].append(feedback["score"])
                        if "points_to_address" in feedback:
                            patterns["topic_specific_performance"]["weaknesses"].extend(feedback["points_to_address"][:1])
                        if "positive_points" in feedback:
                            patterns["topic_specific_performance"]["strengths"].extend(feedback["positive_points"][:1])
            
            elif endpoint == "approach_analysis":
                ai_response = interaction.get("ai_response", {})
                if "score" in ai_response:
                    patterns["recent_scores"].append(ai_response["score"])
                if "areas_for_improvement" in ai_response:
                    patterns["common_weaknesses"].extend(ai_response["areas_for_improvement"][:1])  # Reduced from 2 to 1
                if "strengths" in ai_response:
                    patterns["strengths"].extend(ai_response["strengths"][:1])  # Reduced from 2 to 1
            
            # Calculate response length from input data (limit processing)
            input_data = interaction.get("input", {})
            if "user_answer" in input_data and len(response_lengths) < 5:  # Limit to 5 samples
                response_lengths.append(len(input_data["user_answer"].split()))
            elif "answer" in input_data and len(response_lengths) < 5:  # Limit to 5 samples
                response_lengths.append(len(input_data["answer"].split()))
        
        # Calculate metrics
        if total_sessions > 0:
            patterns["completion_rate"] = completed_sessions / total_sessions
        
        if response_lengths:
            patterns["avg_response_length"] = sum(response_lengths) / len(response_lengths)
        
        # Get most recent scores (last 5)
        patterns["performance_trend"] = patterns["recent_scores"][-5:] if patterns["recent_scores"] else []
        
        # Get most common patterns (top 3)
        patterns["common_weaknesses"] = [item for item, count in Counter(patterns["common_weaknesses"]).most_common(3)]
        patterns["strengths"] = [item for item, count in Counter(patterns["strengths"]).most_common(3)]
        
        # Calculate average score
        if patterns["recent_scores"]:
            patterns["average_score"] = sum(patterns["recent_scores"]) / len(patterns["recent_scores"])
        else:
            patterns["average_score"] = 0
        
        # Add total sessions count
        patterns["total_sessions"] = total_sessions
        
        return patterns
    except Exception as e:
        logger.error(f"Error extracting interaction patterns: {str(e)}", exc_info=True)
        return {}

def generate_enhanced_guidance(patterns: dict, user_name: str = None):
    """
    Generate enhanced personalized guidance based on interaction patterns.
    Creates actionable feedback based on performance analysis.
    """
    try:
        guidance_parts = []
        name_reference = f"{user_name}" if user_name else "You"
        
        # Performance trend analysis
        if patterns.get("performance_trend"):
            recent_scores = patterns["performance_trend"]
            if len(recent_scores) >= 3:
                avg_recent = sum(recent_scores[-3:]) / 3
                if avg_recent > patterns.get("average_score", 0):
                    guidance_parts.append(f"Your recent performance shows improvement, with an average score of {avg_recent:.1f}/10 in your last 3 sessions.")
                elif avg_recent < patterns.get("average_score", 0):
                    guidance_parts.append(f"Your recent performance has been below your average. Focus on consistency and review your approach.")
        
        # Topic-specific guidance
        if patterns.get("topic_specific_performance"):
            topic_perf = patterns["topic_specific_performance"]
            if topic_perf.get("scores"):
                avg_topic_score = sum(topic_perf["scores"]) / len(topic_perf["scores"])
                if avg_topic_score < 5:
                    guidance_parts.append(f"In this topic area, you've averaged {avg_topic_score:.1f}/10. Consider reviewing fundamental concepts.")
                elif avg_topic_score > 7:
                    guidance_parts.append(f"You're performing well in this topic area with an average of {avg_topic_score:.1f}/10. Build on this strength.")
        
        # Response length guidance
        avg_length = patterns.get("avg_response_length", 0)
        if avg_length < 20:
            guidance_parts.append("Your responses tend to be brief. Consider providing more detailed explanations to demonstrate your understanding.")
        elif avg_length > 100:
            guidance_parts.append("Your responses are comprehensive. Consider being more concise while maintaining clarity.")
        
        # Completion rate guidance
        completion_rate = patterns.get("completion_rate", 0)
        if completion_rate < 0.5:
            guidance_parts.append("You often don't complete interview sessions. Try to finish more sessions to build consistency and confidence.")
        
        # Weaknesses and strengths
        if patterns.get("common_weaknesses"):
            weaknesses = ', '.join(patterns['common_weaknesses'][:2])
            guidance_parts.append(f"Areas for improvement: {weaknesses}")
        
        if patterns.get("strengths"):
            strengths = ', '.join(patterns['strengths'][:2])
            guidance_parts.append(f"Your strengths: {strengths}. Continue leveraging these.")
        
        return " ".join(guidance_parts)
    except Exception as e:
        logger.error(f"Error generating enhanced guidance: {str(e)}", exc_info=True)
        return ""

async def analyze_user_patterns(user_id: str):
    """
    Analyze user patterns from previous interactions for personalization.
    Provides comprehensive analysis of user behavior and performance.
    """
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
        patterns["common_weaknesses"] = [item for item, count in Counter(patterns["common_weaknesses"]).most_common(3)]
        patterns["strengths"] = [item for item, count in Counter(patterns["strengths"]).most_common(3)]
        
        # Calculate average score
        if patterns["average_scores"]:
            patterns["average_score"] = sum(patterns["average_scores"]) / len(patterns["average_scores"])
        else:
            patterns["average_score"] = 0
        
        return patterns
    except Exception as e:
        logger.error(f"Error analyzing user patterns: {str(e)}", exc_info=True)
        return {}

async def get_personalized_context(user_id: str, current_topic: str = None, user_name: str = None):
    """
    Get personalized context based on user's previous interactions.
    Provides basic personalization for backward compatibility.
    """
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

        # Summarize user progress and trends (pattern-based only)
        # (No generic advice based on average_score)

        # Highlight recurring weaknesses (pattern-based, not just topic-based)
        if patterns.get("common_weaknesses"):
            weaknesses = ', '.join(patterns['common_weaknesses'][:2])
            if weaknesses:
                guidance_parts.append(f"You often struggle with: {weaknesses}. Targeted practice in these areas could help.")

        # Highlight recurring strengths
        if patterns.get("strengths"):
            strengths = ', '.join(patterns['strengths'][:2])
            if strengths:
                guidance_parts.append(f"Your strengths include: {strengths}. Keep leveraging these in your answers.")

        # Session completion guidance
        scr = patterns.get("session_completion_rate")
        if scr is not None and scr < 0.5:
            guidance_parts.append("Completing more interview sessions would help build consistency and confidence.")

        personalized_context["personalized_guidance"] = " ".join(guidance_parts)
        return personalized_context
    except Exception as e:
        logger.error(f"Error getting personalized context: {str(e)}", exc_info=True)
        return {"user_patterns": {}, "personalized_guidance": ""} 