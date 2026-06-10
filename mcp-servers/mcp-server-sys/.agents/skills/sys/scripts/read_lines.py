#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import itertools
import argparse
from pathlib import Path
from typing import Optional

def get_safe_path(base_folder: str, user_path: str) -> str:
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

def read_file_chunk(
    file_path: str, offset: int = 0, max_lines: Optional[int] = None
) -> str:
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

def read_lines(filename: str, offset: int, count: int, workspace_dir: str) -> str:
    """Read file content by count lines from line at offset."""
    try:
        filepath = get_safe_path(workspace_dir, filename)
        return read_file_chunk(filepath, offset, count)
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read file content by count lines from line at offset.")
    parser.add_argument("filename_pos", nargs="?", help="The file to read.")
    parser.add_argument("offset_pos", type=int, nargs="?", help="The starting line number (0-indexed).")
    parser.add_argument("count_pos", type=int, nargs="?", default=2000, help="The maximum number of lines to read.")
    parser.add_argument("--filename", help="The file to read.")
    parser.add_argument("--offset", type=int, help="The starting line number (0-indexed).")
    parser.add_argument("--count", type=int, help="The maximum number of lines to read.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    offset = args.offset if args.offset is not None else args.offset_pos
    count = args.count if args.count is not None else args.count_pos

    if not filename or offset is None:
        print("Error: Both filename and offset are required.")
        sys.exit(1)

    result = read_lines(filename, offset, count, args.workspace_dir)
    print(result, end="")
    if result.startswith("Error:"):
        sys.exit(1)
