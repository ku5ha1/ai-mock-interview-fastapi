# Core database functions
from .database import get_db, create_indexes, check_collections, validate_user_id

# User interaction functions
from .user_interactions import (
    save_user_ai_interaction, 
    fetch_interactions_for_session, 
    fetch_user_history,
    get_user_interaction_history,
    fetch_user_session_summaries,
    get_user_name_from_history
)

# Interview session functions
from .interview_sessions import (
    create_interview_session,
    get_interview_session,
    update_interview_session_answer,
    add_follow_up_question,
    transition_to_coding_phase,
    save_interview_feedback,
    get_user_interview_sessions,
    reconstruct_session_state
)

# Personalization functions
from .personalization import (
    get_personalized_context,
    get_enhanced_personalized_context,
    extract_interaction_patterns,
    generate_enhanced_guidance,
    analyze_user_patterns
)

# Question bank functions
from .question_bank import (
    fetch_base_question,
    get_available_topics,
    get_user_name_from_id
)

# Export all functions for backward compatibility
__all__ = [
    # Core database
    "get_db",
    "create_indexes", 
    "check_collections",
    "validate_user_id",
    
    # User interactions
    "save_user_ai_interaction",
    "fetch_interactions_for_session",
    "fetch_user_history", 
    "get_user_interaction_history",
    "fetch_user_session_summaries",
    "get_user_name_from_history",
    
    # Interview sessions
    "create_interview_session",
    "get_interview_session",
    "update_interview_session_answer",
    "add_follow_up_question",
    "transition_to_coding_phase",
    "save_interview_feedback",
    "get_user_interview_sessions",
    "reconstruct_session_state",
    
    # Personalization
    "get_personalized_context",
    "get_enhanced_personalized_context",
    "extract_interaction_patterns",
    "generate_enhanced_guidance",
    "analyze_user_patterns",
    
    # Question bank
    "fetch_base_question",
    "get_available_topics",
    "get_user_name_from_id"
] 