"""
MCP Server for PPSC Paper Bank
Exposes FastAPI routes as MCP tools for agent consumption
"""

import asyncio
import json
from typing import Any, Optional
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Initialize MCP server
app = Server("ppsc-paper-bank-mcp")

# Base URL for FastAPI backend
API_BASE_URL = "http://localhost:8000"


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools"""
    return [
        Tool(
            name="get_categories",
            description="Get all available MCQ categories from the database",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_category_with_mcqs",
            description="Get a specific category with all its MCQs",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Category slug (e.g., 'test-explanations-demo')"
                    },
                    "explanation": {
                        "type": "boolean",
                        "description": "Include explanations in response",
                        "default": False
                    },
                    "with_mcq": {
                        "type": "boolean",
                        "description": "Include full MCQ details",
                        "default": True
                    }
                },
                "required": ["slug"]
            }
        ),
        Tool(
            name="get_single_mcq",
            description="Get a single MCQ by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "mcq_id": {
                        "type": "integer",
                        "description": "MCQ ID"
                    },
                    "explanation": {
                        "type": "boolean",
                        "description": "Include explanation",
                        "default": False
                    },
                    "with_mcq": {
                        "type": "boolean",
                        "description": "Include full MCQ details",
                        "default": True
                    }
                },
                "required": ["mcq_id"]
            }
        ),
        Tool(
            name="get_category_single_mcq",
            description="Get a single MCQ within a specific category context",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Category slug"
                    },
                    "mcq_id": {
                        "type": "integer",
                        "description": "MCQ ID"
                    },
                    "explanation": {
                        "type": "boolean",
                        "description": "Include explanation",
                        "default": False
                    },
                    "with_mcq": {
                        "type": "boolean",
                        "description": "Include full MCQ details",
                        "default": True
                    }
                },
                "required": ["slug", "mcq_id"]
            }
        ),
        Tool(
            name="start_scraping",
            description="Start scraping MCQs from a website",
            inputSchema={
                "type": "object",
                "properties": {
                    "website": {
                        "type": "string",
                        "enum": ["testpoint", "pakmcqs", "pacegkacademy"],
                        "description": "Website to scrape from"
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to scrape"
                    },
                    "slug": {
                        "type": "string",
                        "description": "Category slug to store MCQs under"
                    },
                    "scrape_explanations": {
                        "type": "boolean",
                        "description": "Whether to scrape explanations",
                        "default": False
                    }
                },
                "required": ["website", "url", "slug"]
            }
        ),
        Tool(
            name="search_mcqs",
            description="Search for MCQs by question text or category",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "category_slug": {
                        "type": "string",
                        "description": "Filter by category slug (optional)"
                    }
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute MCP tool by calling FastAPI backend"""

    # FastAPI commonly redirects when a trailing slash is missing; follow redirects so
    # MCP tools work regardless of the exact route style.
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        try:
            if name == "get_categories":
                response = await client.get(f"{API_BASE_URL}/categories/")
                result = response.json()
                
            elif name == "get_category_with_mcqs":
                slug = arguments["slug"]
                explanation = arguments.get("explanation", False)
                with_mcq = arguments.get("with_mcq", True)
                params = {"explanation": explanation, "with_mcq": with_mcq}
                response = await client.get(
                    f"{API_BASE_URL}/categories/{slug}/with-mcqs",
                    params=params
                )
                result = response.json()
                
            elif name == "get_single_mcq":
                mcq_id = arguments["mcq_id"]
                explanation = arguments.get("explanation", False)
                with_mcq = arguments.get("with_mcq", True)
                params = {"explanation": explanation, "with_mcq": with_mcq}
                response = await client.get(
                    f"{API_BASE_URL}/mcqs/with-mcqs/{mcq_id}",
                    params=params
                )
                result = response.json()
                
            elif name == "get_category_single_mcq":
                slug = arguments["slug"]
                mcq_id = arguments["mcq_id"]
                explanation = arguments.get("explanation", False)
                with_mcq = arguments.get("with_mcq", True)
                params = {"explanation": explanation, "with_mcq": with_mcq}
                response = await client.get(
                    f"{API_BASE_URL}/categories/{slug}/with-mcqs/{mcq_id}",
                    params=params
                )
                result = response.json()
                
            elif name == "start_scraping":
                website = arguments["website"]
                payload = {
                    "url": arguments["url"],
                    "slug": arguments["slug"],
                    "scrape_explanations": arguments.get("scrape_explanations", False)
                }
                response = await client.post(
                    f"{API_BASE_URL}/scrape/{website}",
                    json=payload
                )
                result = response.json()
                
            elif name == "search_mcqs":
                # This would need a search endpoint in FastAPI
                # For now, return a placeholder
                result = {"message": "Search endpoint not yet implemented"}
                
            else:
                result = {"error": f"Unknown tool: {name}"}
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, indent=2)
            )]


async def main():
    """Run MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
