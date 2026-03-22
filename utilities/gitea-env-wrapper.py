# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

"""
GitHub to Gitea Environment Variable Wrapper CLI

This script reads the 'GITHUB_REPOSITORY' environment variable (e.g., "owner/repo"),
splits it, and sets 'GITEA_MAIN_REPO_OWNER' and 'GITEA_MAIN_REPO_NAME' for a 
subprocess command.

Usage:
    python gitea_env_wrapper.py <command> [args...]

Example:
    export GITHUB_REPOSITORY="g-stefan/test-01"
    python gitea_env_wrapper.py echo "Owner: $GITEA_MAIN_REPO_OWNER, Repo: $GITEA_MAIN_REPO_NAME"
    # Or to run a shell script:
    python gitea_env_wrapper.py ./my_script.sh
"""

import os
import sys
import subprocess

def main():
    # Force UTF-8 encoding for standard output and error to prevent UnicodeEncodeError on Windows/legacy terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        
    # 0. Check for required GITEA_TOKEN
    gitea_token = os.environ.get("GITEA_TOKEN")
    if not gitea_token:
        print("Error: GITEA_TOKEN environment variable is required but missing or empty.", file=sys.stderr)
        sys.exit(1)

    # 0.1 Check for required CODIFY_GITEA_INSTANCE
    gitea_token = os.environ.get("CODIFY_GITEA_INSTANCE")
    if not gitea_token:
        print("Error: CODIFY_GITEA_INSTANCE environment variable is required but missing or empty.", file=sys.stderr)
        sys.exit(1)

    # 0.2 Check for required CODIFY_REPO_OWNER
    gitea_token = os.environ.get("CODIFY_REPO_OWNER")
    if not gitea_token:
        print("Error: CODIFY_REPO_OWNER environment variable is required but missing or empty.", file=sys.stderr)
        sys.exit(1)

    # 0.3 Check for required CODIFY_WORK_PATH
    gitea_token = os.environ.get("CODIFY_WORK_PATH")
    if not gitea_token:
        print("Error: CODIFY_WORK_PATH environment variable is required but missing or empty.", file=sys.stderr)
        sys.exit(1)    

    # 1. Read the GITHUB_REPOSITORY environment variable
    github_repo = os.environ.get("GITHUB_REPOSITORY")

    if not github_repo:
        print("Error: GITHUB_REPOSITORY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # 2. Parse the value (split by '/')
    parts = github_repo.split('/')
    if len(parts) != 2:
        print(f"Error: Invalid GITHUB_REPOSITORY format. Expected 'owner/repo', got '{github_repo}'.", file=sys.stderr)
        sys.exit(1)

    owner, repo_name = parts

    # 3. Create a copy of the current environment and add the new variables
    # We copy the environment so we don't pollute the parent process (though in Python it wouldn't anyway),
    # but more importantly, so we pass all existing env vars PLUS the new ones to the subprocess.
    env = os.environ.copy()
    env["GITEA_MAIN_REPO_OWNER"] = owner
    env["GITEA_MAIN_REPO_NAME"] = repo_name

    # 4. Get the command to execute from the CLI arguments
    # sys.argv[0] is the name of this python script
    # sys.argv[1:] is the command and arguments we want to run
    command = sys.argv[1:]
    
    if not command:
        print("Error: No command provided to execute.", file=sys.stderr)
        print("Usage: python gitea_env_wrapper.py <command> [args...]", file=sys.stderr)
        sys.exit(1)

    # 5. Execute the subprocess
    try:
        # Run the command with the modified environment
        # Setting shell=False is safer, it directly executes the command arguments
        result = subprocess.run(command, env=env)
        
        # Exit this wrapper script with the exact same return code as the subprocess
        sys.exit(result.returncode)
        
    except FileNotFoundError:
        print(f"Error: Command not found: {command[0]}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        # Gracefully handle the user pressing Ctrl+C while the subprocess is running
        sys.exit(130)
    except Exception as e:
        print(f"Error executing subprocess: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()