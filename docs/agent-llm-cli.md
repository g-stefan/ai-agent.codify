# Agent LLM CLI (`agent-llm-cli.py`)

`agent-llm-cli.py` is a powerful, multimodal command-line interface designed to interact with Large Language Models (LLMs) via OpenAI-compatible Chat APIs (such as `llama.cpp` server). 

It supports streaming text generation, embedding images into prompts, maintaining conversation history across sessions, and tracking lifetime token usage. One of its standout features is the dynamic integration with **Model Context Protocol (MCP)** servers, allowing the LLM to seamlessly discover and execute external tools directly from the command line.

## Features
- **Multimodal Support:** Easily include text, single images, or entire folders of images in your prompts.
- **MCP Integration:** Connect to MCP servers via standard input/output (stdio) or HTTP (SSE/Streamable HTTP) to give your LLM access to external tools and APIs.
- **Session Management:** Save and load chat history to maintain continuous conversations.
- **Streaming Output:** Real-time text generation with a built-in thinking/working spinner.
- **Token Tracking:** Detailed usage statistics, including context limits, historical tokens, and estimated tool/prompt tokens.

## Command Line Options

### Input Sources
*Requires at least one of the following inputs:*

- `input` (Positional): Path to a text file containing the prompt, or the direct prompt string itself.
- `-p`, `--prompt`: Pass a direct string on the command line to use as the prompt.
- `--session`: Path to a JSON file to save/load the chat history for continuous conversations.
- `--images`: Path(s) to one or more image files to include in the prompt.
- `--assets`: Path(s) to folder(s) containing image files (`.png`, `.jpg`, `.jpeg`) to automatically include in the prompt.

### Context & Configuration
- `--system`: Path to a text/markdown file containing the system message (only inserted if not already present in the session).
- `--url`: URL of the Chat API endpoint (default: `http://127.0.0.1:8080/v1/chat/completions`). Note: Auto-corrects `/completion` to `/v1/chat/completions`.
- `--api-key`: API key for the LLM server. Can also be set via the `API_KEY` environment variable.
- `--model`: Model name to request from the server (default: `default`).
- `--temp`: Generation temperature (default: `0.7`).
- `--max-tokens`: Maximum tokens to predict. `-1` means infinity (default: `-1`).

### Model Context Protocol (MCP)
- `--mcp`: Command to start an MCP server (e.g., `npx -y ...`) or an HTTP URL (`http://.../sse` or `http://.../mcp`). Can be specified multiple times for multiple servers.
- `--mcp-api-key`: API key for the *preceding* MCP server specified.
- `--mcp-env-base`: Prefix for environment variables to pass to the *preceding* MCP server in stdio mode (e.g., `FOO` to map `FOO_API_KEY` to `API_KEY`).

### Tracking & Debugging
- `--context-limit`: Maximum context size (e.g., `8192`) to display usage percentage in the summary.
- `--usage-file`: Path to a JSON file to save and load lifetime token usage tracking.
- `--tool-session`: Path to a JSON file to log the tool descriptions loaded into the model.
- `--debug`: Path to a JSONL file to log raw API requests and responses for debugging.

### Network & UI
- `--insecure`: Allow insecure server connections when using SSL (disables certificate verification).
- `--timeout`: Timeout in seconds for HTTP requests (default: `360`).
- `--prompt-timeout`: Maximum overall time in seconds allowed for the generation, thinking, and tool execution (default: `360`).
- `--no-spinner`: Disable the thinking and working spinner animation on the console.

## Examples

**1. Basic Text Prompting**
```bash
python agent-llm-cli.py "What is the capital of France?"
```

**2. Using a File and System Prompt**
```bash
python agent-llm-cli.py prompt.txt --system system_instructions.md
```

**3. Multimodal Prompt (with Images)**
```bash
python agent-llm-cli.py "Describe this image in detail" --images photo.jpg graph.png
```

**4. Continuous Conversation with Session Tracking**
```bash
# Turn 1
python agent-llm-cli.py "Hello, my name is Alice." --session chat.json

# Turn 2 (The model will remember Alice)
python agent-llm-cli.py "What is my name?" --session chat.json
```

**5. Integrating with an MCP Server (Stdio)**
```bash
python agent-llm-cli.py "List the files in my current directory" \
    --mcp "npx -y @modelcontextprotocol/server-filesystem ."
```

**6. Integrating with an MCP Server (HTTP/SSE) with Authentication**
```bash
python agent-llm-cli.py "Fetch the latest weather data" \
    --mcp "http://localhost:3000/sse" \
    --mcp-api-key "your-secret-token"
```

**7. Advanced Usage: Tracking Usage, Custom URL, and High Temperature**
```bash
python agent-llm-cli.py "Write a creative sci-fi story." \
    --url "https://api.openai.com/v1/chat/completions" \
    --api-key "sk-..." \
    --model "gpt-4o" \
    --temp 0.9 \
    --usage-file metrics.json \
    --context-limit 128000
```
