#!/usr/bin/env python3
"""
Test script to debug the interview flow
"""

import asyncio
import json
from services.interview import get_next_question

async def test_conversation_history():
    """Test the conversation history processing"""
    
    # Simulate the conversation history that would be built
    conversation_history = [
        {"role": "assistant", "content": "demonstrate select"},
        {"role": "assistant", "content": "Can you walk me through your thought process on how you would approach this problem?"},
        {"role": "user", "content": "sjcnkscksckskccs"}
    ]
    
    print("Testing conversation history processing...")
    print(f"Conversation history: {json.dumps(conversation_history, indent=2)}")
    
    try:
        # Test with coding interview type
        next_question = await get_next_question(
            questions=conversation_history,
            is_base_question=False,
            topic="MCA0015",
            interview_type="coding"
        )
        
        print(f"\nGenerated next question: {next_question}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def test_base_question():
    """Test the base question generation"""
    
    print("\nTesting base question generation...")
    
    try:
        base_question = await get_next_question(
            questions=[],
            is_base_question=True,
            topic="MCA0015",
            interview_type="coding"
        )
        
        print(f"Base question: {base_question}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting interview flow test...")
    
    # Run the tests
    asyncio.run(test_base_question())
    asyncio.run(test_conversation_history())
    
    print("\nTest completed.")
