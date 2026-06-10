#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import datetime
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

def metadata(filename: str, workspace_dir: str) -> dict:
    """Get metadata for a file."""
    try:
        filepath = get_safe_path(workspace_dir, filename)
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get metadata for a file.")
    parser.add_argument("filename_pos", nargs="?", help="The name of the file.")
    parser.add_argument("--filename", help="The name of the file.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    if not filename:
        print(json.dumps({"error": "Filename is required."}))
        sys.exit(1)

    result = metadata(filename, args.workspace_dir)
    print(json.dumps(result, indent=2))
    if "error" in result:
        sys.exit(1)
