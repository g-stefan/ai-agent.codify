#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import re
import argparse

def list_directory(workspace_dir: str, hide_dot_dirs: bool):
    """List files in the workspace."""
    try:
        myPath = workspace_dir
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"Directory '{workspace_dir}' does not exist.")

        myFiles = []
        for dirpath, dirnames, filenames in os.walk(myPath):
            if hide_dot_dirs:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for f in filenames:
                myFiles.append(os.path.join(dirpath, f))

        retV = []
        for line in myFiles:
            lineX = re.sub(r"[\\]", "/", line)
            retV.append(lineX[len(myPath) + 1 :])
    except FileNotFoundError as e:
        return [f"Error: {str(e)}"]
    except PermissionError as e:
        return [f"Error: Permission denied. {str(e)}"]
    except Exception as e:
        return [f"Error: An unexpected system error occurred. {str(e)}"]
    return retV

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lists the files and subdirectories in the workspace.")
    parser.add_argument("workspace_dir_pos", nargs="?", help="Optional workspace directory.")
    parser.add_argument("--workspace-dir", help="Workspace directory.")
    parser.add_argument("--hide-dot-dirs", dest="hide_dot_dirs", action="store_true", help="Hide files/dirs starting with dot.")
    parser.add_argument("--no-hide-dot-dirs", dest="hide_dot_dirs", action="store_false", help="Show files/dirs starting with dot.")
    
    env_hide = os.environ.get("HIDE_DOT_DIRS", "true").lower() in ("true", "1", "yes")
    parser.set_defaults(hide_dot_dirs=env_hide)
    
    args = parser.parse_args()

    workspace_dir = args.workspace_dir or args.workspace_dir_pos or os.environ.get("WORKSPACE_DIR", "Workspace")

    files = list_directory(workspace_dir, args.hide_dot_dirs)
    for f in files:
        print(f)
    if files and files[0].startswith("Error:"):
        sys.exit(1)
