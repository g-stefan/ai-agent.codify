# Agent Prepare Prompt (Expert) (`agent-prepare-prompt.expert.py`)

## Description
The `agent-prepare-prompt.expert.py` script is a utility designed to construct a comprehensive Markdown prompt for an "expert" AI agent. It achieves this by stitching together static template files and dynamic data extracted from a JSON issue document (e.g., exported from Gitea or GitHub). 

Specifically, the script concatenates the following components in order to generate the final output prompt:
1.  **Begin Template**: A predefined introductory text (e.g., role definitions, system instructions).
2.  **Issue Context**: The username of the issue author, the issue title, and the main issue body extracted from the provided JSON file.
3.  **Comments Context**: A sequential list of all comments on the issue, including the author's username and the comment body.
4.  **End Template**: A predefined concluding text (e.g., final instructions, output formatting constraints).

## Configuration Options
This script does not use traditional command-line arguments (like `-f` or `--input`). Instead, it is configured entirely through **Environment Variables**:

| Environment Variable       | Default Value     | Description |
|----------------------------|-------------------|-------------|
| `PROMPT_EXPERT_BEGIN`      | `"prompt.begin.md"`| The file path to the introductory portion of the prompt. |
| `PROMPT_EXPERT_END`        | `"prompt.end.md"`  | The file path to the concluding portion of the prompt. |
| `ISSUE_FILENAME`           | `"issue.json"`     | The file path to the JSON document containing the issue data and comments. |
| `PROMPT_EXPERT_FILENAME`   | `"prompt.md"`      | The destination file path where the fully assembled prompt will be written. |

## Exit Codes
*   **`0` (Success)**: The prompt was successfully assembled and written to the output file.
*   **`1` (Error)**: Execution halted. This occurs if any of the input files (`BEGIN`, `END`, or the `ISSUE`) cannot be read/parsed, or if the script lacks permission to write the output file.

## Examples

### 1. Basic Execution (Defaults)
If all your files (`prompt.begin.md`, `prompt.end.md`, and `issue.json`) are in the current working directory, you can simply run:
```sh
python agent-prepare-prompt.expert.py
```
This will generate a `prompt.md` file in the same directory.

### 2. Custom Environment Variables (Windows PowerShell)
If your files are located in specific subdirectories, you can map them using environment variables before running the script:
```powershell
$env:PROMPT_EXPERT_BEGIN="work.read\prompt.expert.begin.md"
$env:PROMPT_EXPERT_END="work.read\prompt.expert.end.md"
$env:ISSUE_FILENAME="work.write\issue.json"
$env:PROMPT_EXPERT_FILENAME="work.write\final_expert_prompt.md"

python agent-prepare-prompt.expert.py
```

### 3. Custom Environment Variables (Windows CMD)
```cmd
set PROMPT_EXPERT_BEGIN=work.read\prompt.expert.begin.md
set PROMPT_EXPERT_END=work.read\prompt.expert.end.md
set ISSUE_FILENAME=work.write\issue.json
set PROMPT_EXPERT_FILENAME=work.write\final_expert_prompt.md

python agent-prepare-prompt.expert.py
```

### 4. Custom Environment Variables (Linux / macOS / Git Bash)
You can define the variables inline for a single execution:
```sh
PROMPT_EXPERT_BEGIN="work.read/prompt.expert.begin.md" \
PROMPT_EXPERT_END="work.read/prompt.expert.end.md" \
ISSUE_FILENAME="work.write/issue.json" \
PROMPT_EXPERT_FILENAME="work.write/final_expert_prompt.md" \
python agent-prepare-prompt.expert.py
```