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

def apply_diff_text(original_text, diff_text):
    original_lines = original_text.splitlines()
    diff_lines = diff_text.splitlines()

    result_lines = []
    orig_idx = 0

    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]

        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue

        if line.startswith("@@"):
            parts = line.split()
            orig_info = parts[1]
            orig_start = int(orig_info.split(",")[0].replace("-", ""))

            while orig_idx < orig_start - 1:
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1

            i += 1

            while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                hunk_line = diff_lines[i]

                if hunk_line.startswith("---") or hunk_line.startswith("+++"):
                    break

                action = hunk_line[0] if len(hunk_line) > 0 else " "
                content = hunk_line[1:]

                if action == " ":
                    if orig_idx < len(original_lines):
                        result_lines.append(original_lines[orig_idx])
                        orig_idx += 1
                elif action == "-":
                    orig_idx += 1
                elif action == "+":
                    result_lines.append(content)

                i += 1
            continue

        i += 1

    while orig_idx < len(original_lines):
        result_lines.append(original_lines[orig_idx])
        orig_idx += 1

    return "\n".join(result_lines)

def apply_diff_file(filename, diff_text):
    with open(filename, "r", encoding="utf-8") as f:
        original_text = f.read()

    modified_text = apply_diff_text(original_text, diff_text)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(modified_text)

    return True

def apply_diff(filename: str, text: str, workspace_dir: str) -> str:
    """Apply standard unified diff to file."""
    try:
        filepath = get_safe_path(workspace_dir, filename)
        if not apply_diff_file(filepath, text):
            return "Error: unknown error. Diff not applied."
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    return "Diff applied successfully."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply standard unified diff to file.")
    parser.add_argument("filename_pos", nargs="?", help="The name of the file to apply diff to.")
    parser.add_argument("text_pos", nargs="?", help="The unified diff text content.")
    parser.add_argument("--filename", help="The name of the file to apply diff to.")
    parser.add_argument("--text", help="The unified diff text content.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    text = args.text or args.text_pos

    if not filename or text is None:
        print("Error: Both filename and diff text are required.")
        sys.exit(1)

    result = apply_diff(filename, text, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
