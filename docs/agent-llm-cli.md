# Agent LLM CLI (`agent-llm-cli.py`)

## Description

`agent-llm-cli.py` is a robust, asynchronous command-line interface (CLI) client designed to interact with OpenAI-compatible LLM endpoints (specifically tailored for `llama.cpp` servers). It acts as an advanced bridge for multimodal AI inference, offering streaming responses, token usage tracking, and built-in integration with the **Model Context Protocol (MCP)**.

The script supports a rich set of input modalities. Users can provide text prompts directly or via files, extract text from PDFs, and attach images (which are automatically base64-encoded). Furthermore, its standout feature is the ability to connect to external MCP servers (via standard I/O, SSE, or Streamable HTTP). This enables the LLM to autonomously discover and execute local or remote tools in real-time, feeding the tool execution results back into the context for continuous conversation.

Additional features include chat session management (for continuous conversations), UI spinners for visual feedback during generation, system prompt injection, and comprehensive debug logging.

---

## Command Line Options

The script is highly configurable via command-line arguments:

### Input Modalities
| Option | Description |
| :--- | :--- |
| `input` (positional) | Path to a text file containing the prompt, or the direct prompt string itself. |
| `-p`, `--prompt` | Pass a direct string on the command line to use as the prompt. |
| `--system` | Path to a markdown text file containing the system message/instructions. |
| `--images` | Path(s) to image files (e.g., `.png`, `.jpg`) to include in the prompt. |
| `--pdfs` | Path(s) to PDF files to automatically extract text from and include in the prompt. |
| `--assets` | Path(s) to folders containing images and PDF files to automatically detect and include. |

### Session & State Management
| Option | Description |
| :--- | :--- |
| `--session` | Path to a JSON file to save/load the chat history for continuous conversations. |
| `--usage-file` | Path to a JSON file to save and load lifetime token usage tracking. |
| `--tool-session` | Path to a JSON file to log the tool descriptions/schemas loaded into the model. |

### MCP (Model Context Protocol) Config
| Option | Description |
| :--- | :--- |
| `--mcp` | Commands to start MCP servers (e.g., `npx -y ...`) or HTTP URLs (SSE/Streamable HTTP). Can be specified multiple times for multiple servers. |
| `--mcp-api-key` | API key for the preceding `--mcp` server argument. |
| `--mcp-env-base` | Prefix for environment variables to pass to the preceding MCP server in stdio mode (e.g., `FOO` maps `FOO_API_KEY` to `API_KEY`). |

### LLM Server & Execution Parameters
| Option | Description |
| :--- | :--- |
| `--url` | URL of the LLM server Chat API endpoint (default: `http://127.0.0.1:8080/v1/chat/completions`). |
| `--api-key` | API key for the LLM server (can also use `API_KEY` env var). |
| `--model` | Model name to request (default: `default`). |
| `--temp` | Generation temperature (default: `0.7`). |
| `--max-tokens` | Maximum tokens to predict. `-1` means infinity (default: `-1`). |
| `--context-limit` | Maximum context size (e.g., `8192`) used to display context usage percentage. |

### Networking & Debugging
| Option | Description |
| :--- | :--- |
| `--timeout` | Timeout in seconds for individual HTTP requests (default: `360`). |
| `--prompt-timeout` | Maximum overall time allowed for the entire interaction (generation + tool execution) (default: `360`). |
| `--insecure` | Disable SSL certificate verification (useful for local self-signed endpoints). |
| `--debug` | Path to a JSONL file to log API requests and responses for debugging. |
| `--no-spinner` | Disable the thinking and working UI spinner animation in the console. |

---

## Usage Examples

### 1. Basic Text Prompt
Send a simple text prompt to a locally running llama.cpp server.
```bash
python agent-llm-cli.py -p "Explain the theory of relativity in simple terms."
```

### 2. Multimodal Input (Text + Images + PDFs)
Analyze a dataset utilizing an image chart, a PDF manual, and a specific text instruction.
```bash
python agent-llm-cli.py "Please summarize the manual and describe the chart." \
  --images chart.png \
  --pdfs manual.pdf
```

### 3. Using MCP Servers (Tool Execution)
Connect the LLM to a local filesystem tool using the Model Context Protocol, allowing the AI to list and read your files.
```bash
python agent-llm-cli.py -p "What files are in my current directory?" \
  --mcp "npx -y @modelcontextprotocol/server-filesystem ./"
```

### 4. Continuous Chat Session
Save the context of a conversation to a file so that you can continue it in subsequent commands.
```bash
# First interaction
python agent-llm-cli.py -p "My name is Alice." --session chat_history.json

# Second interaction (the model will remember the name)
python agent-llm-cli.py -p "What is my name?" --session chat_history.json
```

### 5. Advanced Configuration (Remote Server, System Prompt, Usage Tracking)
Connect to an external API (like Gemini or OpenAI compatible endpoints), using a system prompt, setting a temperature, and tracking token usage over time.
```bash
python agent-llm-cli.py "Write a python script for a web server." \
  --url "https://api.example.com/v1/chat/completions" \
  --api-key "your_api_key_here" \
  --model "example-model-v2" \
  --temp 0.2 \
  --system system_instructions.md \
  --usage-file token_usage.json
```

---

## Prerequisites
To use all features of this script, ensure the following Python packages are installed:
- `mcp` (Required for `--mcp` tool execution features)
- `pypdf` (Required for `--pdfs` text extraction features)

You can install them via pip:
```bash
pip install mcp pypdf
```