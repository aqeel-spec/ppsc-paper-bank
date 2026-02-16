"""
Agent System for PPSC Paper Bank with Session Management
Uses OpenAI Agents SDK with GitHub Models (OpenAI-compatible endpoint)
Includes paper creation, session memory, and internet search
"""

import os
import asyncio
import httpx
import json
from typing import Optional, List
from datetime import datetime
from dotenv import load_dotenv
import logging

# Import from openai-agents package
import agents as openai_agents
from agents import Agent, Runner, function_tool, SQLiteSession
from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Suppress LiteLLM verbose output completely
import litellm
litellm.suppress_debug_info = True
litellm.set_verbose = False

# Also suppress LiteLLM's logger
litellm_logger = logging.getLogger('LiteLLM')
litellm_logger.setLevel(logging.ERROR)
litellm_logger.propagate = False

# Suppress OpenAI client retry logs
openai_logger = logging.getLogger('openai')
openai_logger.setLevel(logging.ERROR)
openai_logger.propagate = False

# Suppress httpx logs
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.ERROR)
httpx_logger.propagate = False

from .api_key_rotator import get_github_models_config
from .offline_model import OfflineEchoModel

# Load environment variables
load_dotenv()

# Offline mode (for running tests without external LLM quota)
OFFLINE_MODE = os.getenv("PPSC_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Session storage file
SESSION_DB = "agent_sessions.db"

# Initialize GitHub Models configuration
_gh_config: dict[str, str] = get_github_models_config()

github_model: Model

if OFFLINE_MODE:
    logger.info("🧪 Offline mode enabled (PPSC_OFFLINE=1) — external LLM calls disabled")
    github_model = OfflineEchoModel()
else:
    token = _gh_config["api_key"]
    if not token:
        logger.warning("⚠️  GITHUB_TOKEN is empty! Set it in .env to use GitHub Models.")

    logger.info(f"🔑 Using GitHub Models: {_gh_config['model']} @ {_gh_config['base_url']}")

    # Create LiteLLM model pointed at GitHub Models (OpenAI-compatible)
    github_model = LitellmModel(
        model=_gh_config["model"],
        api_key=_gh_config["api_key"],
        base_url=_gh_config["base_url"],
    )


def handle_api_error(error: Exception) -> bool:
    """
    Handle API errors. With a single provider there is no key rotation;
    returns False so callers surface the error immediately.
    """
    error_str = str(error)
    error_type = type(error).__name__
    logger.error(f"❌ API Error ({error_type}): {error_str[:150]}")
    return False


def get_current_model():
    """Get the current LLM model instance."""
    return github_model


# ==================== MCQ Agent Tools ====================

@function_tool
async def get_categories(limit: int = 100) -> str:
    """
    Get all available MCQ categories from the database with pagination.
    
    Args:
        limit: Maximum number of categories to retrieve (default: 100, max: 100)
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        params = {"limit": min(limit, 100), "offset": 0}
        response = await client.get(
            f"{API_BASE_URL}/categories/",
            params=params
        )
        data = response.json()
        
        if not data:
            return "No categories found."
        
        result = f"Available categories ({len(data)} shown):\n"
        for cat in data:
            result += f"- {cat.get('name', 'Unknown')} (slug: `{cat.get('slug', 'N/A')}`, ID: {cat.get('id', 'N/A')})\n"
        return result


@function_tool
async def get_category_mcqs(slug: str, explanation: bool = False, with_mcq: bool = True, limit: int = 5) -> str:
    """
    Get MCQs from a specific category with pagination.
    
    Args:
        slug: The category slug (e.g., 'computer-mcqs')
        explanation: Whether to include explanations
        with_mcq: Whether to include full MCQ details
        limit: Maximum number of MCQs to retrieve (default: 5, max: 20)
    """
    # Limit to reasonable maximum to avoid rate limits
    limit = min(limit, 20)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        params = {
            "explanation": explanation,
            "with_mcq": with_mcq,
            "limit": limit,
            "offset": 0
        }
        response = await client.get(
            f"{API_BASE_URL}/categories/{slug}/with-mcqs",
            params=params
        )
        data = response.json()
        
        if not data or "mcqs" not in data:
            return f"No MCQs found for category '{slug}'."
        
        category_name = data.get("name", slug)
        total_mcqs = data.get("total_mcqs", 0)
        mcqs = data.get("mcqs", [])
        
        result = f"MCQs in category '{category_name}' ({len(mcqs)} shown, {total_mcqs} total):\n\n"
        for i, mcq in enumerate(mcqs, 1):
            result += f"{i}. {mcq.get('question_text', 'No question')}\n"
            result += f"   Answer: {mcq.get('correct_answer', 'N/A')}\n"
            if explanation and mcq.get('explanation'):
                result += f"   Explanation: {mcq.get('explanation')}\n"
            result += "\n"
        
        if total_mcqs > len(mcqs):
            result += f"... and {total_mcqs - len(mcqs)} more MCQs available\n"
        
        return result


@function_tool
async def get_single_mcq(mcq_id: int, explanation: bool = True) -> str:
    """
    Get a single MCQ by ID with full details.
    
    Args:
        mcq_id: The MCQ ID
        explanation: Whether to include explanation
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        params = {"explanation": explanation, "with_mcq": True}
        response = await client.get(
            f"{API_BASE_URL}/mcqs/with-mcqs/{mcq_id}",
            params=params
        )
        data = response.json()
        
        result = f"Question: {data.get('question_text', 'N/A')}\n\n"
        result += "Options:\n"
        for i in range(1, 6):
            opt = data.get(f"option_{i}")
            if opt:
                result += f"  {i}. {opt}\n"
        
        result += f"\nCorrect Answer: {data.get('correct_answer', 'N/A')}\n"
        
        if explanation and data.get('explanation'):
            result += f"\nExplanation: {data.get('explanation')}\n"
        
        return result


# ==================== Paper Agent Tools ====================

@function_tool
async def create_paper(
    title: str,
    difficulty: Optional[str] = None,
    category_slug: Optional[str] = None,
    question_count: int = 20,
    paper_type: str = "practice",
    year: Optional[int] = None
) -> str:
    """
    Create a custom paper/test with MCQs based on complexity, category, and other filters.
    
    Args:
        title: Title for the paper
        difficulty: Filter by difficulty level (easy, medium, hard)
        category_slug: Category slug to pick questions from
        question_count: Number of questions to include (default: 20)
        paper_type: Type of paper (practice, mock, previous)
        year: Year of the paper (optional)
    
    Returns:
        JSON string with paper details including paper_id and selected MCQs
    """
    try:
        # First, get MCQs from category if specified
        mcqs = []
        if category_slug:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                params = {
                    "limit": min(question_count, 100),  # Cap at 100 per request
                    "offset": 0
                }
                response = await client.get(
                    f"{API_BASE_URL}/categories/{category_slug}/with-mcqs",
                    params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    mcqs = data.get("mcqs", [])[:question_count]
                    
                    # Filter by difficulty if specified
                    if difficulty and mcqs:
                        mcqs = [m for m in mcqs if m.get("difficulty") == difficulty][:question_count]
        
        # Create paper in database
        paper_data = {
            "title": title,
            "paper_type": paper_type,
            "difficulty": difficulty,
            "year": year,
            "mcq_links": {"mcq_ids": [mcq["id"] for mcq in mcqs]}
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                f"{API_BASE_URL}/papers/",
                json=paper_data
            )
            
            if response.status_code == 200:
                paper = response.json()
                return json.dumps({
                    "success": True,
                    "paper_id": paper.get("id"),
                    "title": title,
                    "question_count": len(mcqs),
                    "difficulty": difficulty,
                    "mcqs": mcqs[:5],  # Return first 5 for preview
                    "message": f"Paper '{title}' created successfully with {len(mcqs)} questions!"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Failed to create paper: {response.text}"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error creating paper: {str(e)}"
        })


@function_tool
async def get_papers(
    page: int = 1,
    per_page: int = 10
) -> str:
    """
    Get list of all available papers/tests with pagination.
    
    Args:
        page: Page number (default: 1)
        per_page: Number of papers per page (default: 10, max: 100)
    
    Returns:
        JSON string with list of papers and pagination metadata
    """
    try:
        # Match the API's pagination parameters
        params = {
            "page": page,
            "per_page": min(per_page, 100)  # Cap at 100
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"{API_BASE_URL}/papers/",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                papers_dict = data.get("papers", {})
                
                # Convert papers dict to readable list
                papers_list = []
                for key, paper in papers_dict.items():
                    papers_list.append({
                        "id": key,
                        "length": paper.get("length"),
                        "created_at": paper.get("created_at"),
                        "view_url": paper.get("view_url"),
                        "pdf_with_answers": paper.get("pdf_a_url"),
                        "pdf_without_answers": paper.get("pdf_q_url")
                    })
                
                return json.dumps({
                    "success": True,
                    "total_papers": data.get("total_papers", 0),
                    "total_pages": data.get("total_pages", 0),
                    "current_page": data.get("page", 1),
                    "per_page": data.get("per_page", 10),
                    "papers": papers_list
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Failed to fetch papers: {response.text}"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error fetching papers: {str(e)}"
        })


@function_tool
async def get_paper_mcqs(paper_id: int) -> str:
    """
    Get all MCQs from a specific paper.
    
    Args:
        paper_id: ID of the paper
    
    Returns:
        JSON string with paper details and all its MCQs
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"{API_BASE_URL}/papers/{paper_id}/mcqs/"
            )
            
            if response.status_code == 200:
                data = response.json()
                return json.dumps({
                    "success": True,
                    "paper_id": paper_id,
                    "title": data.get("title"),
                    "question_count": len(data.get("mcqs", [])),
                    "mcqs": data.get("mcqs")
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Paper not found or error: {response.text}"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error fetching paper MCQs: {str(e)}"
        })


@function_tool
async def search_internet(query: str, num_results: int = 5) -> str:
    """
    Search the internet for information about topics, MCQ questions, or exam preparation tips.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default: 5)
    
    Returns:
        JSON string with search results
    """
    try:
        # Using DuckDuckGo instant answers API (no API key needed)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                # Get abstract/definition
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", "Definition"),
                        "snippet": data.get("AbstractText"),
                        "url": data.get("AbstractURL", "")
                    })
                
                # Get related topics
                for topic in data.get("RelatedTopics", [])[:num_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "").split(" - ")[0],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", "")
                        })
                
                return json.dumps({
                    "success": True,
                    "query": query,
                    "result_count": len(results),
                    "results": results[:num_results]
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": "Search failed"
                })
    
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Search error: {str(e)}"
        })


# ==================== Scraping Agent Tools ====================

@function_tool
async def start_scraping(
    website: str,
    url: str,
    slug: str,
    scrape_explanations: bool = False
) -> str:
    """
    Start scraping MCQs from a website.
    
    Args:
        website: Website name (testpoint, pakmcqs, or pacegkacademy)
        url: URL to scrape
        slug: Category slug to store MCQs
        scrape_explanations: Whether to scrape explanations
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.post(
            f"{API_BASE_URL}/scrape/start/",
            json={
                "website": website,
                "url": url,
                "slug": slug,
                "scrape_explanations": scrape_explanations
            }
        )
        data = response.json()
        return f"Scraping started: {data.get('message', 'Success')}"


# ==================== Create Agents ====================

paper_agent = Agent(
    name="Paper Creator",
    instructions="""You are an intelligent paper/test creator and manager for PPSC Paper Bank.
    
    Your responsibilities:
    1. Create custom papers based on user requirements (difficulty, topic, question count)
    2. List and manage existing papers
    3. Help users find appropriate papers for practice
    4. Provide information about paper contents
    5. Search the internet for topic information when needed
    
    When creating papers:
    - Ask about difficulty level (easy/medium/hard) if not specified
    - Confirm question count (default: 20)
    - Select appropriate category/topic
    - Use search_internet for topic research if needed
    
    Always be helpful and guide users through the paper creation process.
    """,
    model=github_model,
    tools=[create_paper, get_papers, get_paper_mcqs, search_internet, get_categories]
)

mcq_agent = Agent(
    name="MCQ Assistant",
    instructions="""You are an intelligent MCQ assistant for PPSC Paper Bank.
    
    Your responsibilities:
    1. Help users browse and search through MCQ categories
    2. Retrieve specific MCQs with detailed information
    3. Show MCQs from particular categories
    4. Provide explanations when requested
    
    Always format MCQs clearly with question, options, and answer.
    """,
    model=github_model,
    tools=[get_categories, get_category_mcqs, get_single_mcq]
)

scraping_agent = Agent(
    name="Scraping Agent",
    instructions="""You are a web scraping assistant for PPSC Paper Bank.
    
    Your responsibilities:
    1. Help users add new MCQs from supported websites
    2. Support websites: testpoint, pakmcqs, pacegkacademy
    3. Guide users through the scraping process
    
    Always confirm the website, URL, and category before starting.
    """,
    model=github_model,
    tools=[start_scraping]
)

study_agent = Agent(
    name="Study Assistant",
    instructions="""You are a helpful study assistant for exam preparation.
    
    Your responsibilities:
    1. Help students learn from MCQs
    2. Provide detailed explanations
    3. Create study plans
    4. Offer exam preparation tips
    
    Always be encouraging and educational.
    """,
    model=github_model,
    tools=[get_single_mcq, get_category_mcqs]
)

# Create orchestrator that routes to specialized agents
orchestrator = Agent(
    name="Orchestrator",
    instructions="""You are an intelligent orchestrator for PPSC Paper Bank system.
    
    Route user requests to the appropriate specialized agent:
    - Paper Creator: For creating custom papers/tests, managing papers, searching topics
    - MCQ Assistant: For browsing MCQs, getting questions, exploring categories
    - Scraping Agent: For adding new content from websites (testpoint, pakmcqs, pacegkacademy)
    - Study Agent: For exam preparation, learning assistance, explanations
    
    Always analyze the user's intent and delegate to the most appropriate agent.
    """,
    model=github_model,
    tools=[
        paper_agent.as_tool("paper_creator", "Create and manage custom practice papers/tests"),
        mcq_agent.as_tool("mcq_assistant", "Browse and search MCQ questions and categories"),
        scraping_agent.as_tool("scraping_agent", "Add new content from supported websites"),
        study_agent.as_tool("study_assistant", "Get exam preparation help and explanations")
    ]
)


# ==================== Helper Functions ====================

async def run_agent(
    agent: Agent,
    query: str,
    session_id: Optional[str] = None,
) -> str:
    """
    Run a specific agent with a query and optional session for conversation memory.

    Args:
        agent: The agent to run
        query: User query/message
        session_id: Optional session ID for conversation history (e.g., 'user_123')

    Returns:
        Agent's response
    """
    session = None
    if session_id:
        session = SQLiteSession(session_id, SESSION_DB)

    logger.info(f"Running agent with query: {query[:100]}...")

    try:
        result = await Runner.run(agent, query, session=session)
        logger.info("✓ Agent request completed successfully")
        return result.final_output
    except Exception as e:
        handle_api_error(e)
        raise


async def run_orchestrator(
    query: str,
    session_id: Optional[str] = None,
) -> str:
    """
    Run the orchestrator with a query and optional session for conversation memory.

    Args:
        query: User query/message
        session_id: Optional session ID for conversation history (e.g., 'user_123')

    Returns:
        Orchestrator's response
    """
    session = None
    if session_id:
        session = SQLiteSession(session_id, SESSION_DB)

    logger.info(f"Running orchestrator with query: {query[:100]}...")

    try:
        result = await Runner.run(orchestrator, query, session=session)
        logger.info("✓ Orchestrator request completed successfully")
        return result.final_output
    except Exception as e:
        handle_api_error(e)
        raise


async def get_session_history(session_id: str, limit: Optional[int] = None) -> List:
    """
    Get conversation history for a session.
    
    Args:
        session_id: Session ID to retrieve history for
        limit: Maximum number of items to return (optional)
    
    Returns:
        List of conversation items
    """
    session = SQLiteSession(session_id, SESSION_DB)
    items = await session.get_items(limit=limit)
    return items


async def clear_session(session_id: str) -> None:
    """
    Clear all conversation history for a session.
    
    Args:
        session_id: Session ID to clear
    """
    session = SQLiteSession(session_id, SESSION_DB)
    await session.clear_session()


# ==================== Test Function ====================

async def test_agent():
    """Test the agent system with session memory."""
    print("Testing Agent System with Session Memory")
    print("=" * 60)
    
    session_id = "test_user_123"
    
    # Test 1: Create a paper
    print("\n1. Creating a paper...")
    print("-" * 60)
    response = await run_orchestrator(
        "Create a practice paper with 10 medium difficulty computer questions",
        session_id=session_id
    )
    print(response)
    
    # Test 2: Follow-up question (testing session memory)
    print("\n2. Follow-up question (testing session memory)...")
    print("-" * 60)
    response = await run_orchestrator(
        "Show me the questions in that paper",
        session_id=session_id
    )
    print(response)
    
    # Test 3: Internet search
    print("\n3. Testing internet search...")
    print("-" * 60)
    response = await run_agent(
        paper_agent,
        "Search for information about PPSC exam preparation tips",
        session_id=session_id
    )
    print(response)
    
    # Show session history
    print("\n4. Session history...")
    print("-" * 60)
    history = await get_session_history(session_id, limit=5)
    print(f"Total items in session: {len(history)}")
    
    print("\n" + "=" * 60)
    print("Test completed!")


if __name__ == "__main__":
    asyncio.run(test_agent())
