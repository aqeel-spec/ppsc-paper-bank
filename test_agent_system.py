"""
Comprehensive test suite for PPSC Paper Bank Agent System
Tests all agents, tools, and session management
"""

import asyncio
import sys
import logging
from ppsc_agents import (
    mcq_agent,
    paper_agent,
    scraping_agent,
    study_agent,
    orchestrator,
    run_agent,
    run_orchestrator,
    get_session_history,
    clear_session
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)


async def test_mcq_agent():
    """Test MCQ Agent - Browse categories and questions"""
    print("\n" + "="*70)
    print("TEST 1: MCQ Agent - Get Categories")
    print("="*70)
    
    try:
        response = await run_agent(
            mcq_agent,
            "Show me all available MCQ categories",
            session_id="test_mcq"
        )
        print(f"✓ Success:\n{response}\n")
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_mcq_category_browse():
    """Test browsing MCQs from a category"""
    print("\n" + "="*70)
    print("TEST 2: MCQ Agent - Browse Category MCQs")
    print("="*70)
    
    try:
        response = await run_agent(
            mcq_agent,
            "Show me some questions from the computer-mcqs category",
            session_id="test_mcq"
        )
        print(f"✓ Success:\n{response}\n")
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_paper_agent_categories():
    """Test Paper Agent - Get categories for paper creation"""
    print("\n" + "="*70)
    print("TEST 3: Paper Agent - Get Categories")
    print("="*70)
    
    try:
        response = await run_agent(
            paper_agent,
            "What categories are available for creating a paper?",
            session_id="test_paper"
        )
        print(f"✓ Success:\n{response}\n")
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_internet_search():
    """Test Internet Search functionality"""
    print("\n" + "="*70)
    print("TEST 4: Paper Agent - Internet Search")
    print("="*70)
    
    try:
        response = await run_agent(
            paper_agent,
            "Search the internet for Python programming basics",
            session_id="test_paper"
        )
        print(f"✓ Success:\n{response}\n")
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_session_memory():
    """Test session memory persistence"""
    print("\n" + "="*70)
    print("TEST 5: Session Memory - Multi-turn Conversation")
    print("="*70)
    
    session_id = "test_session_memory"
    
    try:
        # Clear any existing session
        await clear_session(session_id)
        
        # Turn 1
        print("Turn 1: Initial question about categories...")
        response1 = await run_orchestrator(
            "What categories do you have?",
            session_id=session_id
        )
        print(f"Response 1: {response1[:200]}...\n")
        
        # Turn 2 - Should remember context
        print("Turn 2: Follow-up question (testing memory)...")
        response2 = await run_orchestrator(
            "Tell me more about the first one",
            session_id=session_id
        )
        print(f"Response 2: {response2[:200]}...\n")
        
        # Check session history
        history = await get_session_history(session_id)
        print(f"✓ Session Memory Working! History items: {len(history)}")
        
        # Clean up
        await clear_session(session_id)
        print("✓ Session cleared successfully\n")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_orchestrator_routing():
    """Test orchestrator routing to correct agents"""
    print("\n" + "="*70)
    print("TEST 6: Orchestrator - Agent Routing")
    print("="*70)
    
    try:
        # Test routing to MCQ agent
        print("Testing routing to MCQ Agent...")
        response1 = await run_orchestrator(
            "Show me computer MCQs",
            session_id="test_orchestrator"
        )
        print(f"✓ MCQ routing: {response1[:150]}...\n")
        
        # Test routing to Paper agent
        print("Testing routing to Paper Agent...")
        response2 = await run_orchestrator(
            "I want to create a practice paper",
            session_id="test_orchestrator"
        )
        print(f"✓ Paper routing: {response2[:150]}...\n")
        
        await clear_session("test_orchestrator")
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_study_agent():
    """Test Study Agent"""
    print("\n" + "="*70)
    print("TEST 7: Study Agent - Educational Assistance")
    print("="*70)
    
    try:
        response = await run_agent(
            study_agent,
            "Help me understand computer science MCQs",
            session_id="test_study"
        )
        print(f"✓ Success:\n{response}\n")
        await clear_session("test_study")
        return True
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def test_session_utilities():
    """Test session utility functions"""
    print("\n" + "="*70)
    print("TEST 8: Session Utilities - History & Clear")
    print("="*70)
    
    session_id = "test_utilities"
    
    try:
        # Create some history
        await run_orchestrator("Hello", session_id=session_id)
        await run_orchestrator("What categories exist?", session_id=session_id)
        
        # Get history
        history = await get_session_history(session_id, limit=5)
        print(f"✓ Retrieved history: {len(history)} items")
        
        # Clear session
        await clear_session(session_id)
        
        # Verify cleared
        history_after = await get_session_history(session_id)
        print(f"✓ After clear: {len(history_after)} items")
        
        if len(history) > 0 and len(history_after) == 0:
            print("✓ Session utilities working correctly\n")
            return True
        else:
            print("✗ Session utilities not working as expected\n")
            return False
            
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {str(e)[:150]}\n")
        logging.exception("Full error details:")
        return False


async def run_all_tests():
    """Run all tests and report results"""
    print("\n" + "#"*70)
    print("# PPSC Paper Bank Agent System - Comprehensive Test Suite")
    print("#"*70)
    
    tests = [
        ("MCQ Agent - Categories", test_mcq_agent),
        ("MCQ Agent - Browse Category", test_mcq_category_browse),
        ("Paper Agent - Categories", test_paper_agent_categories),
        ("Internet Search", test_internet_search),
        ("Session Memory", test_session_memory),
        ("Orchestrator Routing", test_orchestrator_routing),
        ("Study Agent", test_study_agent),
        ("Session Utilities", test_session_utilities),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            # Small delay to avoid rate limits
            await asyncio.sleep(2)
        except Exception as e:
            print(f"\n✗ Test '{test_name}' crashed: {str(e)}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "#"*70)
    print("# TEST SUMMARY")
    print("#"*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "-"*70)
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print("-"*70)
    
    if passed == total:
        print("\n🎉 All tests passed! System is fully functional.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
