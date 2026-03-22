# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import sys
import os

def convert_markdown_to_json(input_path, output_path):
    """
    Reads a markdown file, extracts the title from the first line,
    and writes the title and the rest of the body to a JSON file.
    """
    # 1. Read the input markdown file
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: The input file '{input_path}' was not found.", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading '{input_path}': {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Parse the content
    if not lines:
        title = ""
        body = ""
    else:
        # Find the first non-empty line to use as the title
        title_index = 0
        for i, line in enumerate(lines):
            if line.strip():
                title_index = i
                break
        
        # Extract title and strip leading markdown header characters ('#') and whitespace
        raw_title = lines[title_index].strip()
        title = raw_title.lstrip('# \t')

        # The rest of the file becomes the body
        body_lines = lines[title_index + 1:]
        # Join the lines and strip leading/trailing newlines to keep it clean
        body = "".join(body_lines).strip('\n')

    # 3. Prepare the JSON data structure
    data = {
        "title": title,
        "body": body
    }

    # 4. Write to the output JSON file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # Using indent=4 makes the JSON file nicely formatted and readable
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Success! Converted '{input_path}' to '{output_path}'.")
    except IOError as e:
        print(f"Error writing to '{output_path}': {e}", file=sys.stderr)
        sys.exit(1)

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(
        description="Convert a Markdown file to a JSON file containing a title and body.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "input_file", 
        help="Path to the input Markdown file (.md)"
    )
    parser.add_argument(
        "output_file", 
        help="Path to the destination JSON file (.json)"
    )

    # Parse arguments provided by the user
    args = parser.parse_args()

    # Run the conversion
    convert_markdown_to_json(args.input_file, args.output_file)

if __name__ == "__main__":
    main()