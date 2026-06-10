#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import shutil
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

def delete(filename: str, workspace_dir: str) -> str:
    """Delete file or directory"""        
    try:
        filepath = get_safe_path(workspace_dir, filename)
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete a file or directory.")
    parser.add_argument("filename_pos", nargs="?", help="The file or directory path to delete.")
    parser.add_argument("--filename", help="The file or directory path to delete.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    filename = args.filename or args.filename_pos
    if not filename:
        print("Error: Filename is required.")
        sys.exit(1)

    result = delete(filename, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
