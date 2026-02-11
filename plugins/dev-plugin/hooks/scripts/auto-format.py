#!/usr/bin/env python3
"""
Auto-formatting hook for Claude Code.
Automatically formats files using prettier after Edit/Write operations.

Currently supports:
- TypeScript/JavaScript (prettier)

Future support planned:
- Python (black, ruff)
- Go (gofmt)
- Rust (rustfmt)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


class AutoFormatter:
    """Intelligent auto-formatter that detects project type and formats accordingly."""

    def __init__(self, project_dir: Path, config: Optional[Dict] = None):
        self.project_dir = project_dir
        self.config = config or {}

    def is_typescript_project(self) -> bool:
        """Check if this is a TypeScript/JavaScript project."""
        indicators = [
            "tsconfig.json",
            "package.json",
            "jsconfig.json"
        ]
        return any((self.project_dir / ind).exists() for ind in indicators)

    def should_format_file(self, file_path: str) -> bool:
        """Determine if file should be formatted based on extension and config."""
        # Skip if formatting is disabled
        if not self.config.get('autoformat', {}).get('enabled', True):
            return False

        # Get file extension
        ext = Path(file_path).suffix

        # TypeScript/JavaScript files
        if ext in ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']:
            return self.is_typescript_project()

        return False

    def format_with_prettier(self, file_path: str) -> Tuple[bool, str]:
        """Format file using prettier."""
        try:
            # Check if prettier is available
            check = subprocess.run(
                ['npx', 'prettier', '--version'],
                cwd=self.project_dir,
                capture_output=True,
                timeout=5
            )

            if check.returncode != 0:
                return False, "Prettier not found (install with: npm install -D prettier)"

            # Format the file
            result = subprocess.run(
                ['npx', 'prettier', '--write', file_path],
                cwd=self.project_dir,
                capture_output=True,
                timeout=30,
                text=True
            )

            if result.returncode == 0:
                return True, f"✓ Formatted {Path(file_path).name} with prettier"
            else:
                # Formatting failed, but don't block (exit 1, not 2)
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                return False, f"⚠ Prettier formatting failed: {error_msg}"

        except subprocess.TimeoutExpired:
            return False, "⚠ Prettier timed out"
        except FileNotFoundError:
            return False, "⚠ npx not found (Node.js required)"
        except Exception as e:
            return False, f"⚠ Error running prettier: {str(e)}"

    def format_file(self, file_path: str) -> Tuple[bool, str]:
        """Format a file using the appropriate formatter."""
        if not self.should_format_file(file_path):
            # Skip formatting, return success
            return True, ""

        # TypeScript/JavaScript - use prettier
        ext = Path(file_path).suffix
        if ext in ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']:
            return self.format_with_prettier(file_path)

        return True, ""


def load_config(project_dir: Path) -> Dict:
    """Load configuration from .claude/dev-plugin.local.md."""
    config_paths = [
        project_dir / '.claude' / 'dev-plugin.local.md',
        Path.home() / '.claude' / 'plugins' / 'dev-plugin' / 'settings.local.md'
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                # Read YAML frontmatter
                content = config_path.read_text()
                if content.startswith('---'):
                    import yaml
                    parts = content.split('---', 2)
                    if len(parts) >= 2:
                        return yaml.safe_load(parts[1]) or {}
            except Exception:
                pass

    # Return defaults
    return {
        'autoformat': {
            'enabled': True
        }
    }


def main():
    """Main hook execution."""
    try:
        # Read hook input from stdin
        hook_input = json.load(sys.stdin)

        # Get project directory
        project_dir = Path(os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd()))

        # Load configuration
        config = load_config(project_dir)

        # Get tool information
        tool_name = hook_input.get('tool_name', '')
        tool_input = hook_input.get('tool_input', {})

        # Only process Edit and Write tools
        if tool_name not in ['Edit', 'Write']:
            # Not a file modification, skip
            sys.exit(0)

        # Get file path
        file_path = tool_input.get('file_path', '')
        if not file_path:
            # No file path, skip
            sys.exit(0)

        # Initialize formatter
        formatter = AutoFormatter(project_dir, config)

        # Format the file
        success, message = formatter.format_file(file_path)

        # Output result
        if message:
            output = {
                "systemMessage": message,
                "suppressOutput": False
            }
            print(json.dumps(output))

        # Exit with appropriate code
        # Exit 0 = success (or skip)
        # Exit 1 = non-blocking warning
        # Don't use exit 2 (blocking) for formatting failures
        sys.exit(0 if success else 1)

    except Exception as e:
        # Unexpected error - don't block, just warn
        error_output = {
            "systemMessage": f"⚠ Auto-format hook error: {str(e)}",
            "suppressOutput": False
        }
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
