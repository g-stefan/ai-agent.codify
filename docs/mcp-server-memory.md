# MCP Server - Memory (`mcp-server-memory.py`)

## Description
The `mcp-server-memory.py` script is a **Model Context Protocol (MCP)** server that provides AI agents with long-term, semantic memory capabilities. It allows an LLM to save text snippets or Q&A pairs to a local filesystem and retrieve them later based on semantic relevance using vector embeddings.

Under the hood, it:
1.  **Embeds** text using an external LLM server endpoint (e.g., `llama.cpp`).
2.  **Stores** the raw text as a file in a designated directory and inserts the embedding into a **MariaDB** database equipped with vector search capabilities.
3.  **Searches** the database using Cosine Distance (`VEC_DISTANCE_COSINE`) when asked to recall information.
4.  **Reranks** the retrieved context (optional but enabled by default) using a secondary LLM reranker endpoint to ensure the most relevant memories are presented to the AI.

The server can run in two modes: standard HTTP mode (accessible via network) or STDIO mode (where it communicates via standard input/output, which is standard for local MCP clients).

## Command-Line Options

| Argument | Type | Description |
| :--- | :--- | :--- |
| `--stdio` | *Flag* | Run the MCP server in standard input/output mode (JSON-RPC over stdio). Used when the MCP client spawns this script as a subprocess. |
| `--mcp` | *Flag* | Run the MCP server in HTTP mode (this is the default behavior if `--stdio` is omitted). |
| `--api-key` | *String* | Enforces API key authentication when running in HTTP mode. Clients must pass the key via the `X-API-Key` or `Authorization: Bearer` headers. |
| `--env-base` | *String* | A prefix applied to all environment variables. Useful for running multiple instances on the same machine without variable collision. (e.g., `--env-base AGENT1` will make the script look for `AGENT1_DB_HOST` instead of `DB_HOST`). |
| `-h`, `--help`| *Flag* | Shows the help message and exits. |

## Environment Variables Configuration

The server relies heavily on environment variables for configuration. If `--env-base` is used, prepend the base string and an underscore to these variable names.

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `48101` | The port the HTTP server binds to (when not in `--stdio` mode). |
| `DB_HOST` | `"127.0.0.1"` | Hostname of the MariaDB server. |
| `DB_PORT` | `3306` | Port of the MariaDB server. |
| `DB_USER` | `"root"` | MariaDB username. |
| `DB_PASS` | `""` | MariaDB password. |
| `DB_NAME` | `"memory_db"` | The database name. |
| `DB_TABLE` | `"embeddings"` | The table name where vector embeddings and file references are stored. |
| `DB_SEARCH_LIMIT`| `8` | Maximum number of candidate vectors retrieved from the database before reranking. |
| `LLAMA_EMBED_URL`| `"http://127.0.0.1:8080/embeddings"` | Endpoint to generate vector embeddings. |
| `LLAMA_RERANK_URL`| `"http://127.0.0.1:8080/v1/rerank"`| Endpoint to rerank retrieved documents for better relevance. |
| `ENABLE_RERANKING`| `"true"` | Set to `"false"` to skip the reranking step and just use raw vector distance. |
| `MEMORY_DIR` | `"Memory"` | The local folder where the raw `.txt` files containing the memory content are saved. |

## Exposed MCP Tools

Once an LLM connects to this MCP server, it gains access to the following tools:

1.  **`remember(info: str) -> str`**: Saves a plain text fact or block of information into the memory database.
2.  **`remember_response(question: str, response: str) -> str`**: A convenience tool that formats a question and answer pair and saves it to memory.
3.  **`recall(question: str, memories_limit: int = 4) -> str`**: Searches the database for memories semantically relevant to the `question`. Returns up to `memories_limit` formatted memory blocks, including the exact date and time they were originally created.

## Dependencies

*   Python packages: `mcp`, `fastmcp`, `uvicorn`, `starlette`
*   Database Driver: `mariadb` (Must be installed via `pip install mariadb`)
*   A running MariaDB server (compiled with Vector Search support if using `VEC_DISTANCE_COSINE`).
*   A running LLM server (like `llama-server`) exposing `/embeddings` and `/v1/rerank` endpoints.

## Examples

### 1. Running in Standard HTTP Mode
Run the server on the default port (`48101`) connected to a local MariaDB instance:
```sh
python mcp-server-memory.py
```

### 2. Running in HTTP Mode with Authentication
Require an API key for all incoming requests:
```sh
python mcp-server-memory.py --api-key "super-secret-key-123"
```

### 3. Running via STDIO (For local MCP Clients)
If you are integrating this directly into an MCP client configuration (like Claude Desktop or the Agent CLI):
```sh
python mcp-server-memory.py --stdio
```

### 4. Running with an Environment Prefix
Run the server on a custom port and database using a specific environment prefix (`MEM1`):
```sh
export MEM1_PORT=50000
export MEM1_DB_NAME="project_alpha_memory"
export MEM1_MEMORY_DIR="/data/alpha/memory"

python mcp-server-memory.py --env-base MEM1
```