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

def write(filename: str, text: str, workspace_dir: str) -> str:
    """Write file contents (only text)."""        
    try:
        filepath = get_safe_path(workspace_dir, filename)
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write file contents (only text).")
    parser.add_argument("filename_pos", nargs="?", help="The name of the file to write to.")
    parser.add_argument("text_pos", nargs="?", help="The text content to write.")
    parser.add_argument("--filename", help="The name of the file to write to.")
    parser.add_argument("--text", help="The text content to write.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    text = args.text or args.text_pos

    if not filename or text is None:
        print("Error: Both filename and text are required.")
        sys.exit(1)

    result = write(filename, text, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
