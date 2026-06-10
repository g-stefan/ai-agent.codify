# MCP System Server
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
import datetime
import shutil
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from typing import List, Any, Optional
from pathlib import Path
from mcp.types import ImageContent

# --- Pre-parse --env-base ---
# We use a separate parser that ignores unknown args to grab the env-base prefix early,
# because we need it to resolve our module-level configuration variables below.
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--tool-prefix", type=str, default="")
pre_parser.add_argument("--mcp-name", type=str, default="System")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
TOOL_PREFIX = pre_args.tool_prefix
MCP_NAME = pre_args.mcp_name

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
WORKSPACE_DIR = get_env_var("DIR", "Workspace")
# Get the port from the environment, defaulting to 48102
PORT = int(get_env_var("PORT", "48108"))

os.makedirs(WORKSPACE_DIR, exist_ok=True)


# --- Security & Path Safety ---
def get_safe_path(base_folder: str, user_path: str) -> Path:
    """
    Validates a path to ensure it cannot escape the specified base_folder
    using path traversal (e.g., '../').
    """
    base_dir = Path(base_folder).resolve()
    target_path = (base_dir / user_path).resolve()

    if not target_path.is_relative_to(base_dir):
        raise PermissionError(
            f"Security Error: Path traversal detected! '{user_path}' is outside the allowed directory."
        )

    if target_path == base_dir:
        raise IsADirectoryError(
            "Security Error: Target path cannot be the base directory itself."
        )

    return base_folder + "/" + user_path


def apply_diff_text(original_text: str, diff_text: str) -> str:
    """
    Applies a standard unified diff to the original text and returns the modified result.
    """
    original_lines = original_text.splitlines()
    diff_lines = diff_text.splitlines()

    result_lines = []
    orig_idx = 0  # Tracks our current line number in the original text (0-indexed)

    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]

        # Skip the file header lines
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue

        # Look for a hunk header, e.g., @@ -1,4 +1,5 @@
        if line.startswith("@@"):
            # Extract the starting line number for the original text
            parts = line.split()
            orig_info = parts[1]  # e.g., "-1,4"
            orig_start = int(orig_info.split(",")[0].replace("-", ""))

            # Catch up: Add any unmodified lines that appeared before this hunk
            while orig_idx < orig_start - 1:
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1

            i += 1

            # Process the lines inside this hunk
            while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                hunk_line = diff_lines[i]

                # Safety check for next file headers if multiple files are in one diff
                if hunk_line.startswith("---") or hunk_line.startswith("+++"):
                    break

                # Determine the action: space (context), - (deletion), or + (addition)
                action = hunk_line[0] if len(hunk_line) > 0 else " "
                content = hunk_line[1:]

                if action == " ":
                    # Context line: keep original
                    if orig_idx < len(original_lines):
                        result_lines.append(original_lines[orig_idx])
                        orig_idx += 1
                elif action == "-":
                    # Deletion: skip this line in the original text
                    orig_idx += 1
                elif action == "+":
                    # Addition: insert the new content
                    result_lines.append(content)

                i += 1
            continue

        i += 1

    # Add any remaining lines from the original text that appeared after the last hunk
    while orig_idx < len(original_lines):
        result_lines.append(original_lines[orig_idx])
        orig_idx += 1

    return "\n".join(result_lines)


def apply_diff_file(filename: str, diff_text: str) -> bool:
    """
    Reads a file, applies a unified diff, and writes the modified text back.
    """
    with open(filename, "r", encoding="utf-8") as f:
        original_text = f.read()

    modified_text = apply_diff_text(original_text, diff_text)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(modified_text)

    return True


def read_file_chunk(file_path: str, offset: int = 0, max_lines: Optional[int] = None) -> str:
    """
    Reads a specific chunk of a file starting from a given line offset.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' was not found.")

    if offset < 0:
        raise ValueError("Offset must be a non-negative integer.")

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            stop = offset + max_lines if max_lines is not None else None
            chunk_lines = itertools.islice(file, offset, stop)
            return "".join(chunk_lines)

    except UnicodeDecodeError:
        raise ValueError(f"File '{file_path}' is not a valid UTF-8 text file.")
    except Exception as e:
        raise RuntimeError(f"An error occurred while reading the file: {e}")


# --- Initialize FastMCP Server ---
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

@mcp.tool(name=f"{TOOL_PREFIX}sys")
async def tool_sys(cmd: str, args: Optional[List[str]] = None) -> Any:
    """
    Executes system actions by mapping arguments dynamically.
    All command arguments must be elements in the 'args' list. If a command requires numerical 
    or boolean inputs, they should be passed as their string representations in the list.
    """
    cmd_lower = cmd.strip().lower()

    try:
        # --- List files / directory listing ---
        if cmd_lower in ("dir", "list_files"):
            pattern = "*"
            subfolder = ""
            if args and len(args) > 0:
                param = args[0]
                try:
                    full_param_path = get_safe_path(WORKSPACE_DIR, param)
                    if os.path.isdir(full_param_path):
                        subfolder = param
                    else:
                        pattern = param
                except Exception:
                    pattern = param

            myPath = WORKSPACE_DIR
            if subfolder:
                myPath = os.path.join(WORKSPACE_DIR, subfolder)

            if not os.path.exists(myPath):
                return f"Error: Path '{subfolder or WORKSPACE_DIR}' does not exist."

            myFiles = []
            for dirpath, dirnames, filenames in os.walk(myPath):
                for f in filenames:
                    myFiles.append(os.path.join(dirpath, f))

            retV = []
            for line in myFiles:
                lineX = re.sub(r"[\\]", "/", line)
                # Normalize path structure relative to the workspace directory
                rel_path = lineX[len(WORKSPACE_DIR) + 1 :]
                filename = os.path.basename(lineX)

                if pattern != "*":
                    if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(filename, pattern):
                        retV.append(rel_path)
                else:
                    retV.append(rel_path)
            return retV

        # --- Copy ---
        elif cmd_lower == "copy":
            if not args or len(args) < 2:
                return "Error: 'copy' command requires 2 arguments: [source, destination]"
            source, destination = args[0], args[1]
            source_path = get_safe_path(WORKSPACE_DIR, source)
            dest_path = get_safe_path(WORKSPACE_DIR, destination)

            if not os.path.exists(source_path):
                return f"Error: The source file '{source}' does not exist."

            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            return f"Successfully copied '{source}' to '{destination}'."

        # --- Read ---
        elif cmd_lower == "read":
            if not args or len(args) < 1:
                return "Error: 'read' command requires 1 argument: [filename]"
            filename = args[0]
            filepath = get_safe_path(WORKSPACE_DIR, filename)

            ext = os.path.splitext(filepath)[1].lower()
            is_image = ext in [".png", ".jpeg", ".jpg"]
            if is_image:
                image_format = "jpeg" if ext in [".jpeg", ".jpg"] else "png"
                with open(filepath, "rb") as f:
                    data = f.read()
                    b64_data = base64.b64encode(data).decode("utf-8")
                    return ImageContent(
                        type="image",
                        data=b64_data,
                        mimeType=f"image/{image_format}",
                    )
            
            with open(filepath, "r", encoding="utf8") as f:
                return f.read()

        # --- Grep ---
        elif cmd_lower == "grep":
            if not args or len(args) < 1:
                return "Error: 'grep' command requires at least 1 argument: [pattern] or [pattern, file_pattern]"
            pattern = args[0]
            file_pattern = args[1] if len(args) > 1 else "*"

            myPath = WORKSPACE_DIR
            if not os.path.exists(myPath):
                return f"Error: Workspace directory '{myPath}' does not exist."

            try:
                search_regex = re.compile(pattern)
                is_regex = True
            except re.error:
                is_regex = False

            retV = []
            for dirpath, dirnames, filenames in os.walk(myPath):
                for f in filenames:
                    if file_pattern != "*" and not fnmatch.fnmatch(f, file_pattern):
                        continue

                    full_path = os.path.join(dirpath, f)
                    lineX = re.sub(r"[\\]", "/", full_path)
                    rel_path = lineX[len(WORKSPACE_DIR) + 1 :]

                    try:
                        with open(full_path, "r", encoding="utf-8") as file:
                            for line_num, line in enumerate(file, 1):
                                match_found = False
                                if is_regex:
                                    if search_regex.search(line):
                                        match_found = True
                                else:
                                    if pattern in line:
                                        match_found = True

                                if match_found:
                                    retV.append(f"{rel_path}\t{line_num}\t{line.rstrip('\r\n')}")
                    except (UnicodeDecodeError, PermissionError):
                        continue
            return retV

        # --- Write ---
        elif cmd_lower == "write":
            if not args or len(args) < 2:
                return "Error: 'write' command requires 2 arguments: [filename, text]"
            filename, text = args[0], args[1]
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf8") as f:
                f.write(text)
            return f"Successfully wrote {len(text)} characters to '{filename}'."

        # --- Mkdir ---
        elif cmd_lower == "mkdir":
            if not args or len(args) < 1:
                return "Error: 'mkdir' command requires 1 argument: [path]"
            path = args[0]
            dirpath = get_safe_path(WORKSPACE_DIR, path)
            Path(dirpath).mkdir(parents=True, exist_ok=True)
            return f"Successfully created directory '{path}'."

        # --- Append ---
        elif cmd_lower == "append":
            if not args or len(args) < 2:
                return "Error: 'append' command requires 2 arguments: [filename, text]"
            filename, text = args[0], args[1]
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "a", encoding="utf8") as f:
                f.write(text)
            return f"Successfully appended {len(text)} characters to '{filename}'."

        # --- Diff ---
        elif cmd_lower == "diff":
            if not args or len(args) < 2:
                return "Error: 'diff' command requires 2 arguments: [filename, diff_text]"
            filename, text = args[0], args[1]
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            if not apply_diff_file(filepath, text):
                return "Error: unknown error. Diff not applied."
            return "Diff applied successfully."

        # --- Replace ---
        elif cmd_lower == "replace":
            if not args or len(args) < 3:
                return "Error: 'replace' command requires 3 arguments: [filename, text_to_replace, new_text]"
            filename, text, new_text = args[0], args[1], args[2]
            filepath = get_safe_path(WORKSPACE_DIR, filename)

            if not Path(filepath).is_file():
                return f"Error: The file '{filename}' does not exist."

            with open(filepath, "r", encoding="utf8") as f:
                content = f.read()

            if text not in content:
                return f"Warning: The exact text to replace was not found in '{filename}'. No changes made."

            occurrences = content.count(text)
            new_content = content.replace(text, new_text)

            with open(filepath, "w", encoding="utf8") as f:
                f.write(new_content)
            return f"Successfully replaced {occurrences} occurrence(s) of text in '{filename}'."

        # --- Delete ---
        elif cmd_lower == "delete":
            if not args or len(args) < 1:
                return "Error: 'delete' command requires 1 argument: [filename]"
            filename = args[0]
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            if os.path.exists(filepath):
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                else:
                    os.remove(filepath)
                return f"Successfully deleted '{filename}'."
            return f"Error: File or directory '{filename}' does not exist."

        # --- Rename ---
        elif cmd_lower == "rename":
            if not args or len(args) < 2:
                return "Error: 'rename' command requires 2 arguments: [source, destination]"
            source, destination = args[0], args[1]
            source_path = get_safe_path(WORKSPACE_DIR, source)
            dest_path = get_safe_path(WORKSPACE_DIR, destination)

            if not os.path.exists(source_path):
                return f"Error: The source file '{source}' does not exist."

            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            os.rename(source_path, dest_path)
            return f"Successfully renamed '{source}' to '{destination}'."

        # --- Metadata ---
        elif cmd_lower == "metadata":
            if not args or len(args) < 1:
                return "Error: 'metadata' command requires 1 argument: [filename]"
            filename = args[0]
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            if not os.path.exists(filepath):
                return {"error": f"File not found: {filename}"}
            
            stat = os.stat(filepath)
            return {
                "filename": filename,
                "size_bytes": stat.st_size,
                "created": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_directory": os.path.isdir(filepath),
                "is_file": os.path.isfile(filepath)
            }

        # --- List text with line numbers ---
        elif cmd_lower == "list":
            if not args or len(args) < 1:
                return "Error: 'list' command requires 1 argument: [filename]"
            filename = args[0]
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            
            ext = os.path.splitext(filepath)[1].lower()
            if ext in [".png", ".jpeg", ".jpg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".bin"]:
                return f"Error: '{filename}' appears to be a binary file. This command only supports text files."

            lines_with_numbers = []
            with open(filepath, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    lines_with_numbers.append(f"{line_num}\t{line.rstrip('\r\n')}")
            return "\n".join(lines_with_numbers)

        # --- Read Lines ---
        elif cmd_lower == "read_lines":
            if not args or len(args) < 2:
                return "Error: 'read_lines' command requires at least 2 arguments: [filename, offset] or [filename, offset, count]"
            filename = args[0]
            try:
                offset = int(args[1])
            except ValueError:
                return f"Error: 'offset' must be an integer, got '{args[1]}'"

            count = 2000
            if len(args) >= 3:
                try:
                    count = int(args[2])
                except ValueError:
                    return f"Error: 'count' must be an integer, got '{args[2]}'"

            filepath = get_safe_path(WORKSPACE_DIR, filename)
            return read_file_chunk(filepath, offset, count)

        # --- Search ---
        elif cmd_lower == "search":
            if not args or len(args) < 1:
                return "Error: 'search' command requires 1 argument: [pattern]"
            pattern = args[0]
            myPath = WORKSPACE_DIR
            if not os.path.exists(myPath):
                return f"Error: Workspace directory '{myPath}' does not exist."

            myFiles = []
            for dirpath, dirnames, filenames in os.walk(myPath):
                for f in filenames:
                    myFiles.append(os.path.join(dirpath, f))

            retV = []
            for line in myFiles:
                lineX = re.sub(r"[\\]", "/", line)
                rel_path = lineX[len(WORKSPACE_DIR) + 1 :]
                filename = os.path.basename(lineX)
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(filename, pattern):
                    retV.append(rel_path)
            return retV

        else:
            supported = [
                "dir / list_files", "copy", "read", "grep", "write", "mkdir",
                "append", "diff", "replace", "delete", "rename", "metadata",
                "list", "read_lines", "search"
            ]
            return f"Error: Unknown system command '{cmd}'. Supported commands: {', '.join(supported)}"

    except FileNotFoundError:
        return f"Error: File not found or the specified path does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"


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
    parser = argparse.ArgumentParser(description="System Unified MCP Server")
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
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable write functionality (only read/list functions will be active)",
    )
    parser.add_argument(
        "--tool-prefix",
        type=str,
        default="",
        help="Prefix for MCP tool, default is empty resulting in 'sys'",
    )
    parser.add_argument(
        "--mcp-name",
        type=str,
        default="System",
        help="MCP name, default: System",
    )

    args = parser.parse_args()

    # STDIO logs must be printed to sys.stderr to avoid breaking JSON-RPC communication on stdout.
    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(
            f"Using environment variable prefix: '{actual_prefix}' (expecting {actual_prefix}PORT)",
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

        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)