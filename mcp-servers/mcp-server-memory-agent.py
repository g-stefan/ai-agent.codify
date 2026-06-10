# MCP Memory (Lightweight Knowledge Graph) with Agent support
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import re
import os
import sys
import fnmatch
import uvicorn
import argparse
import itertools
import base64
import json
import mimetypes
import shlex
import threading
import urllib.request
import ssl
from urllib.error import URLError, HTTPError
from typing import Optional, Dict, Any, List, Tuple
from contextlib import AsyncExitStack
from pathlib import Path
import asyncio

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ContentBlock, TextContent, ImageContent

import mcp
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    streamablehttp_client = None

# --- Pre-parse --env-base ---
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--tool-prefix", type=str, default="memory_")
pre_parser.add_argument("--mcp-name", type=str, default="MemoryAgent")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
TOOL_PREFIX = pre_args.tool_prefix
MCP_NAME = pre_args.mcp_name

def get_env_var(name: str, default: Any = None) -> Any:
    """Get an environment variable, optionally applying the env-base prefix."""
    if ENV_PREFIX:
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)

# Configuration for the Agent
PORT = int(get_env_var("PORT", "48105"))

WORKSPACE_DIR = get_env_var("WORKSPACE_DIR", "Workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

LLM_URL = get_env_var("URL", "http://127.0.0.1:8080/v1/chat/completions")
LLM_API_KEY = get_env_var("API_KEY", None)
LLM_MODEL = get_env_var("MODEL", "default")
LLM_SYSTEM_PROMPT = get_env_var("SYSTEM_PROMPT", """
# System Prompt: Memory Management Protocol

## Role & Purpose
You are an AI assistant equipped with advanced long-term memory and knowledge graph capabilities. Your primary function is to store, organize, retrieve, and maintain persistent knowledge across interactions. You must use the provided memory tools efficiently to build a reliable, structured, and temporally aware information base for yourself and your users.

## Core Principles
1. **Relevance & Precision**: Only store high-value, accurate facts. Avoid redundancy and noise.
2. **Temporal Awareness**: Always anchor memories with `valid_from`/`valid_until` when context is time-sensitive. Use `memory_get_current_datetime` to verify "now".
3. **Hierarchical Organization**: Categorize memories logically (e.g., `Projects/AI`, `Knowledge/History`). Verify categories exist before linking.
4. **Knowledge Graph Integrity**: Maintain explicit Subject-Predicate-Object relations for multi-hop reasoning. Keep structural relationships consistent and update/delete them when facts change.
5. **Efficient Retrieval**: Use targeted searches (`memory_recall`, `memory_recall_by_file`) before broad queries. Leverage node IDs and categories to minimize irrelevant matches.

## Tool Usage Guidelines

### Storage & Saving
- Use `memory_remember` for discrete facts, concepts, or user instructions. Include titles and descriptions for clarity.
- Use `memory_remember_file` when saving entire Workspace files as persistent knowledge bases.
- Always check if similar information already exists before creating duplicates.

### Retrieval & Search
- Start with `memory_recall` using descriptive text queries. Increase `memories_limit` only if results are sparse.
- Use `memory_recall_by_file` when comparing stored knowledge against a specific Workspace file.
- Use `memory_recall_by_node_id` for exact recall of known memory items.

### Knowledge Graph Management
- Use `memory_save_relation` for explicit facts (e.g., `"User", "owns", "dog"`). Prefer this over embedding relations in text memories.
- Use `memory_create_relationship` and `memory_delete_relationship` to manage structural hierarchy between node IDs.
- Query relations with `memory_get_entity_relations` or `memory_get_node_relations` before making assumptions or adding new facts.

### Organization & Categories
- Verify categories exist using `memory_category_exists` before linking nodes.
- Use `memory_link_node_to_category` and `memory_remove_node_from_category` to maintain logical grouping.
- Check node categories with `memory_get_node_category` during audits or merges.

### Maintenance & Context
- Delete outdated information with `memory_delete_node`.
- Read Workspace files via `memory_read_local_file` when cross-referencing external data before saving.

## Best Practices
- **Deduplicate**: Search first, then save. Use descriptive titles to aid future recall.
- **Structure Relations**: Prefer explicit Knowledge Graph relations over implicit text references for critical facts.
- **Temporal Bounds**: Set `valid_until` for time-sensitive data (e.g., project deadlines, temporary instructions).
- **Audit Regularly**: Periodically verify categories and node relations to prevent sprawl or contradictions.

## Constraints & Boundaries
- Do not store speculative or unverified information. Mark uncertain facts clearly in descriptions if saved.
- Avoid over-categorization; keep taxonomy flat unless deep hierarchy is justified.
- Never assume node IDs are stable across sessions; always query by content or title when possible.
- Respect user privacy and data sensitivity. Do not save personal identifiers without explicit context.

## Execution Protocol
When given a task involving memory:
1. Clarify the goal (store, retrieve, update, organize).
2. Check existing knowledge first using appropriate search/query tools.
3. Execute tool calls with precise parameters.
4. Confirm completion and summarize what was stored/changed.

""")

mcp_configs = []


# --- Utilities ---

def get_safe_path(base_folder: str, user_path: str) -> str:
    """Validates a path to ensure it cannot escape the specified base_folder."""
    base_dir = Path(base_folder).resolve()
    target_path = (base_dir / user_path).resolve()

    if not target_path.is_relative_to(base_dir):
        raise PermissionError(f"Security Error: Path traversal detected! '{user_path}' is outside the allowed directory.")
    if target_path == base_dir:
        raise IsADirectoryError("Security Error: Target path cannot be the base directory itself.")

    return os.path.join(base_folder, user_path)

def encode_image(filepath: str) -> Tuple[str, str]:
    """Reads an image and returns its base64 string and mime type."""
    mime_type, _ = mimetypes.guess_type(filepath)
    if not mime_type:
        mime_type = "image/jpeg"
    with open(filepath, "rb") as f:
        b64_str = base64.b64encode(f.read()).decode('utf-8').replace('\n', '').replace('\r', '').strip()
    return b64_str, mime_type

def http_stream_reader(req: urllib.request.Request, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, insecure: bool = False, timeout: int = 360):
    """Runs in a background thread to read the HTTP stream and push to an asyncio Queue."""
    try:
        ctx = None
        if insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
            for line in response:
                asyncio.run_coroutine_threadsafe(queue.put(("data", line)), loop)
        asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(queue.put(("error", e)), loop)

# --- Core LLM Logic ---

async def agent_chat_loop(url: str, messages: List[Dict], tools: List[Dict], tool_to_session: Dict, api_key: str, model: str) -> str:
    """Handles the chat logic, interacting with the LLM API and evaluating tool calls recursively."""
    while True:
        data = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        if tools:
            data["tools"] = tools

        payload = json.dumps(data, separators=(',', ':')).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Content-Length': str(len(payload))
        }
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        
        thread = threading.Thread(target=http_stream_reader, args=(req, queue, loop, True, 360), daemon=True)
        thread.start()

        current_tool_calls = {}
        current_assistant_content = ""
        finish_reason = None
        buffer = ""

        while True:
            try:
                msg_type, content_bytes = await queue.get()
            except Exception as e:
                break

            if msg_type == "error":
                raise RuntimeError(f"HTTP Stream Error: {content_bytes}")
            if msg_type == "done":
                break
                
            line = content_bytes.decode('utf-8').strip()
            if line == "data: [DONE]":
                break
                
            if line.startswith("data: "):
                data_str = line[6:]
                buffer += data_str
                try:
                    chunk = json.loads(buffer)
                    buffer = "" # clear on success
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    current_assistant_content += content

                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index")
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if "id" in tc:
                        current_tool_calls[idx]["id"] += tc["id"]
                    if "function" in tc:
                        if "name" in tc["function"]:
                            current_tool_calls[idx]["name"] += tc["function"]["name"]
                        if "arguments" in tc["function"]:
                            current_tool_calls[idx]["arguments"] += tc["function"]["arguments"]

                if choices[0].get("finish_reason") is not None:
                    finish_reason = choices[0].get("finish_reason")

        # Process Sub-Agent Tool Calls
        if finish_reason == "tool_calls" or current_tool_calls:
            assistant_msg = {"role": "assistant", "content": current_assistant_content if current_assistant_content else None, "tool_calls": []}
            
            for idx, tc in sorted(current_tool_calls.items()):
                assistant_msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                })
            messages.append(assistant_msg)

            for tc in assistant_msg["tool_calls"]:
                name = tc["function"]["name"]
                args_str = tc["function"]["arguments"]
                tool_call_id = tc["id"]
                
                print(f"[*] Sub-agent executing inner tool: {name}", file=sys.stderr)
                try:
                    args_dict = json.loads(args_str) if args_str else {}
                    session = tool_to_session.get(name)
                    
                    if session:
                        result = await session.call_tool(name, arguments=args_dict)
                        has_image = any(c.type == "image" for c in result.content)
                        if has_image:
                            tool_content_list = []
                            for c in result.content:
                                if c.type == "text":
                                    tool_content_list.append({"type": "text", "text": c.text})
                                elif c.type == "image":
                                    img_url = f"data:{c.mimeType};base64,{c.data}"
                                    tool_content_list.append({"type": "image_url", "image_url": {"url": img_url}})
                            final_content = tool_content_list
                        else:
                            final_content = "\n".join([c.text for c in result.content if c.type == "text"])
                    else:
                        final_content = f"Error: Tool '{name}' not found."
                except Exception as e:
                    final_content = f"Error executing tool '{name}': {str(e)}"
                    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": final_content
                })
                
            continue # Repeat the loop to give tool results back to LLM
            
        return current_assistant_content

async def run_agent(text: str) -> str:
    """Prepares the state, establishes inner MCP connections, and runs the sub-agent."""
    messages = []

    # 1. System Prompt
    sys_prompt = LLM_SYSTEM_PROMPT
    if sys_prompt:
        if os.path.isfile(sys_prompt):
            with open(sys_prompt, "r", encoding="utf-8") as f:
                messages.append({"role": "system", "content": f.read()})
        else:
            messages.append({"role": "system", "content": sys_prompt.strip()})
    
    # 2. User Message (Text & Images)
    user_content = []
    if text:
        user_content.append({"type": "text", "text": text})
        
    if not user_content:
        return "Error: Empty request."

    messages.append({"role": "user", "content": user_content})

    # 3. Inner MCP Configuration Setup
    # mcp_configs reads from the global variable updated in __main__
    
    async with AsyncExitStack() as stack:
        tools_list = []
        tool_to_session = {}

        for mcp_config in mcp_configs:
            endpoint = mcp_config.get("endpoint")
            mcp_api_key = mcp_config.get("api_key")
            mcp_env_base = mcp_config.get("env_base")

            try:
                if endpoint.startswith("http://") or endpoint.startswith("https://"):
                    kwargs = {}
                    if mcp_api_key:
                        kwargs["headers"] = {"Authorization": f"Bearer {mcp_api_key}"}

                    if endpoint.rstrip('/').endswith('/mcp'):
                        if streamablehttp_client is None:
                            print("Warning: streamablehttp_client not available in local MCP lib.", file=sys.stderr)
                            continue
                        transport = await stack.enter_async_context(streamablehttp_client(endpoint, **kwargs))
                    else:
                        transport = await stack.enter_async_context(sse_client(endpoint, **kwargs))
                else:
                    parts = shlex.split(endpoint)
                    server_env = None
                    if mcp_env_base:
                        server_env = os.environ.copy()
                        prefix = f"{mcp_env_base}_" if not mcp_env_base.endswith('_') else mcp_env_base
                        for k, v in os.environ.items():
                            if k.startswith(prefix):
                                server_env[k[len(prefix):]] = v
                    
                    server_params = StdioServerParameters(command=parts[0], args=parts[1:], env=server_env)
                    transport = await stack.enter_async_context(stdio_client(server_params))
                
                read, write = transport[0], transport[1]
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                mcp_tools = await session.list_tools()
                for t in mcp_tools.tools:
                    tool_to_session[t.name] = session
                    tools_list.append({
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema
                        }
                    })
            except Exception as e:
                print(f"Warning: Sub-agent failed to connect to MCP server '{endpoint}': {e}", file=sys.stderr)
        
        # 4. Trigger the Chat Process
        return await agent_chat_loop(
            url=LLM_URL,
            messages=messages,
            tools=tools_list,
            tool_to_session=tool_to_session,
            api_key=LLM_API_KEY,
            model=LLM_MODEL
        )

# --- MCP Server Setup ---

mcp_server = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

@mcp_server.tool(name=f"{TOOL_PREFIX}remember_or_recall")
async def remember_or_recall(text: str) -> str:
    """
    Remember or recall information, facts, concepts, or knowledge.
    """
    try:
        response = await run_agent(text)
        return response
    except Exception as e:
        return f"Memory Agent Execution Error: {str(e)}"

# --- Authentication Middleware ---

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        x_api_key = request.headers.get("X-API-Key")

        provided_key = None
        if auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header.split(" ", 1)[1]
        elif x_api_key:
            provided_key = x_api_key

        if not provided_key or provided_key != self.api_key:
            return JSONResponse({"detail": "Unauthorized: Invalid or missing API Key"}, status_code=401)

        return await call_next(request)

# --- Execution ---

class MCPAppendAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):        
        if getattr(namespace, 'mcp_configs', None) is None:
            setattr(namespace, 'mcp_configs', [])
        for v in values:
            namespace.mcp_configs.append({"endpoint": v, "api_key": None, "env_base": None})

class MCPAPIKeyAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        mcp_configs = getattr(namespace, 'mcp_configs', None)
        if not mcp_configs:
            parser.error(f"{option_string} must be provided after an --mcp argument")
        mcp_configs[-1]["api_key"] = values

class MCPEnvBaseAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        mcp_configs = getattr(namespace, 'mcp_configs', None)
        if not mcp_configs:
            parser.error(f"{option_string} must be provided after an --mcp argument")
        mcp_configs[-1]["env_base"] = values

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory Agent LLM MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run in standard stdio mode")
    parser.add_argument("--mcp", type=str, action=MCPAppendAction, nargs='+', help="Commands to start MCP servers (e.g., 'npx -y ...') or HTTP URLs. Can be specified multiple times.")
    parser.add_argument("--mcp-api-key", type=str, action=MCPAPIKeyAction, help="API key for the preceding MCP server.")
    parser.add_argument("--mcp-env-base", type=str, action=MCPEnvBaseAction, help="Prefix for environment variables to pass to the preceding MCP server.")
    parser.add_argument("--system", type=str, help="Path to a markdown text file containing the system message.")
    parser.add_argument("--api-key", type=str, help="Require API key for HTTP requests")
    parser.add_argument("--env-base", type=str, help="Prefix for env vars (e.g., PREFIX)")
    parser.add_argument("--tool-prefix", type=str, default="agent_", help="Prefix for MCP tools")
    parser.add_argument("--mcp-name", type=str, default="MemoryAgent", help="MCP name")
    args = parser.parse_args()
    
    if args.system:
        LLM_SYSTEM_PROMPT = args.system
        
    # --- FIX: Populate global mcp_configs from parsed args ---
    if hasattr(args, 'mcp_configs') and args.mcp_configs:
        mcp_configs.extend(args.mcp_configs)    
    # ---------------------------------------------------------
        
    # Disable SSL cert checks globally to mirror the CLI's flexibility if needed
    ssl._create_default_https_context = ssl._create_unverified_context

    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(f"Using environment variable prefix: '{actual_prefix}'", file=sys.stderr)

    if args.stdio:
        mcp_server.run()
    else:
        starlette_app = mcp_server.streamable_http_app()

        if args.api_key:
            starlette_app.add_middleware(APIKeyAuthMiddleware, api_key=args.api_key)

        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)