# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import shlex
import sys
import threading
import time
import urllib.request
import ssl
import itertools
import socket
from urllib.error import URLError, HTTPError
from typing import Optional, Dict, Any, List, Tuple
from contextlib import AsyncExitStack
from datetime import datetime, timezone

def log_debug(filepath: Optional[str], log_type: str, data: Any) -> None:
    """Logs the API request or response chunk to a JSONL file."""
    if not filepath:
        return
    try:
        entry = {
            "datetime": datetime.now(timezone.utc).isoformat(),
            "type": log_type,
            "data": data
        }
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"\033[93m[!] Warning: Failed to write to debug file: {e}\033[0m", file=sys.stderr)

def encode_image(filepath: str) -> Tuple[str, str]:
    """Reads an image and returns its base64 string and mime type."""
    mime_type, _ = mimetypes.guess_type(filepath)
    if not mime_type:
        mime_type = "image/jpeg"
    with open(filepath, "rb") as f:
        # Strictly remove newlines/carriage returns to prevent data URI corruption
        b64_str = base64.b64encode(f.read()).decode('utf-8').replace('\n', '').replace('\r', '').strip()
    return b64_str, mime_type

def extract_pdf_text(filepath: str) -> str:
    """Extracts text from a PDF file using pypdf."""
    try:
        import pypdf
    except ImportError:
        print("\033[91m[!] Error: 'pypdf' library is required to read PDFs.\033[0m", file=sys.stderr)
        print("\033[93m    Install it with: pip install pypdf\033[0m", file=sys.stderr)
        sys.exit(1)
        
    try:
        text_blocks = []
        with open(filepath, "rb") as f:
            reader = pypdf.PdfReader(f)
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_blocks.append(f"--- Page {i+1} ---\n{page_text}")
        return "\n".join(text_blocks)
    except Exception as e:
        print(f"\033[91m[!] Error reading PDF '{filepath}': {e}\033[0m", file=sys.stderr)
        sys.exit(1)

def estimate_text_chars(messages: List[Dict[str, Any]]) -> int:
    """Helper to count characters in text parts of messages for rough token estimation."""
    chars = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    chars += len(item.get("text", ""))
        if "tool_calls" in m:
            chars += len(json.dumps(m["tool_calls"]))
        if "extra_content" in m:
            chars += len(json.dumps(m["extra_content"]))
    return chars

def deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Deep merges source dictionary into target. Safely concatenates strings if streamed."""
    for key, value in source.items():
        if isinstance(value, dict):
            node = target.setdefault(key, {})
            deep_merge(node, value)
        elif isinstance(value, str) and key in target and isinstance(target[key], str):
            target[key] += value
        elif isinstance(value, list) and key in target and isinstance(target[key], list):
            target[key].extend(value)
        else:
            target[key] = value

def http_stream_reader(req: urllib.request.Request, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, insecure: bool = False, timeout: int = 360):
    """Runs in a background thread to read the HTTP stream and push to an asyncio Queue."""
    try:
        ctx = None
        if insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
            for line in response:
                asyncio.run_coroutine_threadsafe(queue.put(("data", line)), loop)
        asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(queue.put(("error", e)), loop)

async def chat_loop(
    url: str, 
    messages: List[Dict[str, Any]], 
    tools: List[Dict[str, Any]],
    tool_to_session: Dict[str, Any],
    temperature: float = 0.7, 
    n_predict: int = -1,
    api_key: Optional[str] = None,
    model: str = "default",
    context_limit: Optional[int] = None,
    session_msg_count: int = 0,
    usage_tracker: Optional[Dict[str, Any]] = None,
    insecure: bool = False,
    timeout: int = 360,
    debug_file: Optional[str] = None,
    no_spinner: bool = False
) -> None:
    """
    Handles the chat loop, streaming text, detecting tool calls, executing them via MCP, and continuing.
    """
    
    print(f"\033[94m[*] Connecting to {url}...\033[0m", file=sys.stderr)
    
    if usage_tracker is None:
        usage_tracker = {}
        
    while True:
        data = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature
        }
        if n_predict > 0:
            data["max_tokens"] = n_predict
            
        if tools:
            data["tools"] = tools

        log_debug(debug_file, "request", data)

        # Use separators to minify JSON, significantly reducing payload size to prevent server-side truncation
        payload = json.dumps(data, separators=(',', ':')).encode('utf-8')
        
        # Explicitly declare Content-Length to avoid HTTP chunking issues with large payloads
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Content-Length': str(len(payload)),
            'Connection': 'keep-alive',
            'User-Agent': 'agent-llm-cli/1.0'
        }

        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        req = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
            method="POST"
        )

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        thread = threading.Thread(target=http_stream_reader, args=(req, queue, loop, insecure, timeout), daemon=True)
        thread.start()

        start_time = time.time()
        first_token_time: Optional[float] = None
        first_print_time: Optional[float] = None
        last_print_time = time.time()
        last_spinner_update = 0.0
        
        # Accumulators for streaming text, tool calls, and custom attributes like thought signatures
        current_tool_calls = {}
        current_assistant_content = ""
        current_assistant_extra = None
        finish_reason = None
        
        final_usage = None
        final_timings = None
        
        # Setup the UI thinking spinner
        spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
        spinner_active = False

        buffer = ""

        while True:
            try:
                # Wait for 0.1s slices to allow the UI spinner to update dynamically
                msg_type, content_bytes = await asyncio.wait_for(queue.get(), timeout=0.1)
                got_msg = True
            except asyncio.TimeoutError:
                got_msg = False

            current_time = time.time()
            
            # Spinner update logic
            if not no_spinner and current_time - last_spinner_update >= 0.1:
                if first_print_time is None:
                    elapsed = current_time - start_time
                    sys.stdout.write(f"\r\033[96m[{next(spinner)}] Thinking... ({elapsed:.1f}s)\033[0m\033[K")
                    sys.stdout.flush()
                    spinner_active = True
                    last_spinner_update = current_time
                elif current_time - last_print_time > 3.0:
                    if not spinner_active:
                        sys.stdout.write("\033[s")
                    elapsed = current_time - last_print_time
                    sys.stdout.write(f"\033[u\033[K \033[96m[{next(spinner)}] Working... ({elapsed:.1f}s)\033[0m")
                    sys.stdout.flush()
                    spinner_active = True
                    last_spinner_update = current_time

            if not got_msg:
                continue
            
            if msg_type == "error":
                if spinner_active:
                    if first_print_time is None:
                        sys.stdout.write("\r\033[K")
                    else:
                        sys.stdout.write("\033[u\033[K")
                    sys.stdout.flush()
                    spinner_active = False
                e = content_bytes
                if isinstance(e, HTTPError):
                    print(f"\n\033[91m[!] Server Error: {e.code} - {e.reason}\033[0m", file=sys.stderr)
                    error_body = e.read().decode('utf-8')
                    if error_body:
                        print(f"\033[91m    Details: {error_body}\033[0m", file=sys.stderr)
                        if "key 'prompt' not found" in error_body:
                            print("\033[93m    Hint: You are targeting the '/completion' endpoint, but this script requires the Chat API ('/v1/chat/completions').\033[0m", file=sys.stderr)
                elif isinstance(e, URLError):
                    print(f"\n\033[91m[!] Connection Error: {e.reason}\033[0m", file=sys.stderr)
                    if "time" in str(e.reason).lower() or isinstance(e.reason, socket.timeout):
                        print(f"\033[93m    The server took too long to respond (timeout={timeout}s). You can increase it with --timeout.\033[0m", file=sys.stderr)
                    else:
                        print("\033[93m    Make sure your llama-server is running and the URL is correct.\033[0m", file=sys.stderr)
                elif isinstance(e, TimeoutError):
                    print(f"\n\033[91m[!] Connection Timeout: The request exceeded the {timeout}s timeout.\033[0m", file=sys.stderr)
                    print(f"\033[93m    You can increase it with --timeout.\033[0m", file=sys.stderr)
                else:
                    print(f"\n\033[91m[!] Stream Error: {e}\033[0m", file=sys.stderr)
                sys.exit(1)

            if msg_type == "done":
                if spinner_active:
                    if first_print_time is None:
                        sys.stdout.write("\r\033[K")
                    else:
                        sys.stdout.write("\033[u\033[K")
                    sys.stdout.flush()
                    spinner_active = False
                break
                
            line = content_bytes.decode('utf-8').strip()
            
            if line == "data: [DONE]":
                if spinner_active:
                    if first_print_time is None:
                        sys.stdout.write("\r\033[K")
                    else:
                        sys.stdout.write("\033[u\033[K")
                    sys.stdout.flush()
                    spinner_active = False
                break
                
            if line.startswith("data: "):
                data_str = line[6:]
                buffer += data_str
                try:
                    chunk = json.loads(buffer)
                    buffer = "" # clear buffer on success
                    log_debug(debug_file, "response", chunk)
                except json.JSONDecodeError:
                    continue

                if chunk.get("usage"):
                    final_usage = chunk["usage"]
                if chunk.get("timings"):
                    final_timings = chunk["timings"]

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                # Check if there is meaningful content to display (for TTFT stats)
                has_meaningful_content = bool(
                    delta.get("content") or 
                    delta.get("reasoning_content") or 
                    delta.get("tool_calls") or 
                    delta.get("extra_content")
                )

                if has_meaningful_content and first_token_time is None:
                    first_token_time = time.time()
                    
                # Handle extra content (captures thought signatures for non-tool calls)
                if "extra_content" in delta:
                    if current_assistant_extra is None:
                        current_assistant_extra = {}
                    deep_merge(current_assistant_extra, delta["extra_content"])

                # Handle text and reasoning content printing
                reasoning = delta.get("reasoning_content", "")
                content = delta.get("content", "")
                
                just_printed = False
                
                if reasoning or content:
                    if spinner_active:
                        if first_print_time is None:
                            sys.stdout.write("\r\033[K")
                        else:
                            sys.stdout.write("\033[u\033[K")
                        sys.stdout.flush()
                        spinner_active = False
                        
                    if first_print_time is None:
                        first_print_time = time.time()
                        
                    if reasoning:
                        sys.stdout.write(f"\033[95m{reasoning}\033[0m")
                        just_printed = True
                        
                    if content:
                        current_assistant_content += content
                        
                        starts = current_assistant_content.count("<think>")
                        ends = current_assistant_content.count("</think>")
                        is_thinking = starts > ends
                        
                        display_content = content
                        if "<think>" in display_content:
                            display_content = display_content.replace("<think>", "\033[95m<think>\n")
                        
                        if "</think>" in display_content:
                            display_content = display_content.replace("</think>", "\n</think>\033[0m")
                            
                        if is_thinking:
                            if "<think>" in content:
                                sys.stdout.write(f"{display_content}\033[0m")
                            else:
                                sys.stdout.write(f"\033[95m{display_content}\033[0m")
                        else:
                            sys.stdout.write(display_content)
                            
                        just_printed = True
                        
                    if just_printed:
                        sys.stdout.flush()
                        last_print_time = time.time()

                # Handle tool calls
                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index")
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {"id": "", "name": "", "arguments": "", "extra_content": None}
                    if "id" in tc:
                        current_tool_calls[idx]["id"] += tc["id"]
                    if "function" in tc:
                        if "name" in tc["function"]:
                            current_tool_calls[idx]["name"] += tc["function"]["name"]
                        if "arguments" in tc["function"]:
                            current_tool_calls[idx]["arguments"] += tc["function"]["arguments"]
                    
                    # Capture tool-call specific extra content (thought signatures)
                    if "extra_content" in tc:
                        if current_tool_calls[idx]["extra_content"] is None:
                            current_tool_calls[idx]["extra_content"] = {}
                        deep_merge(current_tool_calls[idx]["extra_content"], tc["extra_content"])

                if choices[0].get("finish_reason") is not None:
                    finish_reason = choices[0].get("finish_reason")

        # End of stream block. Print a newline to separate streamed text from stats or tool executions.
        print("\n", file=sys.stderr)
        
        if final_usage:
            predicted_n = final_usage.get("completion_tokens", 0)
            prompt_n = final_usage.get("prompt_tokens", 0)
            total_n = final_usage.get("total_tokens", predicted_n + prompt_n)
            
            ttft = first_token_time - start_time if first_token_time else 0.0
            
            if final_timings and "predicted_per_second" in final_timings:
                speed = final_timings.get("predicted_per_second", 0.0)
            else:
                gen_time = time.time() - first_token_time if first_token_time else 0.0
                speed = (predicted_n / gen_time) if gen_time > 0.001 else 0.0

            exact_history = False
            history_est = 0
            tools_est = 0
            new_est = prompt_n

            if total_n > 0:
                # Calculate character lengths for estimation
                tools_chars = len(json.dumps(tools)) if tools else 0
                history_msgs = messages[:session_msg_count]
                current_msgs = messages[session_msg_count:]
                
                history_chars = estimate_text_chars(history_msgs) if history_msgs else 0
                current_chars = estimate_text_chars(current_msgs) if current_msgs else 0
                total_chars = history_chars + current_chars + tools_chars
                
                if "last_context_size" in usage_tracker and session_msg_count > 0:
                    # Use exact history size from the provided usage file
                    history_est = usage_tracker["last_context_size"]
                    history_est = min(history_est, prompt_n) # Cap just in case tokenization drifted slightly
                    
                    remaining_prompt = prompt_n - history_est
                    if tools_chars + current_chars > 0:
                        tools_est = int(remaining_prompt * (tools_chars / (tools_chars + current_chars)))
                    else:
                        tools_est = 0
                        
                    new_est = remaining_prompt - tools_est
                    exact_history = True
                else:
                    # Fallback to current text-length estimation method
                    if total_chars > 0:
                        history_est = int(prompt_n * (history_chars / total_chars))
                        tools_est = int(prompt_n * (tools_chars / total_chars))
                        new_est = prompt_n - history_est - tools_est
                    else:
                        history_est = 0
                        tools_est = 0
                        new_est = prompt_n
                        
                # Update usage tracking info
                usage_tracker["last_context_size"] = total_n
                usage_tracker["cumulative_prompt_tokens"] = usage_tracker.get("cumulative_prompt_tokens", 0) + prompt_n
                usage_tracker["cumulative_completion_tokens"] = usage_tracker.get("cumulative_completion_tokens", 0) + predicted_n
                usage_tracker["total_tokens_used"] = usage_tracker.get("total_tokens_used", 0) + total_n
                usage_tracker["cumulative_tools_tokens"] = usage_tracker.get("cumulative_tools_tokens", 0) + tools_est
                
                if "history" not in usage_tracker:
                    usage_tracker["history"] = []
                usage_tracker["history"].append({
                    "timestamp": time.time(),
                    "prompt_tokens": prompt_n,
                    "completion_tokens": predicted_n,
                    "total_tokens": total_n,
                    "estimated_tools_tokens": tools_est
                })

            # Only print the summary if we are NOT making a tool call (i.e. this is the final turn)
            if not current_tool_calls:
                print(f"\033[92m[+] Generation Complete!\033[0m", file=sys.stderr)
                print(f"\033[90m    - Tokens generated : {predicted_n}\033[0m", file=sys.stderr)
                
                if total_n > 0:
                    # Format the breakdown cleanly
                    hist_label = "history:" if exact_history else "history ≈"
                    new_label = "new:" if exact_history else "new ≈"
                    
                    breakdown_parts = []
                    if history_est > 0 or exact_history:
                        breakdown_parts.append(f"{hist_label} {history_est}")
                    if tools_est > 0:
                        breakdown_parts.append(f"tools ≈ {tools_est}")
                    breakdown_parts.append(f"{new_label} {new_est}")
                    
                    breakdown_str = ", ".join(breakdown_parts)

                    if context_limit and context_limit > 0:
                        pct = (total_n / context_limit) * 100
                        print(f"\033[90m    - Context usage    : {total_n} / {context_limit} tokens ({pct:.1f}%)\033[0m", file=sys.stderr)
                        print(f"\033[90m                         ({breakdown_str})\033[0m", file=sys.stderr)
                    else:
                        print(f"\033[90m    - Context usage    : {total_n} tokens ({breakdown_str})\033[0m", file=sys.stderr)
                        
                    if "total_tokens_used" in usage_tracker:
                        print(f"\033[90m    - Lifetime usage   : {usage_tracker['total_tokens_used']} tokens\033[0m", file=sys.stderr)
                        
                print(f"\033[90m    - Speed            : {speed:.2f} tokens/sec\033[0m", file=sys.stderr)
                print(f"\033[90m    - Time to 1st token: {ttft:.2f}s\033[0m", file=sys.stderr)

        # Process Tool Calls if necessary
        if finish_reason == "tool_calls" or current_tool_calls:
            assistant_msg = {"role": "assistant", "content": current_assistant_content if current_assistant_content else None, "tool_calls": []}
            
            # Embed message-level thought signatures if present
            if current_assistant_extra:
                assistant_msg["extra_content"] = current_assistant_extra
                
            for idx, tc in sorted(current_tool_calls.items()):
                tc_obj = {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                }
                # Embed tool-call-level thought signatures to satisfy strict API validation
                if tc.get("extra_content"):
                    tc_obj["extra_content"] = tc["extra_content"]
                    
                assistant_msg["tool_calls"].append(tc_obj)
            messages.append(assistant_msg)

            # Execute Tools
            for tc in assistant_msg["tool_calls"]:
                name = tc["function"]["name"]
                args_str = tc["function"]["arguments"]
                tool_call_id = tc["id"]
                
                display_args = args_str if len(args_str) <= 60 else args_str[:57] + "..."
                print(f"\033[93m[*] Model executing tool: {name}({display_args})\033[0m", file=sys.stderr)
                
                try:
                    args_dict = json.loads(args_str) if args_str else {}
                    
                    session = tool_to_session.get(name)
                    
                    if session:
                        result = await session.call_tool(name, arguments=args_dict)
                        # Extract text contents from the MCP result
                        text_results = [c.text for c in result.content if c.type == "text"]
                        result_str = "\n".join(text_results)
                        print(f"\033[92m[+] Tool result snippet: {result_str[:150]}...\033[0m", file=sys.stderr)
                    else:
                        result_str = f"Error: Tool '{name}' not found on any connected MCP server."
                        print(f"\033[91m[!] {result_str}\033[0m", file=sys.stderr)
                        
                except Exception as e:
                    result_str = f"Error executing tool '{name}': {str(e)}"
                    print(f"\033[91m[!] {result_str}\033[0m", file=sys.stderr)
                    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str
                })
                
            # Loop will continue to send the tool results back to the LLM
            print(f"\033[94m[*] Sending tool results back to model...\033[0m", file=sys.stderr)
            continue
            
        # If we got here and it's not a tool call, the generation is complete
        if current_assistant_content or current_assistant_extra:
            msg = {"role": "assistant"}
            if current_assistant_content:
                msg["content"] = current_assistant_content
            else:
                msg["content"] = "" # Models prefer an explicit empty string over missing content
                
            # Preserve message-level thought signatures to satisfy reasoning context
            if current_assistant_extra:
                msg["extra_content"] = current_assistant_extra
            messages.append(msg)
        break

class MCPAppendAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, 'mcp_configs', None) is None:
            setattr(namespace, 'mcp_configs', [])
        for v in values:
            namespace.mcp_configs.append({"endpoint": v, "api_key": None, "env_base": None})

class MCPAPIKeyAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        mcp_configs = getattr(namespace, 'mcp_configs', None)
        if not mcp_configs:
            parser.error(f"{option_string} must be provided after an --mcp argument")
        mcp_configs[-1]["api_key"] = values

class MCPEnvBaseAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        mcp_configs = getattr(namespace, 'mcp_configs', None)
        if not mcp_configs:
            parser.error(f"{option_string} must be provided after an --mcp argument")
        mcp_configs[-1]["env_base"] = values

async def async_main():
    parser = argparse.ArgumentParser(
        description="Stream multimodal input (text, images, PDFs) to a llama.cpp server with MCP support."
    )
    
    parser.add_argument("input", type=str, nargs='?', default=None, help="Path to a text file containing the prompt, or the direct prompt string itself.")
    parser.add_argument("-p", "--prompt", type=str, default=None, help="Pass a direct string on the command line to use as the prompt.")
    parser.add_argument("--session", type=str, help="Path to a JSON file to save/load the chat history for continuous conversations.")
    parser.add_argument("--system", type=str, help="Path to a markdown text file containing the system message.")
    parser.add_argument("--images", type=str, nargs='+', help="Path(s) to image files to include in the prompt.")
    parser.add_argument("--pdfs", type=str, nargs='+', help="Path(s) to PDF files to include in the prompt.")
    parser.add_argument("--assets", type=str, nargs='+', help="Path(s) to folder(s) containing image (png, jpg, jpeg) and PDF files to automatically include in the prompt.")
    parser.add_argument("--mcp", type=str, action=MCPAppendAction, nargs='+', help="Commands to start MCP servers (e.g., 'npx -y ...') or HTTP URLs ('http://.../sse' for SSE, 'http://.../mcp' for Streamable HTTP). Can be specified multiple times.")
    parser.add_argument("--mcp-api-key", type=str, action=MCPAPIKeyAction, help="API key for the preceding MCP server.")
    parser.add_argument("--mcp-env-base", type=str, action=MCPEnvBaseAction, help="Prefix for environment variables to pass to the preceding MCP server in stdio mode (e.g., 'FOO' to map FOO_API_KEY to API_KEY).")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8080/v1/chat/completions", help="URL of the llama-server (default: http://127.0.0.1:8080/v1/chat/completions)")
    parser.add_argument("--temp", type=float, default=0.7, help="Generation temperature (default: 0.7)")
    parser.add_argument("--max-tokens", type=int, default=-1, help="Maximum tokens to predict. -1 means infinity (default: -1)")
    parser.add_argument("--api-key", type=str, default=os.environ.get("API_KEY"), help="API key for the server (can also use API_KEY env var)")
    parser.add_argument("--model", type=str, default="default", help="Model name (e.g., 'gemini-2.5-flash' for Gemini)")
    parser.add_argument("--context-limit", type=int, default=None, help="Maximum context size (e.g., 8192) to display usage percentage.")
    parser.add_argument("--usage-file", type=str, default=None, help="Path to a JSON file to save and load lifetime token usage tracking.")
    parser.add_argument("--tool-session", type=str, default=None, help="Path to a JSON file to log the tool descriptions loaded into the model.")
    parser.add_argument("--insecure", action="store_true", help="Allow insecure server connections when using SSL (disable certificate verification).")
    parser.add_argument("--timeout", type=int, default=360, help="Timeout in seconds for HTTP requests (default: 360)")
    parser.add_argument("--prompt-timeout", type=int, default=360, help="Maximum overall time in seconds allowed for the generation, thinking, and tool execution (default: 360). Returns an error if exceeded.")
    parser.add_argument("--debug", type=str, default=None, help="Path to a JSONL file to log API requests and responses for debugging.")
    parser.add_argument("--no-spinner", action="store_true", help="Disable the thinking and working spinner animation on the console.")

    args = parser.parse_args()

    # Ensure at least some form of input was provided
    if not any([args.input, args.prompt, args.session, args.images, args.pdfs, args.assets]):
        parser.error("You must provide at least one input source: a file, a prompt string (-p), images, pdfs, assets, or a session.")

    if args.insecure:
        # Globally disable SSL verification for standard library functions (helps with external module connections)
        ssl._create_default_https_context = ssl._create_unverified_context

    # Configure Backend Setup
    api_key = args.api_key
    # Auto-correct old /completion endpoint to Chat API endpoint for llama-server
    if args.url.endswith("/completion"):
        print("\033[93m[*] Notice: Auto-correcting URL from '/completion' to '/v1/chat/completions' for Chat API & MCP support.\033[0m", file=sys.stderr)
        args.url = args.url.replace("/completion", "/v1/chat/completions")

    # Verify MCP dependencies if MCP is requested
    if getattr(args, 'mcp_configs', None):
        try:
            import mcp
            from mcp.client.stdio import stdio_client, StdioServerParameters
            from mcp.client.sse import sse_client
            from mcp.client.session import ClientSession
            
            # Streamable HTTP is available in newer versions of the mcp package
            try:
                from mcp.client.streamable_http import streamablehttp_client
            except ImportError:
                streamablehttp_client = None

        except ImportError:
            print("\033[91m[!] Error: The 'mcp' library is required to use MCP servers.\033[0m", file=sys.stderr)
            print("\033[93m    Install it with: pip install mcp\033[0m", file=sys.stderr)
            sys.exit(1)

    messages = []

    # Load session history if provided
    session_msg_count = 0
    if args.session and os.path.exists(args.session):
        try:
            with open(args.session, 'r', encoding='utf-8') as f:
                messages = json.load(f)
            session_msg_count = len(messages)
            print(f"\033[94m[*] Loaded previous session from {args.session} ({session_msg_count} messages)\033[0m", file=sys.stderr)
        except Exception as e:
            print(f"\033[91m[!] Error loading session '{args.session}': {e}\033[0m", file=sys.stderr)
            sys.exit(1)
            
    # Load usage tracker if provided
    usage_tracker = {}
    if args.usage_file and os.path.exists(args.usage_file):
        try:
            with open(args.usage_file, 'r', encoding='utf-8') as f:
                usage_tracker = json.load(f)
            print(f"\033[94m[*] Loaded token usage tracking from {args.usage_file}\033[0m", file=sys.stderr)
        except Exception as e:
            print(f"\033[91m[!] Error loading usage file '{args.usage_file}': {e}\033[0m", file=sys.stderr)
            sys.exit(1)

    # Load tool session history if provided
    tool_history = []
    if args.tool_session and os.path.exists(args.tool_session):
        try:
            with open(args.tool_session, 'r', encoding='utf-8') as f:
                tool_history = json.load(f)
            print(f"\033[94m[*] Loaded tool history from {args.tool_session}\033[0m", file=sys.stderr)
        except Exception as e:
            print(f"\033[91m[!] Error loading tool session '{args.tool_session}': {e}\033[0m", file=sys.stderr)
            sys.exit(1)

    # 1. System Message (Only insert if not already present in the history)
    if args.system and not any(m.get("role") == "system" for m in messages):
        try:
            with open(args.system, 'r', encoding='utf-8') as f:
                messages.insert(0, {"role": "system", "content": f.read()})
                session_msg_count += 1
        except Exception as e:
            print(f"\033[91m[!] Error reading system file '{args.system}': {e}\033[0m", file=sys.stderr)
            sys.exit(1)

    # Process --assets folder(s) to dynamically populate args.pdfs and args.images
    if getattr(args, 'assets', None):
        if args.images is None:
            args.images = []
        if args.pdfs is None:
            args.pdfs = []
            
        for asset_dir in args.assets:
            if os.path.isdir(asset_dir):
                print(f"\033[94m[*] Scanning assets folder: {asset_dir}...\033[0m", file=sys.stderr)
                # Sort files to ensure deterministic ingestion order
                for filename in sorted(os.listdir(asset_dir)):
                    filepath = os.path.join(asset_dir, filename)
                    if os.path.isfile(filepath):
                        ext = os.path.splitext(filename)[1].lower()
                        if ext == '.pdf':
                            if filepath not in args.pdfs:
                                args.pdfs.append(filepath)
                        elif ext in ['.png', '.jpg', '.jpeg']:
                            if filepath not in args.images:
                                args.images.append(filepath)
            else:
                print(f"\033[93m[*] Warning: Asset path '{asset_dir}' is not a valid directory.\033[0m", file=sys.stderr)

    user_content = []

    # 2. PDF Files
    if args.pdfs:
        for pdf_path in args.pdfs:
            print(f"\033[94m[*] Extracting text from PDF: {pdf_path}...\033[0m", file=sys.stderr)
            pdf_text = extract_pdf_text(pdf_path)
            user_content.append({"type": "text", "text": f"\n--- Content of {pdf_path} ---\n{pdf_text}\n"})

    # 3. Main Text Prompt
    prompt_text = ""
    
    if args.input:
        if os.path.isfile(args.input):
            try:
                with open(args.input, 'r', encoding='utf-8') as f:
                    prompt_text = f.read()
            except Exception as e:
                print(f"\033[91m[!] Error reading file '{args.input}': {e}\033[0m", file=sys.stderr)
                sys.exit(1)
        else:
            # If it's not a valid file path, treat it as a direct string prompt
            if len(args.input) < 256 and " " not in args.input and "." in args.input:
                print(f"\033[93m[*] Warning: '{args.input}' looks like a filename but was not found. Treating as text prompt.\033[0m", file=sys.stderr)
            prompt_text = args.input

    if args.prompt:
        if prompt_text:
            prompt_text += "\n\n" + args.prompt
        else:
            prompt_text = args.prompt

    if prompt_text and prompt_text.strip():
        user_content.append({"type": "text", "text": prompt_text.strip()})

    if not user_content:
        print("\033[93m[!] Warning: The provided prompt content is empty.\033[0m", file=sys.stderr)

    # 4. Images
    if args.images:
        for img_path in args.images:
            file_size = os.path.getsize(img_path)
            # Add a warning for massive images which often cause endpoint processing failures or proxy drops
            if file_size > 15 * 1024 * 1024:
                print(f"\033[93m[!] Warning: Image '{img_path}' is very large ({file_size / 1024 / 1024:.1f}MB). The server might reject it or hit memory limits.\033[0m", file=sys.stderr)
                
            print(f"\033[94m[*] Encoding image: {img_path}...\033[0m", file=sys.stderr)
            try:
                b64, mime = encode_image(img_path)
                user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            except Exception as e:
                print(f"\033[91m[!] Error processing image '{img_path}': {e}\033[0m", file=sys.stderr)
                sys.exit(1)

    messages.append({"role": "user", "content": user_content})

    # MCP Setup Context
    async with AsyncExitStack() as stack:
        tools_list = []
        tool_to_session = {}
        
        mcp_configs = getattr(args, 'mcp_configs', None)
        if mcp_configs:
            for mcp_config in mcp_configs:
                endpoint = mcp_config["endpoint"]
                mcp_api_key = mcp_config["api_key"]
                mcp_env_base = mcp_config["env_base"]
                
                try:
                    if endpoint.startswith("http://") or endpoint.startswith("https://"):
                        kwargs = {}
                        if mcp_api_key:
                            kwargs["headers"] = {"Authorization": f"Bearer {mcp_api_key}"}

                        # Differentiate between Streamable HTTP and SSE based on the endpoint path
                        if endpoint.rstrip('/').endswith('/mcp'):
                            if streamablehttp_client is None:
                                print(f"\033[91m[!] Error: 'streamablehttp_client' is not available in your 'mcp' library version.\033[0m", file=sys.stderr)
                                print("\033[93m    Please update the package with: pip install -U mcp\033[0m", file=sys.stderr)
                                sys.exit(1)
                            print(f"\033[94m[*] Initializing MCP Server (Streamable HTTP): {endpoint}\033[0m", file=sys.stderr)
                            transport = await stack.enter_async_context(streamablehttp_client(endpoint, **kwargs))
                        else:
                            print(f"\033[94m[*] Initializing MCP Server (SSE): {endpoint}\033[0m", file=sys.stderr)
                            transport = await stack.enter_async_context(sse_client(endpoint, **kwargs))
                    else:
                        print(f"\033[94m[*] Initializing MCP Server (Stdio): {endpoint}\033[0m", file=sys.stderr)
                        parts = shlex.split(endpoint)
                        
                        # Handle stdio environment injection via --mcp-env-base
                        server_env = None
                        if mcp_env_base:
                            server_env = os.environ.copy()
                            # Use {env_base}_ as prefix to target only specific config keys
                            prefix = f"{mcp_env_base}_" if not mcp_env_base.endswith('_') else mcp_env_base
                            mapped_count = 0
                            
                            for k, v in os.environ.items():
                                if k.startswith(prefix):
                                    mapped_key = k[len(prefix):]
                                    server_env[mapped_key] = v
                                    mapped_count += 1
                                    
                            if mapped_count > 0:
                                print(f"\033[90m    - Injected {mapped_count} env vars mapped from prefix '{prefix}'\033[0m", file=sys.stderr)
                        
                        server_params = StdioServerParameters(command=parts[0], args=parts[1:], env=server_env)
                        transport = await stack.enter_async_context(stdio_client(server_params))
                    
                    # Safely unpack read and write streams. This handles both older 2-tuple 
                    # and newer 3-tuple formats returned by different MCP transports
                    read, write = transport[0], transport[1]
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    
                    mcp_tools = await session.list_tools()
                    print(f"\033[92m    -> Connected. Extracted {len(mcp_tools.tools)} tools.\033[0m", file=sys.stderr)
                    
                    for t in mcp_tools.tools:
                        if t.name in tool_to_session:
                            print(f"\033[93m    -> Warning: Tool '{t.name}' is overwritten by the current server.\033[0m", file=sys.stderr)
                            # Remove the old tool from tools_list to avoid duplicate definitions
                            tools_list = [tool for tool in tools_list if tool.get("function", {}).get("name") != t.name]
                            
                        tool_to_session[t.name] = session
                        # Convert to standard OpenAI tool format for llama-server
                        tools_list.append({
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.inputSchema
                            }
                        })
                except BaseException as e:
                    # By catching BaseException, we handle ExceptionGroup (from AnyIO), CancelledError, and normal Exceptions
                    # Let SystemExits/KeyboardInterrupts pass freely
                    if isinstance(e, (KeyboardInterrupt, SystemExit)):
                        raise
                    
                    err_name = type(e).__name__
                    err_msg = str(e)
                    
                    print(f"\033[93m[!] Warning: Unable to connect to MCP server '{endpoint}'.\033[0m", file=sys.stderr)
                    print(f"\033[93m    The server might be offline or unreachable.\033[0m", file=sys.stderr)
                    print(f"\033[93m    Details: [{err_name}] {err_msg}\033[0m", file=sys.stderr)
                    raise

        # Log tools if tool session tracking is enabled
        if args.tool_session:
            tool_history.append({
                "timestamp": time.time(),
                "tools": tools_list
            })

        # Start the Chat Loop
        interrupted = False
        prompt_timeout_occurred = False
        try:
            chat_coro = chat_loop(
                url=args.url,
                messages=messages,
                tools=tools_list,
                tool_to_session=tool_to_session,
                temperature=args.temp,
                n_predict=args.max_tokens,
                api_key=api_key,
                model=args.model,
                context_limit=args.context_limit,
                session_msg_count=session_msg_count,
                usage_tracker=usage_tracker,
                insecure=args.insecure,
                timeout=args.timeout,
                debug_file=args.debug,
                no_spinner=args.no_spinner
            )
            
            if args.prompt_timeout and args.prompt_timeout > 0:
                await asyncio.wait_for(chat_coro, timeout=args.prompt_timeout)
            else:
                await chat_coro
                
        except (asyncio.TimeoutError, TimeoutError):
            print("\n\n\033[91mError: Prompt timeout\033[0m", file=sys.stderr)
            prompt_timeout_occurred = True
        except KeyboardInterrupt:
            print("\n\n\033[93m[!] Generation interrupted by user.\033[0m", file=sys.stderr)
            interrupted = True
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise
            err_name = type(e).__name__
            err_msg = str(e)
            print(f"\n\033[91m[!] Unexpected error during chat execution: [{err_name}] {err_msg}\033[0m", file=sys.stderr)
            
        # Save session history (even if timeout/interrupted to keep context generated so far)
        if args.session:
            try:
                with open(args.session, 'w', encoding='utf-8') as f:
                    json.dump(messages, f, indent=2)
                print(f"\n\033[94m[*] Chat session saved to {args.session}\033[0m", file=sys.stderr)
            except Exception as e:
                print(f"\n\033[91m[!] Error saving session: {e}\033[0m", file=sys.stderr)

        # Save usage tracking
        if args.usage_file and usage_tracker:
            try:
                with open(args.usage_file, 'w', encoding='utf-8') as f:
                    json.dump(usage_tracker, f, indent=2)
                print(f"\033[94m[*] Token usage saved to {args.usage_file}\033[0m", file=sys.stderr)
            except Exception as e:
                print(f"\033[91m[!] Error saving usage tracking: {e}\033[0m", file=sys.stderr)

        # Save tool session history
        if args.tool_session:
            try:
                with open(args.tool_session, 'w', encoding='utf-8') as f:
                    json.dump(tool_history, f, indent=2)
                print(f"\033[94m[*] Tool schemas logged to {args.tool_session}\033[0m", file=sys.stderr)
            except Exception as e:
                print(f"\033[91m[!] Error saving tool session: {e}\033[0m", file=sys.stderr)
                
        if prompt_timeout_occurred:
            sys.exit(1)
        if interrupted:
            sys.exit(0)

def main():
    # Force UTF-8 encoding for standard output and error to prevent UnicodeEncodeError on Windows/legacy terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        # Fallback in case exception bubbles outside async_main
        print("\n\n\033[93m[!] Generation interrupted by user.\033[0m", file=sys.stderr)        
        sys.exit(1)
    except SystemExit as e:
        # Gracefully handle normal SystemExits (from sys.exit)
        sys.exit(e.code)
    except BaseException as e:
        sys.exit(1)

if __name__ == "__main__":
    main()