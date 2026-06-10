#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import re
import fnmatch
import argparse

def search(pattern: str, workspace_dir: str, hide_dot_dirs: bool):
    """Search files by filename pattern."""
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
            rel_path = lineX[len(myPath) + 1 :]
            filename = os.path.basename(lineX)
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(filename, pattern):
                retV.append(rel_path)
    except FileNotFoundError as e:
        return [f"Error: {str(e)}"]
    except PermissionError as e:
        return [f"Error: Permission denied. {str(e)}"]
    except Exception as e:
        return [f"Error: An unexpected system error occurred. {str(e)}"]
    return retV

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search files by filename pattern.")
    parser.add_argument("pattern_pos", nargs="?", default="*", help="The filename pattern to match (glob).")
    parser.add_argument("--pattern", help="The filename pattern to match (glob).")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    
    parser.add_argument("--hide-dot-dirs", dest="hide_dot_dirs", action="store_true", help="Hide files/dirs starting with dot.")
    parser.add_argument("--no-hide-dot-dirs", dest="hide_dot_dirs", action="store_false", help="Show files/dirs starting with dot.")
    
    env_hide = os.environ.get("HIDE_DOT_DIRS", "true").lower() in ("true", "1", "yes")
    parser.set_defaults(hide_dot_dirs=env_hide)
    
    args = parser.parse_args()

    pattern = args.pattern or args.pattern_pos

    files = search(pattern, args.workspace_dir, args.hide_dot_dirs)
    for f in files:
        print(f)
    if files and files[0].startswith("Error:"):
        sys.exit(1)
