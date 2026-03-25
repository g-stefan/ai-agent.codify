# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import uuid
import base64
import shutil
import argparse
import urllib.request
from typing import List, Dict, Any
from datetime import datetime

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ContentBlock, TextContent, ImageContent

try:
    import mariadb
except ImportError:
    print(
        "Warning: The 'mariadb' module is not installed. Please install it using: pip install mariadb",
        file=sys.stderr,
    )

# --- Pre-parse --env-base and --read-only ---
# We use a separate parser that ignores unknown args to grab the env-base prefix early,
# because we need it to resolve our module-level configuration variables below.
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--read-only", action="store_true")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
READ_ONLY = pre_args.read_only


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

MEMORY_DIR = get_env_var("MEMORY_DIR", "Memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

WORKSPACE_DIR = get_env_var("WORKSPACE_DIR", "Workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# --- Helper Functions ---

DB_TYPE_UNKNOWN = 0
DB_TYPE_TEXT = 1
DB_TYPE_IMAGE = 2


def read_file_content_and_type(
    filepath: str, binary: bool = False
) -> tuple[str, bool, str]:
    """Helper to read file content and determine if it should be treated as an image."""
    ext = os.path.splitext(filepath)[1].lower()
    is_image = ext in [".png", ".jpeg", ".jpg"]

    if is_image:
        imageFormat = "jpeg" if ext in [".jpeg", ".jpg"] else "png"
        if binary:
            with open(filepath, "rb") as f:
                data = f.read()
                return data, True, imageFormat

        with open(filepath, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            return b64_data, True, imageFormat
    else:
        # Treat other files as text
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), False, ""


def get_embedding(text_or_image_url: str, is_image: bool = False) -> List[float]:
    """Fetch embedding vector for a given text or image from the Llama Server."""
    if is_image:
        # Structure for multimodal data containing an image
        payload = {
            "content": [
                {"prompt_string": "<__media__>", "multimodal_data": [text_or_image_url]}
            ]
        }
    else:
        # Standard text structure
        payload = {
            "content": [{"prompt_string": text_or_image_url, "multimodal_data": []}]
        }

    req = urllib.request.Request(
        LLAMA_EMBED_URL, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))

        # Match standard openai or direct list response
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


def save_embedding_to_db(doc_name: str, embedding: List[float], is_image: bool):
    """Insert the document filename, its embedding, and creation date into MariaDB."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        emb_str = json.dumps(embedding)
        # Using NOW() to automatically stamp the memory creation time based on the DB server
        recordType = DB_TYPE_TEXT
        if is_image:
            recordType = DB_TYPE_IMAGE
        query = f"INSERT INTO `{DB_TABLE}` (created_at, document, type, embedding) VALUES (NOW(), ?, ?, VEC_FromText(?))"
        cur.execute(query, (doc_name, recordType, emb_str))
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
        # Only higher similarity (e.g., < 0.1 is roughly a 90% match), 
        query = f"""
            SELECT document, created_at, VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) as distance
            FROM `{DB_TABLE}`            
            ORDER BY distance ASC
            LIMIT ?
        """
        cur.execute(query, (emb_str, limit))
        # Filter similarity (e.g., < 0.6 is roughly a 40% match), 
        results = []        
        for row in cur:            
            if row[2] < 0.6:
                results.append({"document": row[0], "created_at": row[1]})
        return results
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def recall_by_embedding(emb: List[float], memories_limit: int = 3) -> List[Any]:
    # 1. Vector Search DB for top matches
    db_matches = search_db(emb, limit=memories_limit)

    if not db_matches:
        return []

    # 2. Read matched documents
    documents = []
    for match in db_matches:
        fname = match["document"]
        filepath = os.path.join(MEMORY_DIR, fname)

        if os.path.exists(filepath):
            ext = os.path.splitext(filepath)[1].lower()
            is_image = ext in [".png", ".jpeg", ".jpg"]
            if is_image:
                content, is_image, imageFormat = read_file_content_and_type(
                    filepath, True
                )
                b64_data = base64.b64encode(content).decode("utf-8")
                documents.append(
                    ImageContent(
                        type="image",
                        data=b64_data,
                        mimeType=f"image/{imageFormat.lower()}",
                    )
                )
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                    documents.append(TextContent(type="text", text=content))

    return documents


# --- MCP Tools ---

# Only register write functionality if not in read-only mode
if not READ_ONLY:

    @mcp.tool()
    async def remember(info: str) -> str:
        """Remember, save a information or text or fact to memory."""
        try:
            doc_id = str(uuid.uuid4())
            filename = f"{doc_id}.txt"
            filepath = os.path.join(MEMORY_DIR, filename)

            # 1. Save content to Workspace Folder (Memory Directory)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(info)

            # 2. Fetch Embeddings
            emb = get_embedding(info)

            # 3. Save to MariaDB
            save_embedding_to_db(filename, emb, False)

            return f"Memory successfully saved (ID: {doc_id})."
        except Exception as e:
            return f"Error saving memory: {str(e)}"

    @mcp.tool()
    async def remember_file(filename: str) -> str:
        """Remember, save an existing file (text or image) from the workspace folder to memory."""
        try:
            original_filepath = os.path.join(WORKSPACE_DIR, filename)
            if not os.path.exists(original_filepath):
                return f"Error: File '{filename}' not found in workspace ({WORKSPACE_DIR})."

            # Generate new GUID-based filename
            doc_id = str(uuid.uuid4())
            _, ext = os.path.splitext(filename)
            new_filename = f"{doc_id}{ext}"
            new_filepath = os.path.join(MEMORY_DIR, new_filename)

            # Read content and fetch embeddings
            content, is_image, imageFormat = read_file_content_and_type(
                original_filepath
            )
            emb = get_embedding(content, is_image=is_image)

            # Copy the file to the memory directory with the new name
            shutil.copy2(original_filepath, new_filepath)

            # Save to MariaDB with the new filename
            save_embedding_to_db(new_filename, emb, is_image)

            return (
                f"File '{filename}' successfully saved to memory as '{new_filename}'."
            )
        except Exception as e:
            return f"Error saving file to memory: {str(e)}"


@mcp.tool()
async def recall(text_or_image_description: str, memories_limit: int = 3) -> List[Any]:
    """
    Recall information from memory based on a text or a image description.
    Use the 'memories_limit' parameter to specify the maximum number of relevant memories to return (default is 3).
    If the user want to search using an image, use this with the image description
    """
    try:
        emb = get_embedding(text_or_image_description)
        documents = recall_by_embedding(emb, memories_limit)
        if not documents:
            return [
                TextContent(
                    type="text",
                    text="No memory found",
                )
            ]

        return documents[:memories_limit]
    except Exception as e:
        return [TextContent(type="text", text=f"Error recalling memory: {str(e)}")]

@mcp.tool()
async def recall_by_file(filename: str, memories_limit: int = 3) -> List[Any]:
    """
    Recall files from memory based on a text or image file contents located in the workspace folder.
    Use the 'memories_limit' parameter to specify the maximum number of relevant memories to return (default is 3).
    """
    try:
        filepath = os.path.join(WORKSPACE_DIR, filename)
        if not os.path.exists(filepath):
            return [f"Error: File '{filename}' not found in workspace."]

        content, is_image, imageFormat = read_file_content_and_type(filepath)

        # Get embedding for the file
        emb = get_embedding(content, is_image=is_image)

        documents = recall_by_embedding(emb, memories_limit)
        if not documents:
            return [
                TextContent(
                    type="text",
                    text="No memory found",
                )
            ]
        return documents[:memories_limit]
    except Exception as e:
        return [f"Error recalling by file: {str(e)}"]


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
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable write functionality (only recall functions will be active)",
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

    if READ_ONLY:
        print(
            "Server is running in READ-ONLY mode (write tools disabled).",
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