# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import re
import os
import sys
import fnmatch
import uvicorn
import argparse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from typing import List, Any
from pathlib import Path

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


# Get the workspace directory from the environment, defaulting to "Workspace"
WORKSPACE_DIR = get_env_var("WORKSPACE_DIR", "Workspace")
# Get the port from the environment, defaulting to 48102
PORT = int(get_env_var("PORT", "48102"))
# Flag to hide directories starting with a dot (e.g., .git, .agent), defaults to True
HIDE_DOT_DIRS = get_env_var("HIDE_DOT_DIRS", "true").lower() in ("true", "1", "yes")

os.makedirs(WORKSPACE_DIR, exist_ok=True)

# ---
def get_safe_path(base_folder: str, user_path: str) -> Path:
    """
    Validates a path to ensure it cannot escape the specified base_folder
    using path traversal (e.g., '../').

    Args:
        base_folder (str): The root directory where files are allowed to be accessed.
        user_path (str): The file path provided by the user.

    Returns:
        Path: The resolved, safe target Path object.

    Raises:
        PermissionError: If a path traversal attempt is detected.
        IsADirectoryError: If the target path points to the base directory itself.
    """
    # 1. Get the absolute, normalized path of the base folder.
    base_dir = Path(base_folder).resolve()

    # 2. Combine the base folder with the user-provided path.
    target_path = (base_dir / user_path).resolve()

    # 3. Check if the resolved target path is still within the base directory.
    if not target_path.is_relative_to(base_dir):
        raise PermissionError(
            f"Security Error: Path traversal detected! '{user_path}' is outside the allowed directory."
        )

    # 4. Prevent referencing the base directory itself directly if not wanted.
    if target_path == base_dir:
        raise IsADirectoryError(
            "Security Error: Target path cannot be the base directory itself."
        )

    return base_folder + "/" + user_path


# ---

mcp = FastMCP("Workspace", stateless_http=True, json_response=False)


@mcp.tool()
async def read_file_content_from_workspace(filename: str) -> str:
    """Read file contents from workspace."""
    text = ""
    try:
        filename = get_safe_path(WORKSPACE_DIR, filename)
        with open(filename, "r", encoding="utf8") as f:
            text = f.read()
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    return text


@mcp.tool()
async def write_file_content_to_workspace(filename: str, text: str) -> str:
    """Write file contents to workspace."""
    basePath = WORKSPACE_DIR
    try:
        filename = get_safe_path(WORKSPACE_DIR, filename)
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "w", encoding="utf8") as f:
            f.write(text)
    except FileNotFoundError:
        return f"Error: The system cannot find the path specified for '{filename}'."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    filenameX = filename[len(basePath) + 1 :]
    return f"Successfully wrote {len(text)} characters to '{filenameX}'."


@mcp.tool()
async def list_files_on_workspace() -> List[str]:
    """List files found on workspace."""
    try:
        myPath = WORKSPACE_DIR
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"Workspace directory '{myPath}' does not exist.")

        myFiles = []
        for dirpath, dirnames, filenames in os.walk(myPath):
            if HIDE_DOT_DIRS:
                # Modify dirnames in-place to prevent os.walk from entering dot directories
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for f in filenames:
                myFiles.append(os.path.join(dirpath, f))

        retV = []
        for line in myFiles:
            lineX = re.sub(r"[\\]", "/", line)
            retV.append(lineX[len(myPath) + 1 :])
    except FileNotFoundError as e:
        return [f"Error: {str(e)}"]
    except PermissionError as e:
        return [f"Error: Permission denied. {str(e)}"]
    except Exception as e:
        return [f"Error: An unexpected system error occurred. {str(e)}"]
    return retV


@mcp.tool()
async def search_files_on_workspace_by_filename(pattern: str = "*") -> List[str]:
    """Search files on workspace by filename pattern."""
    try:
        myPath = WORKSPACE_DIR
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"Workspace directory '{myPath}' does not exist.")

        myFiles = []
        for dirpath, dirnames, filenames in os.walk(myPath):
            if HIDE_DOT_DIRS:
                # Modify dirnames in-place to prevent os.walk from entering dot directories
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for f in filenames:
                myFiles.append(os.path.join(dirpath, f))

        retV = []
        for line in myFiles:
            lineX = re.sub(r"[\\]", "/", line)
            rel_path = lineX[len(myPath) + 1 :]
            filename = os.path.basename(lineX)
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(filename, pattern):
                retV.append(rel_path)
    except FileNotFoundError as e:
        return [f"Error: {str(e)}"]
    except PermissionError as e:
        return [f"Error: Permission denied. {str(e)}"]
    except Exception as e:
        return [f"Error: An unexpected system error occurred. {str(e)}"]
    return retV


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce API key authentication for incoming HTTP requests."""

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        # Allow OPTIONS requests to pass through for CORS preflight
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Workspace MCP Server")
    parser.add_argument(
        "--stdio", action="store_true", help="Run in standard stdio mode"
    )
    parser.add_argument(
        "--mcp", action="store_true", help="Run in HTTP mode (current/default mode)"
    )
    parser.add_argument("--api-key", type=str, help="Require API key for HTTP requests")
    parser.add_argument(
        "--env-base",
        type=str,
        help="Prefix for environment variables to isolate different servers (e.g., PREFIX)",
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
        # Run the server in standard stdio mode
        mcp.run()
    else:
        # Default behavior (also catches --mcp)
        # Get the Starlette app for streamable HTTP
        starlette_app = mcp.streamable_http_app()

        # Add API Key Middleware if specified
        if args.api_key:
            starlette_app.add_middleware(APIKeyAuthMiddleware, api_key=args.api_key)

        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "*"
            ],  # Allow all origins for development; restrict in production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Run the server
        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)
