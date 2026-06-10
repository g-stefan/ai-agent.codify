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

def rename(source: str, destination: str, workspace_dir: str) -> str:
    """Rename or move a file."""
    try:
        source_path = get_safe_path(workspace_dir, source)
        dest_path = get_safe_path(workspace_dir, destination)

        if not os.path.exists(source_path):
            return f"Error: The source file '{source}' does not exist."

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename or move a file.")
    parser.add_argument("source_pos", nargs="?", help="The source file path.")
    parser.add_argument("destination_pos", nargs="?", help="The destination file path.")
    parser.add_argument("--source", help="The source file path.")
    parser.add_argument("--destination", help="The destination file path.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    args = parser.parse_args()

    source = args.source or args.source_pos
    destination = args.destination or args.destination_pos

    if not source or not destination:
        print("Error: Both source and destination are required.")
        sys.exit(1)

    result = rename(source, destination, args.workspace_dir)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)
