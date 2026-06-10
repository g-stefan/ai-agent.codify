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

def replace(filename: str, text: str, new_text: str, workspace_dir: str) -> str:
    """Replace specific occurrences of text in a file with new text."""        
    try:
        filepath = get_safe_path(workspace_dir, filename)

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

    except FileNotFoundError:
        return f"Error: The system cannot find the path specified for '{filename}'."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    
    return f"Successfully replaced {occurrences} occurrence(s) of text in '{filename}'."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replace specific occurrences of text in a file.")
    parser.add_argument("filename_pos", nargs="?", help="The file to edit.")
    parser.add_argument("text_pos", nargs="?", help="The exact text to replace.")
    parser.add_argument("new_text_pos", nargs="?", help="The new text to replace with.")
    parser.add_argument("--filename", help="The file to edit.")
    parser.add_argument("--text", help="The exact text to replace.")
    parser.add_argument("--new-text", help="The new text to replace with.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    text = args.text or args.text_pos
    new_text = args.new_text or args.new_text_pos

    if not filename or text is None or new_text is None:
        print("Error: filename, text to replace, and new_text are all required.")
        sys.exit(1)

    result = replace(filename, text, new_text, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
