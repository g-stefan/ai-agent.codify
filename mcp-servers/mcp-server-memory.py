# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import uuid
import argparse
import urllib.request
from typing import List, Dict, Any
from datetime import datetime

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

try:
    import mariadb
except ImportError:
    print(
        "Warning: The 'mariadb' module is not installed. Please install it using: pip install mariadb",
        file=sys.stderr,
    )

# --- Pre-parse --env-base ---
# We use a separate parser that ignores unknown args to grab the env-base prefix early,
# because we need it to resolve our module-level configuration variables below.
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base


def get_env_var(name: str, default: Any = None) -> Any:
    """Get an environment variable, optionally applying the env-base prefix."""
    if ENV_PREFIX:
        # Ensure there is exactly one underscore between prefix and name
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)


# Initialize the MCP Server
mcp = FastMCP("Memory", stateless_http=True, json_response=False)

# Configuration via Environment Variables (with fallbacks and prefix support)
PORT = int(get_env_var("PORT", 48101))
DB_HOST = get_env_var("DB_HOST", "127.0.0.1")
DB_PORT = int(get_env_var("DB_PORT", 3306))
DB_USER = get_env_var("DB_USER", "root")
DB_PASS = get_env_var("DB_PASS", "")
DB_NAME = get_env_var("DB_NAME", "memory_db")
DB_TABLE = get_env_var("DB_TABLE", "embeddings")
DB_SEARCH_LIMIT = int(get_env_var("DB_SEARCH_LIMIT", 8))

LLAMA_EMBED_URL = get_env_var("LLAMA_EMBED_URL", "http://127.0.0.1:8080/embeddings")
LLAMA_RERANK_URL = get_env_var("LLAMA_RERANK_URL", "http://127.0.0.1:8080/v1/rerank")

# Environment Variable to toggle reranking (defaults to True for backward compatibility)
ENABLE_RERANKING = get_env_var("ENABLE_RERANKING", "true").lower() in (
    "true",
    "1",
    "yes",
    "on",
)

MEMORY_DIR = get_env_var("MEMORY_DIR", "Memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

# --- Helper Functions ---


def get_embedding(text: str) -> List[float]:
    """Fetch embedding vector for a given text from the Llama Server."""
    payload = {"content": [{"prompt_string": text, "multimodal_data": []}]}
    req = urllib.request.Request(
        LLAMA_EMBED_URL, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))

        # Match standard openai or direct list response (like in agent-cli-embeddings.py)
        if isinstance(result, dict) and "data" in result:
            return result["data"][0]["embedding"]
        elif isinstance(result, list):
            sorted_data = sorted(result, key=lambda x: x.get("index", 0))
            emb = sorted_data[0].get("embedding", [])
            # In case of token-level embeddings, grab the last vector
            if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                return emb[-1]
            return emb

    raise ValueError("Unrecognized embedding response format from server.")


def get_db_connection():
    """Helper to get MariaDB connection, omitting password if empty."""
    kwargs = {"host": DB_HOST, "port": DB_PORT, "user": DB_USER, "database": DB_NAME}
    if DB_PASS:
        kwargs["password"] = DB_PASS
    return mariadb.connect(**kwargs)


def save_embedding_to_db(doc_name: str, embedding: List[float]):
    """Insert the document filename, its embedding, and creation date into MariaDB."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        emb_str = json.dumps(embedding)
        # Using NOW() to automatically stamp the memory creation time based on the DB server
        query = f"INSERT INTO `{DB_TABLE}` (created_at, document, embedding) VALUES (NOW(), ?, VEC_FromText(?))"
        cur.execute(query, (doc_name, emb_str))
        conn.commit()
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def search_db(
    embedding: List[float], limit: int = DB_SEARCH_LIMIT
) -> List[Dict[str, Any]]:
    """Find top matching document filenames and creation dates using Vector Cosine Distance."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        emb_str = json.dumps(embedding)
        # Modified to select both document and created_at fields
        query = f"""
            SELECT document, created_at
            FROM `{DB_TABLE}`
            ORDER BY VEC_DISTANCE_COSINE(embedding, VEC_FromText(?))
            LIMIT ?
        """
        cur.execute(query, (emb_str, limit))
        results = [{"document": row[0], "created_at": row[1]} for row in cur]
        return results
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def rerank(query: str, documents: List[str], memory_search_limit: int = 4) -> List[str]:
    """Rerank a list of documents against a query using the Llama Server."""
    if not documents:
        return []
    if len(documents) <= 1:
        return documents

    payload = {"query": query, "documents": documents}
    req = urllib.request.Request(
        LLAMA_RERANK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as response:
        response_data = json.loads(response.read().decode("utf-8"))

    # Extract highest scoring document indices
    if isinstance(response_data, list):
        scored = sorted(enumerate(response_data), key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, score in scored[:memory_search_limit]]
    elif isinstance(response_data, dict) and "results" in response_data:
        results = response_data["results"]
        top_indices = [res.get("index", 0) for res in results[:memory_search_limit]]
    elif isinstance(response_data, dict) and "scores" in response_data:
        scores = response_data["scores"]
        scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, score in scored[:memory_search_limit]]
    else:
        top_indices = [0]

    return [documents[i] for i in top_indices if i < len(documents)]


# --- MCP Tools ---


@mcp.tool()
async def remember(info: str) -> str:
    """Remember, save a information a text or fact to memory."""
    try:
        doc_id = str(uuid.uuid4())
        filename = f"{doc_id}.txt"
        filepath = os.path.join(MEMORY_DIR, filename)

        # 1. Save content to Workspace Folder
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(info)

        # 2. Fetch Embeddings
        emb = get_embedding(info)

        # 3. Save to MariaDB
        save_embedding_to_db(filename, emb)

        return f"Memory successfully saved (ID: {doc_id})."
    except Exception as e:
        return f"Error saving memory: {str(e)}"


@mcp.tool()
async def remember_response(question: str, response: str) -> str:
    """Remember response, save a question and its corresponding response to memory."""
    text = f"Q: {question}\nA: {response}"
    return await remember(text)


@mcp.tool()
async def recall(question: str, memories_limit: int = 4) -> str:
    """
    Recall information from memory based on a text or query .
    Use the 'memories_limit' parameter to specify the maximum number of relevant memories to return (default is 4).
    """
    try:
        # 1. Generate query embedding
        emb = get_embedding(question)

        # 2. Vector Search DB for top matches
        # If reranking is enabled, fetch more candidates so reranking has options
        search_limit = (
            max(DB_SEARCH_LIMIT, memories_limit * 2)
            if ENABLE_RERANKING
            else memories_limit
        )
        db_matches = search_db(emb, limit=search_limit)

        if not db_matches:
            return "No relevant memories found in the database."

        # 3. Read matched documents from filesystem and append creation date
        documents = []
        for match in db_matches:
            fname = match["document"]
            created_at = match["created_at"]
            filepath = os.path.join(MEMORY_DIR, fname)

            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                    # Format the content to include the creation date for the LLM context
                    date_str = "Unknown Date"
                    if created_at:
                        if hasattr(created_at, "strftime"):
                            date_str = created_at.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            date_str = str(created_at)

                    doc_with_date = f"Creation Date: {date_str}\n{content}"
                    documents.append(doc_with_date)

        if not documents:
            return "Memory documents found in DB but missing from filesystem."

        # 4. Conditionally Rerank the gathered context
        if ENABLE_RERANKING:
            best_matches = rerank(question, documents, memories_limit)
        else:
            # If skipping rerank, just take the top vector matches up to the memories_limit
            best_matches = documents[:memories_limit]

        # 5. Format the results
        formatted_results = "\n\n---\n\n".join(
            [f"Memory {i+1}:\n{doc}" for i, doc in enumerate(best_matches)]
        )
        return f"Top {len(best_matches)} relevant memories:\n\n{formatted_results}"

    except Exception as e:
        return f"Error recalling memory: {str(e)}"


# --- Authentication Middleware ---


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce API key authentication on HTTP endpoints."""

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        # Allow CORS preflight requests to pass through without authentication
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check both X-API-Key and Authorization Bearer token headers
        api_key_header = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")

        provided_key = None
        if api_key_header:
            provided_key = api_key_header
        elif auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header.split(" ", 1)[1]

        if provided_key != self.api_key:
            return JSONResponse(
                {"detail": "Unauthorized - Invalid or missing API Key"}, status_code=401
            )

        return await call_next(request)


if __name__ == "__main__":
    # Main argument parser includes all arguments, including the --env-base we already processed
    parser = argparse.ArgumentParser(description="Memory MCP Server")
    parser.add_argument(
        "--stdio", action="store_true", help="Run the MCP server in standard stdio mode"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run the MCP server in HTTP/SSE mode (default)",
    )
    parser.add_argument(
        "--api-key", type=str, help="Enforce API key authentication in HTTP mode"
    )
    parser.add_argument(
        "--env-base",
        type=str,
        default="",
        help="Prefix for environment variables (e.g. 'PREFIX' checks for 'PREFIX_VARIABLE')",
    )
    args = parser.parse_args()

    # Note: When using stdio mode, standard out must be clean for JSON-RPC messages.
    # Therefore, all initialization logs are routed to sys.stderr.
    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(
            f"Using environment variable prefix: '{actual_prefix}' (e.g., expecting {actual_prefix}PORT)",
            file=sys.stderr,
        )

    print(
        f"Reranking is currently {'ENABLED' if ENABLE_RERANKING else 'DISABLED'}",
        file=sys.stderr,
    )

    if args.stdio:
        print("Starting Memory MCP Server in STDIO mode...", file=sys.stderr)
        mcp.run()
    else:
        # Default mode (HTTP)
        print(
            f"Starting Memory MCP Server in HTTP mode on port {PORT}...",
            file=sys.stderr,
        )

        starlette_app = mcp.streamable_http_app()

        # 1. Add API Key Middleware if the command line argument is provided
        if args.api_key:
            print("API Key authentication is ENABLED.", file=sys.stderr)
            starlette_app.add_middleware(APIKeyMiddleware, api_key=args.api_key)

        # 2. Add CORS Middleware (Added last so it wraps the app first, handling OPTIONS directly)
        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)
