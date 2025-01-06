# Disk Cleaner Tool

A secure disk cleaning utility designed to help you clean up old files while ensuring system file safety. This tool intelligently identifies and removes unused files while protecting critical system directories.

[中文版说明](README_CN.md)

## Key Features

- **Safe Scanning**: Automatically skips critical system directories
- **Smart Detection**: Identifies unused files based on last access time
- **Space Analysis**: Displays recoverable space statistics
- **Safety Confirmation**: Requires user confirmation before cleanup
- **Detailed Logging**: Records all cleaning operations

## Requirements

- Python 3.6 or higher
- Windows Operating System
- Administrator privileges (for accessing protected directories)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Run the program as administrator:
   ```
   python disk_cleaner.py
   ```
2. Enter the directory path to clean (e.g., `C:\`)
3. Specify the file age (number of days since last access)
4. Confirm the cleanup operation

## Security Features

- Automatic protection of system-critical directories
- Detailed file list and size information before cleanup
- All operations require user confirmation
- Backup recommendation before major cleanups

## Important Notes

- Avoid running cleanup during critical system operations
- Test on non-system drives first
- Run with administrator privileges if permission issues occur
- Always backup important data before performing cleanup operations

## Safety Guidelines

The tool implements several safety measures:
- System directory protection
- User confirmation requirements
- Detailed operation logging
- Reversible operations (when possible)

## Contributing

Feel free to submit issues and enhancement requests!