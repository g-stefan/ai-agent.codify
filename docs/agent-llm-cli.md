# Agent LLM CLI (`agent-llm-cli.py`)

## Description
The `agent-llm-cli.py` script is a powerful, multimodal command-line interface for interacting with an LLM (Large Language Model) server compatible with the OpenAI Chat Completions API format (such as `llama.cpp` or a proxy for Gemini). 

It features built-in support for processing text prompts, extracting text from PDFs, encoding images as Base64, and managing complex chat sessions. Crucially, it integrates fully with the **Model Context Protocol (MCP)**, allowing the LLM to dynamically discover and execute external tools and fetch data directly from connected MCP servers (via Stdio, SSE, or Streamable HTTP). It also provides token usage tracking, connection resilience, and robust error handling.

## Command-Line Options

The CLI accepts various flags to customize the prompt, connection, multimodal inputs, and context tracking:

### Input Sources
You must provide at least one of these input sources for the tool to function:
*   `input` (positional): Path to a text file containing the prompt, or the direct prompt string itself.
*   `-p`, `--prompt <text>`: Pass a direct string on the command line to use as the prompt.
*   `--system <path>`: Path to a Markdown/text file containing the system message.
*   `--images <path> [path...]`: Path(s) to image files to include in the prompt (encoded automatically).
*   `--pdfs <path> [path...]`: Path(s) to PDF files to extract text from and include in the prompt.
*   `--session <path>`: Path to a JSON file to save and load the chat history for continuous conversations.

### MCP (Model Context Protocol) Configuration
*   `--mcp <command/url>`: Commands to start MCP servers (e.g., `npx -y ...`) or HTTP URLs (`http://.../sse` or `http://.../mcp`). This argument can be specified multiple times for multiple servers.
*   `--mcp-api-key <key>`: API key for the *preceding* `--mcp` server.
*   `--mcp-env-base <prefix>`: Prefix for environment variables to pass to the preceding MCP server in stdio mode (e.g., `FOO` maps `FOO_API_KEY` to `API_KEY`).

### Server & Model Settings
*   `--url <url>`: URL of the LLM server endpoint. Default: `http://127.0.0.1:8080/v1/chat/completions`.
*   `--api-key <key>`: API key for the server. Can also be set via the `API_KEY` environment variable.
*   `--model <name>`: Model name to request. Default: `default`.
*   `--temp <float>`: Generation temperature. Default: `0.7`.
*   `--max-tokens <int>`: Maximum tokens to predict. `-1` means infinity. Default: `-1`.
*   `--insecure`: Allow insecure server connections when using SSL (disables certificate verification).
*   `--timeout <seconds>`: Timeout in seconds for HTTP stream requests. Default: `360`.
*   `--prompt-timeout <seconds>`: Maximum overall time in seconds allowed for generation, thinking, and tool execution. Returns an error if exceeded. Default: `360`.

### Tracking & Debugging
*   `--context-limit <int>`: Maximum context size (e.g., 8192) to display context usage percentages in the console.
*   `--usage-file <path>`: Path to a JSON file to save and load lifetime token usage tracking.
*   `--tool-session <path>`: Path to a JSON file to log the tool descriptions loaded into the model.
*   `--debug <path>`: Path to a JSONL file to log raw API requests and responses for debugging.
*   `--no-spinner`: Disable the "thinking" and "working" spinner animation on the console output.

## Examples

### 1. Basic Text Prompt
Ask a direct question using the `-p` argument:
```sh
python agent-llm-cli.py -p "What is the capital of France?"
```

### 2. Using Files and Context Tracking
Load a system prompt, a user prompt from a text file, and maintain the conversation history across runs:
```sh
python agent-llm-cli.py prompt.txt \
  --system system_instructions.md \
  --session chat_history.json
```

### 3. Multimodal Input (PDFs and Images)
Extract text from a PDF, encode an image, and provide a prompt asking to summarize or compare them:
```sh
python agent-llm-cli.py -p "Describe the image and summarize the PDF." \
  --images architecture_diagram.png \
  --pdfs project_specifications.pdf
```

### 4. Integrating with an MCP Server
Start a local MCP server (via `npx` stdio) and connect to a remote server simultaneously, providing an API key via environment variables mapping:
```sh
python agent-llm-cli.py -p "Check the local filesystem and fetch weather data." \
  --mcp "npx -y @modelcontextprotocol/server-filesystem /tmp" \
  --mcp "http://weather-mcp.local/sse" \
  --mcp-api-key "my-secret-key"
```

### 5. Connecting to a Remote LLM with Advanced Metrics
Query a remote Gemini/OpenAI-compatible endpoint, tracking token usage and debugging payloads:
```sh
python agent-llm-cli.py -p "Write a Python script for sorting." \
  --url "https://api.example.com/v1/chat/completions" \
  --api-key "sk-xxxxxx" \
  --model "gemini-2.5-flash" \
  --temp 0.2 \
  --context-limit 128000 \
  --usage-file metrics.json \
  --debug api_trace.jsonl
```