# Gitea Issues Get Utility (`gitea-issues-get.py`)

## Description
The `gitea-issues-get.py` script is a versatile Python command-line utility for interacting with the Gitea REST API to retrieve issue data. It provides several modes of operation, allowing you to fetch all issues in a repository, a specific issue by its ID, the first available open issue, or exclusively open issues assigned to a specific user.

Crucially, when fetching targeted open issues or assigned issues, the script automatically retrieves the entire **comment history** for those issues and embeds it directly into the resulting JSON payload. This provides automated agents with the full context of a problem, including the original report and any subsequent discussion.

## Command-Line Options

This script utilizes `argparse` and requires explicit command-line flags for its configuration. 

### Required Arguments
| Argument | Description |
| :--- | :--- |
| `--url` | The base URL of the Gitea server (e.g., `https://gitea.example.com`). |
| `--token` | Your Gitea personal access token for API authentication. |
| `--owner` | The username or organization that owns the repository. |
| `--repo` | The name of the target repository. |

### Optional / Mode Arguments
| Argument | Type | Description |
| :--- | :--- | :--- |
| `--issue` | *Integer* | Fetches a single specific issue by its index/number. |
| `--assignee` | *String* | Fetches only open issues that are currently assigned to this specific username. |
| `--first-open` | *Flag* | Fetches the single oldest open issue. If combined with `--assignee`, it fetches the first open issue assigned to that user. |
| `--out` | *String* | Specifies the output JSON filename. If omitted, the script generates a dynamic filename based on the repository, issue number, or assignee. |
| `--error-on-no-issue` | *Flag* | If set, the script will exit with error code `1` if no matching issues are found. Useful for breaking CI/CD pipelines or agent loops when there is no work to do. |
| `-h`, `--help`| *Flag* | Shows the help message and exits. |

## Prerequisites
This script requires the `requests` library:
```sh
pip install requests
```

## Exit Codes
*   **`0` (Success)**: Issues were successfully fetched and saved to the JSON file. It also returns `0` if no issues were found *unless* the `--error-on-no-issue` flag is set.
*   **`1` (Error)**: An error occurred during HTTP requests (e.g., 404 Not Found, 401 Unauthorized, network errors), or no issues were found while the `--error-on-no-issue` flag was active.

## Examples

### 1. Fetch the First Open Issue Assigned to a Bot
This is the most common use-case for automated workers. It finds the first open issue assigned to `ai-agent-bot` and saves it to `issue.json`. If no issues exist, it fails the script (`--error-on-no-issue`).
```sh
python gitea-issues-get.py \
  --url https://git.example.com \
  --token my_secret_token \
  --owner core-team \
  --repo agent-tools \
  --assignee ai-agent-bot \
  --first-open \
  --error-on-no-issue \
  --out issue.json
```

### 2. Fetch a Specific Issue by ID
Download issue #42 from the repository and save it to `bug_42.json`:
```sh
python gitea-issues-get.py \
  --url https://git.example.com \
  --token my_secret_token \
  --owner core-team \
  --repo agent-tools \
  --issue 42 \
  --out bug_42.json
```

### 3. Fetch All Issues in a Repository
Download the entire issue tracker history (open and closed) to the default dynamic filename (`agent-tools_all_issues.json`):
```sh
python gitea-issues-get.py \
  --url https://git.example.com \
  --token my_secret_token \
  --owner core-team \
  --repo agent-tools
```