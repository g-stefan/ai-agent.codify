#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import base64
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

def read(filename: str, workspace_dir: str):
    """Read image file contents."""
    try:
        filepath = get_safe_path(workspace_dir, filename)

        ext = os.path.splitext(filepath)[1].lower()
        is_image = ext in [".png", ".jpeg", ".jpg"]
        if not is_image:
            return f"Error: It's a text file."

        imageFormat = "jpeg" if ext in [".jpeg", ".jpg"] else "png"
        with open(filepath, "rb") as f:
            data = f.read()
            b64_data = base64.b64encode(data).decode("utf-8")
            return {
                "type": "image",
                "data": b64_data,
                "mimeType": f"image/{imageFormat.lower()}",
            }
        
    except FileNotFoundError:
        return f"Error: File not found. The path '{filename}' does not exist."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read image file contents.")
    parser.add_argument("filename_pos", nargs="?", help="The name of the file to read.")
    parser.add_argument("--filename", help="The name of the file to read.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    if not filename:
        print("Error: Filename is required.")
        sys.exit(1)

    result = read(filename, args.workspace_dir)
    if isinstance(result, dict):
        print(json.dumps(result, indent=2))
    else:
        print(result, end="")
        if result.startswith("Error:"):
            sys.exit(1)
