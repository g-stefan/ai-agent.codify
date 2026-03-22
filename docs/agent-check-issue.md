# Agent Check Issue (`agent-check-issue.py`)

## Description
The `agent-check-issue.py` script is a safeguard utility designed to prevent redundant operations on a given Gitea issue. It reads a local JSON file containing the issue's data and inspects its comment history. 

Specifically, it checks the **most recent comment** on the issue. If the author of that latest comment matches the designated worker's username (the agent or bot account), the script concludes that the work has already been submitted and is currently awaiting review or approval. In this scenario, it aborts further execution, outputs an error message (`Error: Work already done! Waiting for approval.`), and exits with a status code of `1`.

## Configuration Options
This script does not rely on traditional command-line arguments (e.g., `--user` or `-f`). Instead, it is configured exclusively through **Environment Variables**:

| Environment Variable      | Default Value | Description |
|---------------------------|---------------|-------------|
| `GITEA_WORK_REPO_OWNER`   | `"unknown"`   | The username of the automated agent, bot, or worker account. The script compares this value against the author of the last issue comment. |
| `ISSUE_FILENAME`          | `"issue.json"`| The file path to the JSON document containing the issue's details and comments array. |

## Exit Codes
* **`0` (Success)**: The last comment was not made by the worker (or there are no comments), indicating it is safe to proceed with processing the issue.
* **`1` (Error)**: Execution halted. This happens if the issue JSON file cannot be read/parsed, or if the worker account has already left the most recent comment.

## Examples

### 1. Basic Execution (Defaults)
If your issue data is located in `issue.json` in the current directory, and you are using the default worker name (`"unknown"`):
```sh
python agent-check-issue.py
```

### 2. Custom Environment Variables (Windows PowerShell)
If you need to specify a custom bot username and a specific path to your issue JSON file:
```powershell
$env:GITEA_WORK_REPO_OWNER="gitea-agent-bot"
$env:ISSUE_FILENAME="work.write\issue.json"
python agent-check-issue.py
```

### 3. Custom Environment Variables (Windows CMD)
```cmd
set GITEA_WORK_REPO_OWNER=gitea-agent-bot
set ISSUE_FILENAME=work.write\issue.json
python agent-check-issue.py
```

### 4. Custom Environment Variables (Linux / macOS / Git Bash)
You can inline the environment variables before the command:
```sh
GITEA_WORK_REPO_OWNER="gitea-agent-bot" ISSUE_FILENAME="work.write/issue.json" python agent-check-issue.py
```