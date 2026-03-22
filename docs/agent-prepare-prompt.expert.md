# `agent-prepare-prompt.expert.py` Documentation

## Description

`agent-prepare-prompt.expert.py` is a Python utility script designed to generate an "expert prompt" markdown file by synthesizing data from a Gitea (or similar) issue JSON file with predefined text templates. 

In addition to text generation, the script parses the issue and its comments for attached files (assets). It securely downloads these assets into a designated working directory, utilizing an optional authorization token. This is particularly useful in automated AI agent workflows where an agent needs full context of an issue, including the conversation history and attached files, formatted into a single cohesive prompt.

### Key Features:
- **Prompt Generation:** Combines a prefix template (`prompt.begin.md`), the issue metadata (author, title, body, comments), and a suffix template (`prompt.end.md`) into a single output file.
- **Asset Extraction:** Automatically discovers, extracts, and downloads file attachments (assets) from both the main issue and its comment threads.
- **Secure Downloads:** Supports authenticated downloads using a `GITEA_TOKEN` to prevent 401/403 HTTP errors when fetching private assets.
- **Robust Error Handling:** Checks for missing files, handles HTTP download errors gracefully, streams large file downloads to manage memory, and exits with non-zero status codes on failure.

---

## Configuration / Command Line Options

While the script imports the `argparse` module, it **does not use standard command-line flags** (like `--file` or `-o`). Instead, its behavior is strictly configured using **Environment Variables**. 

If an environment variable is not provided, the script falls back to sensible defaults.

### Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PROMPT_EXPERT_BEGIN` | `prompt.begin.md` | Path to the markdown file containing the introductory text of the prompt. |
| `PROMPT_EXPERT_END` | `prompt.end.md` | Path to the markdown file containing the concluding text of the prompt. |
| `PROMPT_EXPERT_FILENAME` | `prompt.md` | The resulting output file path where the generated expert prompt will be saved. |
| `ISSUE_FILENAME` | `issue.json` | Path to the JSON file containing the issue and comment data (expected in an array format). |
| `WORK_WRITE` | `work.write` | The base working directory. Assets will be downloaded into a subdirectory named `assets` within this path (`WORK_WRITE/assets/`). |
| `GITEA_TOKEN` | *(None)* | The API authorization token used to authenticate asset downloads. |

---

## Usage Examples

### Example 1: Basic Execution (Using Defaults)
If your working directory already contains `prompt.begin.md`, `prompt.end.md`, and `issue.json`, you can run the script without any arguments:

```bash
python agent-prepare-prompt.expert.py
```

### Example 2: Custom File Paths
You can override the default file locations by setting environment variables before executing the script.

**Linux / macOS:**
```bash
PROMPT_EXPERT_BEGIN="templates/header.md" \
PROMPT_EXPERT_END="templates/footer.md" \
ISSUE_FILENAME="data/bug_report.json" \
PROMPT_EXPERT_FILENAME="output/final_prompt.md" \
python agent-prepare-prompt.expert.py
```

**Windows (PowerShell):**
```powershell
$env:PROMPT_EXPERT_BEGIN="templates/header.md"
$env:PROMPT_EXPERT_END="templates/footer.md"
$env:ISSUE_FILENAME="data/bug_report.json"
$env:PROMPT_EXPERT_FILENAME="output/final_prompt.md"
python agent-prepare-prompt.expert.py
```

### Example 3: Downloading Private Assets with a Token
If the issue contains assets hosted on a private Gitea instance, you must supply a token to authorize the downloads.

**Linux / macOS:**
```bash
GITEA_TOKEN="your_personal_access_token_here" python agent-prepare-prompt.expert.py
```

**Windows (PowerShell):**
```powershell
$env:GITEA_TOKEN="your_personal_access_token_here"
python agent-prepare-prompt.expert.py
```

---

## Prerequisites
- **Python 3.x**
- **`requests` library:** The script relies on the `requests` library for handling HTTP downloads. Ensure it is installed in your environment:
  ```bash
  pip install requests
  ```

## Output File Naming Strategy for Assets
When assets are downloaded, the script attempts to prevent filename collisions and ensure safety by renaming the downloaded files using their internal UUID. 

Files are saved in the `WORK_WRITE/assets/` directory using the format:
`<uuid><original_file_extension>`
*(e.g., `123e4567-e89b-12d3-a456-426614174000.png`)*
