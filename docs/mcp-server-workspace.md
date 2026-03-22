# MCP Server - Workspace (`mcp-server-workspace.py`)

## Description
The `mcp-server-workspace.py` script is a **Model Context Protocol (MCP)** server that grants AI agents safe, controlled access to a specific directory (workspace) on the local filesystem. 

By exposing essential file-system tools (read, write, list, and search), it allows an LLM to interact with local code or data. Crucially, the script implements strict path-traversal validation (`get_safe_path`) to ensure the AI cannot escape the designated workspace directory to read or modify external system files. It also filters out hidden directories (like `.git`) by default to prevent accidental corruption or unnecessary context loading.

Like the memory server, it can be run as a standalone HTTP server or as a subprocess via standard input/output (STDIO) for local client integration.

## Command-Line Options

| Argument | Type | Description |
| :--- | :--- | :--- |
| `--stdio` | *Flag* | Run the MCP server in standard input/output mode (JSON-RPC over stdio). Used when the MCP client spawns this script as a subprocess. |
| `--mcp` | *Flag* | Run the MCP server in HTTP mode (this is the default behavior if `--stdio` is omitted). |
| `--api-key` | *String* | Enforces API key authentication when running in HTTP mode. Clients must pass the key via the `X-API-Key` or `Authorization: Bearer` headers. |
| `--env-base` | *String* | A prefix applied to all environment variables. Useful for running multiple independent workspaces on the same machine without variable collision. (e.g., `--env-base PROJECT1` will make the script look for `PROJECT1_WORKSPACE_DIR`). |
| `-h`, `--help`| *Flag* | Shows the help message and exits. |

## Environment Variables Configuration

If `--env-base` is used, prepend the base string and an underscore to these variable names.

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `48102` | The port the HTTP server binds to (when not in `--stdio` mode). |
| `WORKSPACE_DIR`| `"Workspace"` | The absolute or relative path to the directory the agent is allowed to access. The script will create this directory if it doesn't exist. |
| `HIDE_DOT_DIRS`| `"true"` | If `"true"`, directories starting with a dot (e.g., `.git`, `.vscode`) will be hidden from the `list` and `search` tools. |

## Exposed MCP Tools

Once an LLM connects to this MCP server, it gains access to the following tools:

1.  **`read_file_content_from_workspace(filename: str) -> str`**: Reads and returns the content of a file within the workspace.
2.  **`write_file_content_to_workspace(filename: str, text: str) -> str`**: Writes the provided `text` to the specified `filename` in the workspace. Automatically creates parent directories if they don't exist. Overwrites existing files.
3.  **`list_files_on_workspace() -> List[str]`**: Recursively lists all files in the workspace (ignoring dot-directories if configured). Returns an array of relative file paths.
4.  **`search_files_on_workspace_by_filename(pattern: str = "*") -> List[str]`**: Recursively searches the workspace for files matching a specific glob pattern (e.g., `*.py` or `src/*`).

## Security Features
*   **Path Traversal Prevention:** Any file path passed to the read/write tools is resolved and checked against the absolute path of the `WORKSPACE_DIR`. If a tool attempts to use `../` to escape the root directory, a `PermissionError` is thrown.
*   **Hidden Directories:** By ignoring `.git` and similar directories, it protects source control internals from accidental AI modification.

## Dependencies
*   Python packages: `mcp`, `fastmcp`, `uvicorn`, `starlette`

## Examples

### 1. Running in Standard HTTP Mode
Serve the default `./Workspace` directory on port 48102:
```sh
python mcp-server-workspace.py
```

### 2. Serving a Specific Project Directory with Auth
Serve a specific codebase on a custom port and require an API key:
```sh
export WORKSPACE_DIR="/home/user/projects/frontend-app"
export PORT=55000

python mcp-server-workspace.py --api-key "my-secure-agent-key"
```

### 3. Running via STDIO
Run the workspace server for a local MCP client (like Claude Desktop) using an environment variable prefix (`AGENT_A`):
```sh
export AGENT_A_WORKSPACE_DIR="./worker_a_dir"

python mcp-server-workspace.py --stdio --env-base AGENT_A
```