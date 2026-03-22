# Git Push Utility (`git-push.py`)

## Description
`git-push.py` is a Python automation script that streamlines the process of fetching, staging, committing, and pushing changes to a Git repository. 

Rather than relying on manual user input for the commit message and repository path, the script dynamically reads its configuration from a JSON report file and environment variables. It navigates to the specified repository directory, prunes and fetches the latest remote state, stages all local changes, creates a commit using a title extracted from the JSON report, and pushes the changes to the remote branch. Finally, it restores the original working directory.

## Command Line Options

This script does **not** take standard command-line arguments (like `--help` or `--repo`). Instead, it is configured entirely through **Environment Variables** and a **JSON Configuration File**.

### Environment Variables
*   `GITEA_MAIN_REPO_NAME`: The name of the target repository folder. *(Default: `"unknown"`)*
*   `WORK_PATH`: The base directory path where the repository is located. *(Default: `"."`)*
*   `WORK_REPORT_FILENAME`: The path to the JSON file containing the work report. *(Default: `"work.json"`)*

### JSON File Requirements
The script expects the file specified by `WORK_REPORT_FILENAME` to be valid JSON. It looks for a `title` key to use as the Git commit message.
```json
{
  "title": "Fix bug in user authentication"
}
```
*If the `title` key is missing, the script defaults to the commit message: `"Work done"`.*

## Examples

### 1. Basic Usage (Default Behavior)
If you run the script without setting any environment variables, it looks for a directory named `unknown` in the current directory (`.`), reads `work.json` for the commit message, and executes the Git commands.
```bash
python git-push.py
```

### 2. Custom Repository and Path
To push changes for a specific repository located in a custom workspace, set the environment variables before execution:
```bash
# On Linux/macOS
export WORK_PATH="/home/user/workspace"
export GITEA_MAIN_REPO_NAME="my-awesome-app"
export WORK_REPORT_FILENAME="task-123-report.json"

python git-push.py
```

```powershell
# On Windows (PowerShell)
$env:WORK_PATH="C:\workspace"
$env:GITEA_MAIN_REPO_NAME="my-awesome-app"
$env:WORK_REPORT_FILENAME="task-123-report.json"

python git-push.py
```

### Execution Flow & Git Commands
The script executes the following Git commands in order:
1.  `git fetch --prune --prune-tags` (Fetches remote changes and removes deleted remote branches/tags. Errors here are ignored).
2.  `git add --all` (Stages all modified, new, and deleted files).
3.  `git commit -m "<title>"` (Commits the staged changes).
4.  `git push` (Pushes the commit to the remote repository).

## Error Handling
If any of the critical Git commands (`git add`, `git commit`, or `git push`) fail, the Python script will immediately abort execution and pass the exact non-zero exit code returned by the failing Git command back to the system. This makes it highly suitable for CI/CD pipelines.