#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import sys
import argparse
import json

# Tiny 1x1 transparent PNG base64 representation
B64_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

def main():
    parser = argparse.ArgumentParser(description="Test image outputs for MCP System Skills.")
    parser.add_argument("--format", choices=["json", "uri", "raw", "text"], default="json", help="Format to output.")
    args = parser.parse_args()

    if args.format == "json":
        # Output as a JSON dict
        print(json.dumps({
            "type": "image",
            "data": B64_PNG,
            "mimeType": "image/png"
        }))
    elif args.format == "uri":
        # Output as a Data URI
        print(f"data:image/png;base64,{B64_PNG}")
    elif args.format == "raw":
        # Output as a raw base64 PNG
        print(B64_PNG)
    else:
        # Regular text
        print("This is plain text output.")

if __name__ == "__main__":
    main()
