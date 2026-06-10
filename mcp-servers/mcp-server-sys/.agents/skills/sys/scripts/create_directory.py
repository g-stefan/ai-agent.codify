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

def mkdir(path: str, workspace_dir: str) -> str:
    """Create a new directory."""
    try:
        dirpath = get_safe_path(workspace_dir, path)
        Path(dirpath).mkdir(parents=True, exist_ok=True)
    except FileNotFoundError:
        return f"Error: The system cannot find the path specified for '{path}'."
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except Exception as e:
        return f"Error: An unexpected system error occurred. {str(e)}"
    return f"Successfully created directory '{path}'."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new directory.")
    parser.add_argument("path_pos", nargs="?", help="The path of the directory to create.")
    parser.add_argument("--path", help="The path of the directory to create.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    path = args.path or args.path_pos
    if not path:
        print("Error: Path is required.")
        sys.exit(1)

    result = mkdir(path, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
