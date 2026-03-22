# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import subprocess
import sys
import argparse

def main():
    # Set up basic argument parsing so it acts like a proper CLI.
    # We default to 'agent.json', but allow overrides if needed.
    parser = argparse.ArgumentParser(description="CLI tool to execute the agent subprocess.")
    parser.add_argument(
        '--config', 
        type=str, 
        default='agent.json', 
        help='Path to the agent configuration file (defaults to agent.json)'
    )
    args = parser.parse_args()

    # Construct the command list as recommended by the subprocess module
    command = ["python", "agent/agent-run.py", "--config", args.config]
    
    print(f"Starting subprocess: {' '.join(command)}\n" + "-"*40)

    try:
        # subprocess.run waits for the command to complete.
        # By not redirecting stdout/stderr, the output will stream directly to your terminal.
        result = subprocess.run(command)
        
        # sys.exit() with the return code ensures that if the script fails, 
        # this CLI wrapper fails with the exact same error code.
        # A return code of 0 means success, anything else is an error.
        sys.exit(result.returncode)
        
    except KeyboardInterrupt:
        # Gracefully handle the user pressing CTRL+C
        print("\nProcess interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except FileNotFoundError:
        # Handles cases where 'python' isn't in the system PATH
        print("Error: 'python' executable not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Catch-all for any other unexpected execution errors
        print(f"An unexpected error occurred while trying to run the command:\n{e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()