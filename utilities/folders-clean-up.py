# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import shutil
from pathlib import Path
import sys

def clear_directory(dir_path: str) -> None:
    """
    Removes all files and subdirectories inside the specified directory.
    The directory itself is kept intact.
    """
    path = Path(dir_path)
    
    # Security check: Ensure the target directory is within the current working directory
    cwd = Path.cwd().resolve()
    resolved_path = path.resolve()
    
    try:
        resolved_path.relative_to(cwd)
    except ValueError:
        print(f"⚠️  Security block: '{dir_path}' is outside the current working directory. Skipping.")
        return

    # Check if the path exists and is a directory
    if not path.exists():
        print(f"⚠️  Directory '{dir_path}' does not exist. Skipping.")
        return

    if not path.is_dir():
        print(f"⚠️  Path '{dir_path}' is not a directory. Skipping.")
        return

    print(f"Cleaning up '{dir_path}'...")
    deleted_count = 0
    
    # Iterate through all items in the directory
    for item in path.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink() # Delete file or symlink
            elif item.is_dir():
                shutil.rmtree(item) # Delete subdirectory and its contents
            
            deleted_count += 1
        except PermissionError:
            print(f"❌ Permission denied: Cannot delete {item.name}")
        except Exception as e:
            print(f"❌ Failed to delete {item.name}. Reason: {e}")
            
    print(f"✅ Removed {deleted_count} items from '{dir_path}'.\n")

def main():
    # Set up the command line argument parser
    parser = argparse.ArgumentParser(
        description="A CLI tool to remove all files and subdirectories from specified folders."
    )
    
    # Default folders specified by the user
    default_folders = ["work.write", "work.report"]
    
    parser.add_argument(
        "folders", 
        nargs="*", 
        default=default_folders,
        help=f"The folders to clean. Defaults to: {', '.join(default_folders)}"
    )
    
    args = parser.parse_args()

    print("Starting cleanup process...\n" + "-"*30)
    
    # Process each folder
    for folder in args.folders:
        clear_directory(folder)
        
    print("-" * 30 + "\nCleanup process finished.")

if __name__ == "__main__":
    # Force UTF-8 encoding for standard output and error to prevent UnicodeEncodeError on Windows/legacy terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        
    # Ensure the script is being run directly and safely exit when done
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)