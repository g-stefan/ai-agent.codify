#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import re
import fnmatch
import argparse

def grep(pattern: str, file_pattern: str, workspace_dir: str, hide_dot_dirs: bool):
    """
    Search the contents of files for a given text or regex pattern.
    Returns a list of matching lines formatted as 'relative_filepath\tline_number:\tline_content'.
    """
    try:
        myPath = workspace_dir
        if not os.path.exists(myPath):
            raise FileNotFoundError(f"Directory '{workspace_dir}' does not exist.")

        try:
            search_regex = re.compile(pattern)
            is_regex = True
        except re.error:
            is_regex = False

        retV = []
        for dirpath, dirnames, filenames in os.walk(myPath):
            if hide_dot_dirs:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for f in filenames:
                if file_pattern != "*" and not fnmatch.fnmatch(f, file_pattern):
                    continue

                full_path = os.path.join(dirpath, f)
                lineX = re.sub(r"[\\]", "/", full_path)
                rel_path = lineX[len(str(myPath)) + 1 :]

                try:
                    with open(full_path, "r", encoding="utf-8") as file:
                        for line_num, line in enumerate(file, 1):
                            match_found = False

                            if is_regex:
                                if search_regex.search(line):
                                    match_found = True
                            else:
                                if pattern in line:
                                    match_found = True

                            if match_found:
                                retV.append(f"{rel_path}\t{line_num}:\t{line.rstrip('\r\n')}")

                except UnicodeDecodeError:
                    continue
                except PermissionError:
                    continue

    except FileNotFoundError as e:
        return [f"Error: {str(e)}"]
    except PermissionError as e:
        return [f"Error: Permission denied. {str(e)}"]
    except Exception as e:
        return [f"Error: An unexpected system error occurred. {str(e)}"]

    return retV

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search the contents of files for a given text or regex pattern.")
    parser.add_argument("pattern_pos", nargs="?", help="The text or regular expression to search for.")
    parser.add_argument("file_pattern_pos", nargs="?", default="*", help="Optional glob pattern to filter which files to read.")
    parser.add_argument("--pattern", help="The text or regular expression to search for.")
    parser.add_argument("--file-pattern", help="Optional glob pattern to filter which files to read.")
    parser.add_argument("--workspace-dir", default=os.environ.get("WORKSPACE_DIR", "Workspace"), help="Workspace directory.")
    
    parser.add_argument("--hide-dot-dirs", dest="hide_dot_dirs", action="store_true", help="Hide files/dirs starting with dot.")
    parser.add_argument("--no-hide-dot-dirs", dest="hide_dot_dirs", action="store_false", help="Show files/dirs starting with dot.")
    
    env_hide = os.environ.get("HIDE_DOT_DIRS", "true").lower() in ("true", "1", "yes")
    parser.set_defaults(hide_dot_dirs=env_hide)
    
    args = parser.parse_args()

    pattern = args.pattern or args.pattern_pos
    file_pattern = args.file_pattern or args.file_pattern_pos

    if not pattern:
        print("Error: Pattern is required.")
        sys.exit(1)

    results = grep(pattern, file_pattern, args.workspace_dir, args.hide_dot_dirs)
    for line in results:
        print(line)
    if results and results[0].startswith("Error:"):
        sys.exit(1)
