# Gitea Environment Wrapper (`gitea-env-wrapper.py`)

## Description
`gitea-env-wrapper.py` is a command-line utility designed to bridge environment variables between GitHub-style environments (such as GitHub Actions or similar CI/CD systems) and Gitea-specific tools. Its primary function is to read the standard `GITHUB_REPOSITORY` environment variable (which is formatted as `owner/repo`), parse it, and inject `GITEA_MAIN_REPO_OWNER` and `GITEA_MAIN_REPO_NAME` into the environment of a subprocess. 

Before executing the wrapped command, the script acts as a strict validation gate, ensuring that all necessary Gitea and Codify-related environment variables are present in the system. It then executes the provided command transparently, passing along the modified environment, standard output, errors, and propagating the exact final exit code.

## Command Line Options

```text
usage: python gitea-env-wrapper.py <command> [args...]
```

### Arguments Detail:
*   `<command>` *(Required)*: The executable command, binary, or script you wish to run within the prepared Gitea environment.
*   `[args...]` *(Optional)*: Any arguments or flags that should be passed directly to the `<command>`.

### Required Environment Variables:
The script will fail and exit with an error before running the command if any of the following environment variables are missing or empty:
*   `GITHUB_REPOSITORY`: The repository slug, which must be strictly in the format `owner/repo`.
*   `GITEA_TOKEN`: Authentication token required for Gitea API access.
*   `CODIFY_GITEA_INSTANCE`: The URL or identifier of the target Gitea instance.
*   `CODIFY_REPO_OWNER`: The owner name utilized by the Codify toolset.
*   `CODIFY_WORK_PATH`: The designated working directory path for Codify operations.

## Examples

### 1. Running a Simple Shell Command
You can use the wrapper to run a tool that requires the injected variables. *(Note: We use `printenv` or pass a script here, as using `echo $VAR` would be evaluated by the parent shell before the Python script runs.)*
```bash
export GITHUB_REPOSITORY="g-stefan/test-01"
export GITEA_TOKEN="your_token_here"
export CODIFY_GITEA_INSTANCE="https://gitea.example.com"
export CODIFY_REPO_OWNER="g-stefan"
export CODIFY_WORK_PATH="/tmp/work"

python gitea-env-wrapper.py printenv GITEA_MAIN_REPO_NAME
```

### 2. Wrapping Another Python Script
If you have a Python script that relies on `GITEA_MAIN_REPO_OWNER` and `GITEA_MAIN_REPO_NAME`, you can wrap it effortlessly while passing arguments:
```bash
python gitea-env-wrapper.py python my_gitea_script.py --verbose
```

### 3. Executing a Shell Script
You can safely wrap the execution of a bash/shell deployment script:
```bash
python gitea-env-wrapper.py ./deploy_to_gitea.sh
```

## Safety and Error Handling
*   **Strict Environment Validation**: Instantly halts execution with descriptive standard error (`stderr`) messages if any of the mandatory environment variables are missing, preventing cascading failures in the underlying commands.
*   **Format Validation**: Verifies that `GITHUB_REPOSITORY` correctly contains exactly one forward slash (`owner/repo`), preventing malformed variable injection.
*   **Transparent Execution**: The script safely launches the subprocess without invoking a shell (`shell=False`), mitigating shell injection vulnerabilities.
*   **Exit Code Propagation**: Gracefully catches interrupt signals (Ctrl+C) and guarantees that the wrapper's exit code perfectly matches the exit code of the subprocess, making it reliable for CI/CD pipelines.
