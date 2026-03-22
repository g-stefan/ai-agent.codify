# Agent Run (`agent-run.py`)

## Description
The `agent-run.py` script is a powerful, asynchronous task runner that executes a sequence of system commands defined in a JSON configuration file. It provides advanced orchestration features tailored for automated agents, including real-time output streaming, environment variable expansion, timeouts, and execution logging. 

One of its most advanced features is the ability to handle **dynamic commands**—where the standard output of one command can yield a new JSON array of commands that are dynamically injected into the current execution queue. It also supports robust failure recovery, allowing an interrupted or failed sequence to be resumed from the exact point of failure using an execution log.

## Command-Line Options

The script uses standard command-line flags to control its behavior:

| Argument | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config` | *Required* | Path to the JSON configuration file containing the array of commands to execute. |
| `-l`, `--log` | *Optional* | Path to an output JSONL (JSON Lines) file where execution results (stdout, stderr, return codes) will be logged. |
| `-r`, `--retry` | *Flag* | If set, the script reads the provided log file and resumes execution starting from the last failed command (identified by its `tag`). Requires `--log`. |
| `-h`, `--help` | *Flag* | Shows the help message and exits. |

## JSON Configuration Format

The input JSON file (`--config`) must contain a root array of command objects. Each object supports the following properties:

*   **`command`** *(String or Array)*: The command to execute. Supports environment variable expansion (e.g., `echo $MY_VAR`).
*   **`tag`** *(String, Optional)*: A unique identifier for the command. This is crucial for the `--retry` feature to locate where to resume.
*   **`required`** *(Boolean, Default: `true`)*: If `true`, a non-zero exit code from this command will halt the entire script. If `false`, execution continues to the next command.
*   **`timeout`** *(Number, Optional)*: Maximum execution time in seconds before the process is killed (returns exit code 124).
*   **`env`** *(Object, Optional)*: Key-value pairs of environment variables to inject specifically for this command.
*   **`error-exit-ok`** *(Boolean, Default: `false`)*: If the command fails, halt the sequence but exit the `agent-run.py` script gracefully with a success code (`0`) instead of an error code.
*   **`dynamic_commands`** *(Boolean, Default: `false`)*: If `true` and the command succeeds, its `stdout` is parsed as a JSON array of new command objects, which are then injected immediately after the current command in the queue.

## Examples

### 1. Basic Execution
Run a sequence of commands defined in `pipeline.json`:
```sh
python agent-run.py --config pipeline.json
```

### 2. Execution with Logging
Run the commands and maintain a detailed JSONL log of all outputs and return codes:
```sh
python agent-run.py -c pipeline.json --log execution.log
```

### 3. Resuming from a Failure
If a previous run failed halfway through, use the retry flag to resume from the tagged command that failed:
```sh
python agent-run.py -c pipeline.json -l execution.log --retry
```

### Example `pipeline.json`
```json
[
    {
        "tag": "setup-env",
        "command": "mkdir -p build",
        "required": true
    },
    {
        "tag": "fetch-data",
        "command": "curl -o build/data.json https://api.example.com/data",
        "timeout": 30,
        "env": {
            "AUTHORIZATION": "Bearer my-token"
        }
    },
    {
        "tag": "generate-dynamic-tasks",
        "command": "python generate_tasks.py build/data.json",
        "dynamic_commands": true
    },
    {
        "tag": "cleanup",
        "command": "rm -rf temp_files/",
        "required": false
    }
]
```