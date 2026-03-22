# Folders Clean Up (`folders-clean-up.py`)

## Description
`folders-clean-up.py` is a command-line utility designed to safely and efficiently empty specified directories. It removes all files, subdirectories, and symlinks within the target folders while preserving the root folder itself. 

The script includes a built-in security mechanism that strictly limits operations to directories within the current working directory. If a user attempts to clean a directory outside of this scope, the script will actively block the operation and skip the directory to prevent accidental system damage. It also safely handles missing directories, insufficient permissions, and ensures UTF-8 output compatibility across different terminals.

## Command Line Options

```text
usage: folders-clean-up.py [-h] [folders ...]

A CLI tool to remove all files and subdirectories from specified folders.

positional arguments:
  folders     The folders to clean. Defaults to: work.write, work.report

options:
  -h, --help  show this help message and exit
```

### Arguments Detail:
*   `folders` *(Optional)*: A space-separated list of folder paths you want to clean. If no folders are provided, the script will automatically default to cleaning the `work.write` and `work.report` directories.
*   `-h`, `--help`: Displays the help message detailing the usage and arguments.

## Examples

### 1. Run with Default Folders
If you run the script without any arguments, it will attempt to empty the `work.write` and `work.report` folders located in the current directory:
```bash
python folders-clean-up.py
```

### 2. Clean Specific Folders
You can specify one or more custom folders to clean by passing their paths as arguments:
```bash
python folders-clean-up.py build dist temp_cache
```

### 3. Display Help
To see the help menu and understand how to use the tool:
```bash
python folders-clean-up.py --help
```

## Safety and Error Handling
*   **Path Traversal Prevention:** Any path that resolves outside the current working directory is blocked with a security warning.
*   **Missing Directories:** If a specified directory does not exist or the path points to a file instead of a directory, it will be skipped with a warning.
*   **Permissions:** If the script lacks the permissions to delete a specific file or folder inside the target, it will report a "Permission denied" error for that item and continue processing the rest.
