# MCP Workspace
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
pre_parser.add_argument("--read-only", action="store_true")
pre_parser.add_argument("--tool-prefix", type=str, default="workspace_")
pre_parser.add_argument("--mcp-name", type=str, default="Workspace")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
READ_ONLY = pre_args.read_only
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


def apply_diff_text(original_text, diff_text):
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


def apply_diff_file(filename, diff_text):
    """
    Reads a file, applies a unified diff using apply_diff,
    and writes the modified text back to the file.
    """
    with open(filename, "r", encoding="utf-8") as f:
        original_text = f.read()

    modified_text = apply_diff_text(original_text, diff_text)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(modified_text)

    return True


def read_file_chunk(
    file_path: str, offset: int = 0, max_lines: Optional[int] = None
) -> str:
    """
    Reads a specific chunk of a file starting from a given line offset.

    Args:
        file_path (str): The path to the file to be read.
        offset (int): The starting line number (0-indexed). Defaults to 0.
        max_lines (int, optional): The maximum number of lines to read.
                                   If None, reads to the end of the file.

    Returns:
        str: A single string containing the requested lines, ready for LLM input.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' was not found.")

    if offset < 0:
        raise ValueError("Offset must be a non-negative integer.")

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            # Calculate where to stop reading
            stop = offset + max_lines if max_lines is not None else None

            # itertools.islice efficiently skips the first 'offset' lines
            # without loading them into memory, then yields the next lines up to 'stop'
            chunk_lines = itertools.islice(file, offset, stop)

            # Join the lines into a single text block
            return "".join(chunk_lines)

    except UnicodeDecodeError:
        raise ValueError(f"File '{file_path}' is not a valid UTF-8 text file.")
    except Exception as e:
        raise RuntimeError(f"An error occurred while reading the file: {e}")


# ---
# Initialize the MCP Server
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

# Only register write functionality if not in read-only mode
if not READ_ONLY:

    @mcp.tool(name=f"{TOOL_PREFIX}write")
    async def tool_write(filename: str, text: str) -> str:
        """Write file contents (only text)."""        
        try:
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf8") as f:
                f.write(text)
        except FileNotFoundError:
            return f"Error: The system cannot find the path specified for '{filename}'."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"        
        return f"Successfully wrote {len(text)} characters to '{filename}'."

    @mcp.tool(name=f"{TOOL_PREFIX}create_directory")
    async def tool_create_directory(path: str) -> str:
        """Creates a new directory (supports recursive creation)"""
        try:
            dirpath = get_safe_path(WORKSPACE_DIR, path)
            Path(dirpath).mkdir(parents=True, exist_ok=True)
        except FileNotFoundError:
            return f"Error: The system cannot find the path specified for '{path}'."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"
        return f"Successfully created directory '{path}'."

    @mcp.tool(name=f"{TOOL_PREFIX}append")
    async def tool_append(filename: str, text: str) -> str:
        """Append text to a file."""
        try:
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            # Ensure parent directories exist
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "a", encoding="utf8") as f:
                f.write(text)
        except FileNotFoundError:
            return f"Error: The system cannot find the path specified for '{filename}'."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"
        return f"Successfully appended {len(text)} characters to '{filename}'."

    @mcp.tool(name=f"{TOOL_PREFIX}copy")
    async def tool_copy(source: str, destination: str) -> str:
        """Copy a file."""
        try:
            source_path = get_safe_path(WORKSPACE_DIR, source)
            dest_path = get_safe_path(WORKSPACE_DIR, destination)

            if not os.path.exists(source_path):
                return f"Error: The source file '{source}' does not exist."

            # Ensure the parent directories of the destination exist
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source_path, dest_path)
        except FileNotFoundError:
            return f"Error: The system cannot find the path specified."
        except FileExistsError:
            return f"Error: The destination path '{destination}' already exists."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except OSError as e:
            return f"Error: OS error occurred. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"
        return f"Successfully copied '{source}' to '{destination}'."

    @mcp.tool(name=f"{TOOL_PREFIX}apply_diff")
    async def tool_apply_diff(filename: str, text: str) -> str:
        """Apply standard unified diff to file."""
        try:
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            if not apply_diff_file(filepath, text):
                return "Error: unknown error. Diff not applied."
        except FileNotFoundError:
            return f"Error: File not found. The path '{filename}' does not exist."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"
        return "Diff applied successfully."

    @mcp.tool(name=f"{TOOL_PREFIX}replace_text")
    async def tool_replace_text(filename: str, text: str, new_text: str) -> str:
        """Replace specific occurrences of text in a file with new text."""        
        try:
            # Resolve the safe path
            filepath = get_safe_path(WORKSPACE_DIR, filename)

            # Ensure the file actually exists before reading
            if not Path(filepath).is_file():
                return f"Error: The file '{filename}' does not exist."

            # Read the current contents of the file
            with open(filepath, "r", encoding="utf8") as f:
                content = f.read()

            # Check if the text to replace actually exists in the file
            if text not in content:
                return f"Warning: The exact text to replace was not found in '{filename}'. No changes made."

            # Count occurrences for the success message
            occurrences = content.count(text)

            # Replace the text
            new_content = content.replace(text, new_text)

            # Write the updated contents back to the file
            with open(filepath, "w", encoding="utf8") as f:
                f.write(new_content)

        except FileNotFoundError:
            return f"Error: The system cannot find the path specified for '{filename}'."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"
        
        return f"Successfully replaced {occurrences} occurrence(s) of text in '{filename}'."

    @mcp.tool(name=f"{TOOL_PREFIX}delete")
    async def tool_delete(filename: str) -> str:
        """Delete file or directory"""        
        try:
            filepath = get_safe_path(WORKSPACE_DIR, filename)
            if os.path.exists(filepath):
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                else:
                    os.remove(filepath)
        except FileNotFoundError:
            return f"Error: The system cannot find the path specified for '{filename}'."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"        
        return f"Successfully deleted '{filename}'."

    @mcp.tool(name=f"{TOOL_PREFIX}rename")
    async def tool_rename(source: str, destination: str) -> str:
        """Rename or move a file."""
        try:
            # Get safe paths for both source and destination
            source_path = get_safe_path(WORKSPACE_DIR, source)
            dest_path = get_safe_path(WORKSPACE_DIR, destination)

            if not os.path.exists(source_path):
                return f"Error: The source file '{source}' does not exist."

            # Ensure the parent directories of the destination exist
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)

            os.rename(source_path, dest_path)
        except FileNotFoundError:
            return f"Error: The system cannot find the path specified."
        except FileExistsError:
            return f"Error: The destination path '{destination}' already exists."
        except PermissionError as e:
            return f"Error: Permission denied. {str(e)}"
        except OSError as e:
            return f"Error: OS error occurred. {str(e)}"
        except Exception as e:
            return f"Error: An unexpected system error occurred. {str(e)}"        
        return f"Successfully renamed '{source}' to '{destination}'."

# ---


@mcp.tool(name=f"{TOOL_PREFIX}file_info")
async def tool_file_info(filename: str) -> dict:
    """Returns metadata"""
    try:
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
    except PermissionError as e:
        return {"error": f"Permission denied: {str(e)}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}


@mcp.tool(name=f"{TOOL_PREFIX}read")
async def tool_read_file(filename: str) -> Any:
    """Read a text file."""
    text = ""
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)

        ext = os.path.splitext(filepath)[1].lower()
        is_image = ext in [".png", ".jpeg", ".jpg"]
        if is_image:
            return f"Error: It's an image file."
        
        with open(filepath, "r", encoding="utf8") as f:
            text = f.read()
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    return text

@mcp.tool(name=f"{TOOL_PREFIX}read_image")
async def tool_read_image(filename: str) -> Any:
    """Read an image file."""
    text = ""
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)

        ext = os.path.splitext(filepath)[1].lower()
        is_image = ext in [".png", ".jpeg", ".jpg"]
        if not is_image:
            return f"Error: It's a text file."
        
        imageFormat = "jpeg" if ext in [".jpeg", ".jpg"] else "png"
        with open(filepath, "rb") as f:
            data = f.read()
            b64_data = base64.b64encode(data).decode("utf-8")
            return ImageContent(
                type="image",
                data=b64_data,
                mimeType=f"image/{imageFormat.lower()}",
            )
                
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    return text


@mcp.tool(name=f"{TOOL_PREFIX}read_with_line_numbers")
async def tool_read_with_line_numbers(filename: str) -> str:
    """
    Reads a text file with line numbers prepended.    
    """
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)
        
        # Prevent attempting to read binary file extensions
        ext = os.path.splitext(filepath)[1].lower()
        if ext in [".png", ".jpeg", ".jpg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".bin"]:
            return f"Error: '{filename}' appears to be a binary file. This tool only supports text files."

        lines_with_numbers = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                lines_with_numbers.append(f"{line_num}:\t{line.rstrip('\r\n')}")
        
        return "\n".join(lines_with_numbers)
    except UnicodeDecodeError:
         return f"Error: File '{filename}' is not a valid UTF-8 text file."
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"


@mcp.tool(name=f"{TOOL_PREFIX}list")
async def tool_list() -> List[str]:
    """Returns a list of files and subdirectories in a path."""
    try:
        myPath = WORKSPACE_DIR
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"{MCP_NAME} directory does not exist.")

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


@mcp.tool(name=f"{TOOL_PREFIX}search")
async def tool_search(pattern: str = "*") -> List[str]:
    """Search files by filename pattern."""
    try:
        myPath = WORKSPACE_DIR
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"{MCP_NAME} directory does not exist.")

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


@mcp.tool(name=f"{TOOL_PREFIX}read_lines")
async def tool_read_lines(filename: str, offset: int, count: int = 2000) -> str:
    """Read text file content by count lines from line at offset."""
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)
        return read_file_chunk(filepath, offset, count)
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"


@mcp.tool(name=f"{TOOL_PREFIX}grep")
async def tool_grep(pattern: str, file_pattern: str = "*") -> List[str]:
    """
    Search the contents of files for a given text or regex pattern.
    Returns a list of matching lines formatted as 'relative_filepath\tline_number\tline_content'.

    Args:
        pattern: The text or regular expression to search for inside files.
        file_pattern: Optional glob pattern to filter which files to read (e.g., "*.py"). Default is "*".
    """
    try:
        myPath = WORKSPACE_DIR
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"{MCP_NAME} directory does not exist.")

        # Attempt to compile the pattern as a regex.
        # If it's an invalid regex (e.g., "*foo*"), fallback to literal text matching.
        try:
            search_regex = re.compile(pattern)
            is_regex = True
        except re.error:
            is_regex = False

        retV = []
        for dirpath, dirnames, filenames in os.walk(myPath):
            if HIDE_DOT_DIRS:
                # Modify dirnames in-place to prevent os.walk from entering dot directories
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for f in filenames:
                # Check if the filename matches the optional file_pattern
                if file_pattern != "*" and not fnmatch.fnmatch(f, file_pattern):
                    continue

                full_path = os.path.join(dirpath, f)

                # Normalize path and get relative path, same as search_files
                lineX = re.sub(r"[\\]", "/", full_path)
                rel_path = lineX[len(str(myPath)) + 1 :]

                try:
                    # Open and read file line by line to keep memory usage low
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
                                # Return format: file_path\tline_number\tline_content
                                retV.append(f"{rel_path}\t{line_num}:\t{line.rstrip('\r\n')}")

                except UnicodeDecodeError:
                    # Gracefully skip binary files or files with unsupported encodings
                    continue
                except PermissionError:
                    # Skip files we don't have permission to read
                    continue

    except FileNotFoundError as e:
        return [f"Error: {str(e)}"]
    except PermissionError as e:
        return [f"Error: Permission denied. {str(e)}"]
    except Exception as e:
        return [f"Error: An unexpected system error occurred. {str(e)}"]
   
    return retV


# --- Authentication Middleware ---


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
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable write functionality (only read/list functions will be active)",
    )
    parser.add_argument(
        "--tool-prefix",
        type=str,
	default="workspace_",
        help="Prefix for MCP tool",
    )
    parser.add_argument(
        "--mcp-name",
        type=str,
	default="Workspace",
        help="MCP name, default: Workspace",
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