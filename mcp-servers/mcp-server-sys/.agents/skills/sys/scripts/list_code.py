#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import argparse
from pathlib import Path

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

def list_code(filename: str, workspace_dir: str) -> str:
    """
    Read text file contents and return lines prefixed by line numbers separated by a tab.
    Only works for text files.
    """
    try:
        filepath = get_safe_path(workspace_dir, filename)
        
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read text file contents and return lines prefixed by line numbers.")
    parser.add_argument("filename_pos", nargs="?", help="The name of the file to list.")
    parser.add_argument("--filename", help="The name of the file to list.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    if not filename:
        print("Error: Filename is required.")
        sys.exit(1)

    result = list_code(filename, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
