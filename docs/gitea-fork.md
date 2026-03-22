# Gitea Fork Utility (`gitea-fork.py`)

## Description
The `gitea-fork.py` script is a Python utility designed to interact with the Gitea REST API. Its primary function is to programmatically fork an existing repository into the authenticated user's account or a specified organization.

This script uses only the Python standard library (`urllib.request`), meaning it does not require external dependencies like `requests`. It is built with robust error handling, providing clear output for HTTP errors, network issues, and conflicts (e.g., when a repository is already forked).

## Command-Line Options

The script accepts several positional and optional arguments to control the forking process:

| Argument | Type | Description |
| :--- | :--- | :--- |
| `url` | *Positional* | The base URL of the Gitea instance (e.g., `https://gitea.example.com`). |
| `owner` | *Positional* | The username or organization that owns the original repository. |
| `repo` | *Positional* | The name of the repository you want to fork. |
| `-t`, `--token` | *Optional* | Your Gitea API access token. If omitted, the script will attempt to read the `GITEA_TOKEN` environment variable. |
| `-o`, `--org` | *Optional* | The name of an organization to fork the repository into. If not provided, it forks to the authenticated user's personal account. |
| `--ok-if-forked-already` | *Flag* | If provided, the script will exit successfully (code `0`) even if the Gitea API returns a 409 Conflict indicating the repository is already forked. Ideal for idempotent automation scripts. |
| `-h`, `--help` | *Flag* | Shows the help message and exits. |

## Exit Codes
*   **`0` (Success)**: The repository was successfully forked, or it was already forked and the `--ok-if-forked-already` flag was used.
*   **`1` (Error)**: The script failed. This could be due to a missing API token, invalid repository/owner names (404 Not Found), authentication failure (401 Unauthorized), network issues, or a conflict (409) if the repository is already forked without the bypass flag.

## Examples

### 1. Basic Fork to Personal Account
Fork the `go-gitea/gitea` repository to your own account using a token passed via the command line:
```sh
python gitea-fork.py https://gitea.com go-gitea gitea --token my_secret_token_123
```

### 2. Using Environment Variables for the Token
To avoid hardcoding secrets in your command history, set the `GITEA_TOKEN` environment variable:

**Linux / macOS:**
```sh
export GITEA_TOKEN="my_secret_token_123"
python gitea-fork.py https://gitea.com go-gitea gitea
```

**Windows (PowerShell):**
```powershell
$env:GITEA_TOKEN="my_secret_token_123"
python gitea-fork.py https://gitea.com go-gitea gitea
```

### 3. Forking into an Organization
Fork the repository into a specific organization named `my-dev-org`:
```sh
python gitea-fork.py https://gitea.com go-gitea gitea -o my-dev-org
```

### 4. Idempotent Execution (Automation Friendly)
If you are running this in a CI/CD pipeline or an agent script where the fork might already exist, use the `--ok-if-forked-already` flag to prevent the script from failing if the fork is already present:
```sh
python gitea-fork.py https://gitea.com go-gitea gitea --ok-if-forked-already
```