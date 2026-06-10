# MCP System Server
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import re
import base64
import argparse
import subprocess
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent
from typing import List, Optional, Any


def get_env_var(name: str, default: Any = None) -> Any:
    """Get an environment variable, optionally applying the env-base prefix."""
    if ENV_PREFIX:
        # Ensure there is exactly one underscore between prefix and name
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)

DEFAULT_SCRIPTS_PATH = os.path.join(".agents", "skills", "sys", "scripts")

# Parse command line options to customize server details
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="MCP_SYSTEM")
pre_parser.add_argument("--tool-prefix", type=str, default="")
pre_parser.add_argument("--mcp-name", type=str, default="System")
pre_parser.add_argument("--scripts-dir", type=str, default=DEFAULT_SCRIPTS_PATH)
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
TOOL_PREFIX = pre_args.tool_prefix
MCP_NAME = pre_args.mcp_name
SCRIPTS_DIR = pre_args.scripts_dir

# Get the scripts directory from the environment
SCRIPTS_DIR = get_env_var("DIR", SCRIPTS_DIR)
# Get the port from the environment, defaulting to 48102
HTTP_PORT = int(get_env_var("PORT", "48102"))

# Initialize the FastMCP Server
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

@mcp.tool(name=f"{TOOL_PREFIX}sys")
async def tool_sys(name: str, arguments: Optional[List[str]] = None) -> Any:
    """
    Execute a system command
    Args:
        name (str): The name of the command to execute (e.g., 'copy', 'write').
        arguments (List[str], optional): The list of arguments to pass to the script.
    """
    # Ensure name is normalized and has the .py extension
    if not name.lower().endswith(".py"):
        script_file_name = f"{name}.py"
    else:
        script_file_name = script_name

    # Prevent path traversal by keeping it to a simple base filename
    if os.path.basename(script_file_name) != script_file_name:
         return f"Error: Invalid command name '{name}'. Path traversal is not permitted."

    script_path = os.path.join(SCRIPTS_DIR, script_file_name)

    # Ensure the script actually exists
    if not os.path.isfile(script_path):
        return f"Error: Command '{name}' does not exist."

    # Build the execution command running in the current directory
    cmd = [sys.executable, script_path]
    if arguments:
        cmd.extend(arguments)

    try:
        # Run the Python interpreter as a subprocess
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        # Combine and return stdout and stderr
        output = result.stdout
        if result.stderr:
            if output:
                output += "\n" + result.stderr
            else:
                output = result.stderr

        # Check if output contains an image
        # Check result.stdout first to avoid potential pollution from stderr warnings
        for text_to_check in [result.stdout, output]:
            if not text_to_check:
                continue
            
            cleaned_text = text_to_check.strip()
            
            # 1. Check if it's a JSON object representing an image (as returned by read.py)
            if cleaned_text.startswith("{"):
                try:
                    parsed = json.loads(cleaned_text)
                    if isinstance(parsed, dict) and parsed.get("type") == "image" and "data" in parsed:
                        return ImageContent(
                            type="image",
                            data=parsed["data"],
                            mimeType=parsed.get("mimeType", "image/png"),
                        )
                except Exception:
                    pass

            # 2. Check if it's a Data URI
            if cleaned_text.startswith("data:image/"):
                base64_marker = ";base64,"
                marker_idx = cleaned_text.find(base64_marker)
                if marker_idx != -1:
                    mime_type = cleaned_text[5:marker_idx]
                    b64_part = cleaned_text[marker_idx + len(base64_marker):]
                    b64_match = re.match(r"^([a-zA-Z0-9+/=\s\r\n]+)", b64_part)
                    if b64_match:
                        raw_b64 = re.sub(r"\s+", "", b64_match.group(1))
                        return ImageContent(
                            type="image",
                            data=raw_b64,
                            mimeType=mime_type,
                        )

            # 3. Check if it is raw base64 data starting with image magic bytes
            b64_match = re.match(r"^([a-zA-Z0-9+/=\s\r\n]+)", cleaned_text)
            if b64_match:
                raw_b64 = re.sub(r"\s+", "", b64_match.group(1))
                if raw_b64:
                    # Match standard image headers
                    # Decode up to 32 chars (24 bytes) to safely identify magic bytes
                    test_b64 = raw_b64[:32]
                    padding_needed = (4 - len(test_b64) % 4) % 4
                    test_b64 += "=" * padding_needed
                    try:
                        decoded = base64.b64decode(test_b64)
                        mime_type = None
                        if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
                            mime_type = "image/png"
                        elif decoded.startswith(b"\xff\xd8\xff"):
                            mime_type = "image/jpeg"
                        elif decoded.startswith(b"GIF89a") or decoded.startswith(b"GIF87a"):
                            mime_type = "image/gif"
                        elif decoded.startswith(b"RIFF") and len(decoded) >= 12 and decoded[8:12] == b"WEBP":
                            mime_type = "image/webp"
                        elif decoded.startswith(b"BM"):
                            mime_type = "image/bmp"
                        elif decoded.startswith(b"<?xml") or decoded.startswith(b"<svg"):
                            mime_type = "image/svg+xml"

                        if mime_type:
                            full_padding_needed = (4 - len(raw_b64) % 4) % 4
                            clean_b64 = raw_b64 + "=" * full_padding_needed
                            return ImageContent(
                                type="image",
                                data=clean_b64,
                                mimeType=mime_type,
                            )
                    except Exception:
                        pass
        
        return output
    except Exception as e:
        return f"Error executing command '{script_file_name}': {str(e)}"

# --- Authentication Middleware ---
class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce API key authentication for incoming HTTP requests."""

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
            return JSONResponse(
                {"detail": "Unauthorized: Invalid or missing API Key"}, status_code=401
            )

        return await call_next(request)

# --- Execution Entrypoint ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="System Skills MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run in standard stdio mode")
    parser.add_argument("--mcp", action="store_true", help="Run in HTTP mode")
    parser.add_argument("--mcp-name", type=str, default="SystemSkills", help="MCP name")
    parser.add_argument("--scripts-dir", type=str, default=os.path.join(".agents", "skills", "sys", "scripts"), help="Skills directory path")
    parser.add_argument(
        "--env-base",
        type=str,
        help="Prefix for environment variables to isolate different servers (e.g., PREFIX)",
    )
    parser.add_argument(
        "--tool-prefix",
        type=str,
	default="",
        help="Prefix for MCP tool",
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

    if args.stdio:
        mcp.run()
    else:
        starlette_app = mcp.streamable_http_app()

        if args.api_key:
            starlette_app.add_middleware(APIKeyAuthMiddleware, api_key=args.api_key)

        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(starlette_app, host="127.0.0.1", port=HTTP_PORT)

