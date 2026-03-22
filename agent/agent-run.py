# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import asyncio
import os
import sys
from datetime import datetime, timezone

def expand_args(args, custom_env):
    """
    Expands environment variables in a list of arguments or a string 
    using a custom environment dictionary.
    """
    original_env = os.environ.copy()
    try:
        # Temporarily update os.environ so expandvars uses the new variables
        os.environ.update(custom_env)
        if isinstance(args, list):
            return [os.path.expandvars(str(arg)) for arg in args]
        elif isinstance(args, str):
            return os.path.expandvars(args)
        return args
    finally:
        # Always restore the original environment
        os.environ.clear()
        os.environ.update(original_env)

async def read_stream(stream, out_stream, color_code=None):
    """
    Asynchronously reads from a stream chunk by chunk, writes it to the output stream
    (with optional ANSI color), and returns the accumulated string.
    """
    chunks = []
    while True:
        # Read up to 1024 bytes at a time to stream in real-time
        chunk = await stream.read(1024)
        if not chunk:
            break
        text = chunk.decode('utf-8', errors='replace')
        chunks.append(text)
        
        # Write to console in real-time
        if color_code:
            out_stream.write(f"{color_code}{text}\033[0m")
        else:
            out_stream.write(text)
        out_stream.flush()
        
    return "".join(chunks)

async def main_async():
    parser = argparse.ArgumentParser(
        description="Run a sequence of commands defined in a JSON file."
    )
    parser.add_argument('-c', '--config', required=True, 
                        help="Path to the JSON configuration file")
    parser.add_argument('-l', '--log', 
                        help="Path to the output JSONL log file")
    parser.add_argument('-r', '--retry', action='store_true',
                        help="Retry from the last failed command in the log (requires --log)")
    
    args = parser.parse_args()

    if args.retry and not args.log:
        parser.error("--retry requires --log to be specified.")

    # Load JSON Configuration
    try:
        with open(args.config, 'r') as f:
            commands = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(commands, list):
        print("Error: JSON root must be an array of command objects.", file=sys.stderr)
        sys.exit(1)

    # Determine starting index for retry
    start_index = 0
    if args.retry and args.log and os.path.exists(args.log):
        last_entry = None
        try:
            with open(args.log, 'r') as lf:
                for line in lf:
                    if line.strip():
                        last_entry = json.loads(line)
        except Exception as e:
            print(f"Warning: Could not read log file for retry: {e}", file=sys.stderr)
        
        if last_entry and last_entry.get("return_code", 0) != 0:
            failed_tag = last_entry.get("tag")
            if failed_tag:
                for idx, cmd in enumerate(commands):
                    if cmd.get("tag") == failed_tag:
                        start_index = idx
                        print(f"Retrying from command with tag '{failed_tag}' at index {idx}.", file=sys.stderr)
                        break
                else:
                    print(f"Warning: Failed tag '{failed_tag}' not found in config. Starting from beginning.", file=sys.stderr)
            else:
                print("Warning: Last failed command in log has no tag. Starting from beginning.", file=sys.stderr)

    # Process each command
    i = start_index
    while i < len(commands):
        cmd_obj = commands[i]
        raw_cmd = cmd_obj.get("command")
        tag = cmd_obj.get("tag")
        if not raw_cmd:
            print(f"Warning: Command object at index {i} is missing 'command'. Skipping.", file=sys.stderr)
            i += 1
            continue

        dynamic_commands = cmd_obj.get("dynamic_commands", False)
        required = cmd_obj.get("required", True)
        timeout_sec = cmd_obj.get("timeout", None)
        env_overrides = cmd_obj.get("env", {})
        error_exit_ok = cmd_obj.get("error-exit-ok", False)

        # Prepare environment copy for this specific command execution
        cmd_env = os.environ.copy()
        
        # Sequentially process environment overrides to allow secondary resolution
        # E.g., "MY_VAR": "val1", "MY_VAR2": "$MY_VAR/val2"
        for k, v in env_overrides.items():
            # Expand variables within the value itself using the current state of cmd_env
            expanded_val = expand_args(str(v), cmd_env)
            # Update the environment immediately so subsequent keys can use it
            cmd_env[str(k)] = expanded_val

        # Expand environment variables within the command arguments
        expanded_cmd = expand_args(raw_cmd, cmd_env)
        
        use_shell = isinstance(expanded_cmd, str)

        try:
            tag_info = f" [Tag: {tag}]" if tag else ""
            print(f"Executing{tag_info}: {raw_cmd}")

            # Start subprocess asynchronously
            if use_shell:
                process = await asyncio.create_subprocess_shell(
                    expanded_cmd,
                    env=cmd_env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *expanded_cmd,
                    env=cmd_env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

            # Create tasks to read stdout and stderr continuously
            stdout_task = asyncio.create_task(read_stream(process.stdout, sys.stdout))
            stderr_task = asyncio.create_task(read_stream(process.stderr, sys.stderr, color_code="\033[91m"))

            timed_out = False
            
            # Wait for process to complete, with optional timeout
            try:
                if timeout_sec is not None:
                    await asyncio.wait_for(process.wait(), timeout=float(timeout_sec))
                else:
                    await process.wait()
            except asyncio.TimeoutError:
                timed_out = True
                try:
                    process.kill()
                except OSError:
                    pass  # Process might have just finished
                await process.wait()  # Ensure cleanup

            # Wait for output streams to finish reading
            stdout_text = await stdout_task
            stderr_text = await stderr_task
            
            return_code = process.returncode

            # Handle timeout scenario
            if timed_out:
                timeout_msg = f"timeout after {timeout_sec} seconds"
                print(f"\033[91m{timeout_msg}\033[0m", file=sys.stderr)
                
                # Append the timeout text to stderr so it's captured in the log
                if stderr_text and not stderr_text.endswith('\n'):
                    stderr_text += '\n'
                stderr_text += timeout_msg
                
                # Assign standard timeout error code
                return_code = 124

            # Handle JSONL Logging
            if args.log:
                log_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tag": tag,
                    "command": raw_cmd,
                    "required": required,
                    "return_code": return_code,
                    "stdout": stdout_text,
                    "stderr": stderr_text
                }
                try:
                    with open(args.log, 'a') as lf:
                        lf.write(json.dumps(log_entry) + '\n')
                except IOError as e:
                    print(f"Warning: Failed to write to log file: {e}", file=sys.stderr)

            # Notify failure in red for all commands, but only exit if required
            if return_code != 0:
                if not timed_out:
                    print(f"\033[91mError: Command '{raw_cmd}'{tag_info} failed with return code {return_code}.\033[0m", file=sys.stderr)
                if required:
                    if error_exit_ok:
                        print("Exiting execution successfully (code 0) due to 'error-exit-ok': true.", file=sys.stderr)
                        sys.exit(0)
                    sys.exit(return_code)

            # Handle injecting dynamic commands into the sequence
            if dynamic_commands and return_code == 0:
                try:
                    new_cmds = json.loads(stdout_text)
                    if isinstance(new_cmds, list):
                        # Inject right after the current command index
                        commands[i+1:i+1] = new_cmds
                    else:
                        print(f"Warning: Expected JSON array for dynamic commands from '{raw_cmd}', got other type.", file=sys.stderr)
                except json.JSONDecodeError as e:
                    print(f"Error parsing dynamic commands JSON from '{raw_cmd}': {e}", file=sys.stderr)
                    if required:
                        if error_exit_ok:
                            print("Exiting execution successfully (code 0) due to 'error-exit-ok': true.", file=sys.stderr)
                            sys.exit(0)
                        sys.exit(1)

        except Exception as e:
            print(f"Error executing command '{raw_cmd}': {e}", file=sys.stderr)
            if required:
                if error_exit_ok:
                    print("Exiting execution successfully (code 0) due to 'error-exit-ok': true.", file=sys.stderr)
                    sys.exit(0)
                sys.exit(1)
        
        i += 1

if __name__ == "__main__":
    # Safely configure standard output and error to prevent UnicodeEncodeErrors
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.", file=sys.stderr)
        sys.exit(130)