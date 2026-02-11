#!/usr/bin/env python3
"""
Git checkpointing hook for Claude Code.
Automatically creates detailed git commits at the end of sessions.

Features:
- Commits all changes to current branch
- Auto-stages modified files
- Generates detailed commit messages with diff summary
- Skips if no git repo exists
- Blocks if merge conflicts detected
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class GitCheckpointer:
    """Manages automatic git checkpoints."""

    def __init__(self, project_dir: Path, config: Optional[Dict] = None):
        self.project_dir = project_dir
        self.config = config or {}

    def is_git_repo(self) -> bool:
        """Check if current directory is a git repository."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=self.project_dir,
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def has_merge_conflicts(self) -> bool:
        """Check if there are unresolved merge conflicts."""
        try:
            # Check for merge conflicts
            result = subprocess.run(
                ['git', 'diff', '--name-only', '--diff-filter=U'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )

            conflicted_files = result.stdout.strip()
            return len(conflicted_files) > 0
        except Exception:
            return False

    def get_changed_files(self) -> List[str]:
        """Get list of changed files (staged + unstaged)."""
        try:
            # Get both staged and unstaged changes
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return []

            # Parse git status output
            changed_files = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    # Format: "XY filename"
                    # X = staged status, Y = unstaged status
                    status = line[:2]
                    filename = line[3:]

                    # Skip untracked files (marked as ??)
                    if status != '??':
                        changed_files.append(filename)

            return changed_files
        except Exception:
            return []

    def stage_all_changes(self) -> Tuple[bool, str]:
        """Stage all modified files."""
        try:
            result = subprocess.run(
                ['git', 'add', '-u'],  # -u stages modified/deleted, not new files
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return True, "Staged all changes"
            else:
                return False, f"Failed to stage changes: {result.stderr}"
        except Exception as e:
            return False, f"Error staging changes: {str(e)}"

    def get_diff_summary(self) -> str:
        """Get a brief summary of staged changes."""
        try:
            # Get diffstat for staged changes
            result = subprocess.run(
                ['git', 'diff', '--cached', '--stat'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                # Return condensed summary (first 3 files + summary line)
                lines = result.stdout.strip().split('\n')
                if len(lines) <= 4:
                    return result.stdout.strip()
                else:
                    # Show first 3 files + summary
                    summary_parts = lines[:3] + [f"... and {len(lines) - 4} more files"] + [lines[-1]]
                    return '\n'.join(summary_parts)
            else:
                return "No staged changes"
        except Exception:
            return "Unable to generate diff summary"

    def create_commit_message(self, changed_files: List[str], diff_summary: str) -> str:
        """Generate a detailed commit message."""
        # Get file count
        file_count = len(changed_files)

        # Get file types
        file_types = set()
        for f in changed_files:
            ext = Path(f).suffix
            if ext:
                file_types.add(ext)

        # Build commit message
        message_parts = []

        # Header
        if file_count == 1:
            message_parts.append(f"Auto-checkpoint: Modified {changed_files[0]}")
        else:
            file_types_str = ', '.join(sorted(file_types)) if file_types else 'various'
            message_parts.append(f"Auto-checkpoint: Modified {file_count} files ({file_types_str})")

        # Add blank line
        message_parts.append("")

        # Add diff summary
        message_parts.append("Changes:")
        message_parts.append(diff_summary)

        # Add footer
        message_parts.append("")
        message_parts.append("Committed by: Claude Code dev-plugin")

        return '\n'.join(message_parts)

    def create_checkpoint(self) -> Tuple[bool, str]:
        """Create a git checkpoint commit."""
        # Check if checkpointing is enabled
        if not self.config.get('git_checkpoint', {}).get('enabled', True):
            return True, "Git checkpointing disabled in config"

        # Check if git repo exists
        if not self.is_git_repo():
            # Skip silently as per requirements
            return True, "Not a git repository, skipping checkpoint"

        # Check for merge conflicts
        if self.has_merge_conflicts():
            # Block if conflicts exist (exit 2)
            return False, "⛔ Cannot checkpoint: unresolved merge conflicts detected. Please resolve conflicts first."

        # Get changed files
        changed_files = self.get_changed_files()

        if not changed_files:
            # No changes to commit
            return True, "No changes to checkpoint"

        # Stage all changes
        success, message = self.stage_all_changes()
        if not success:
            return False, f"⛔ Failed to stage changes: {message}"

        # Get diff summary
        diff_summary = self.get_diff_summary()

        # Generate commit message
        commit_message = self.create_commit_message(changed_files, diff_summary)

        # Create commit
        try:
            result = subprocess.run(
                ['git', 'commit', '-m', commit_message],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Extract commit hash
                commit_hash = None
                for line in result.stdout.split('\n'):
                    if 'checkpoint' in line.lower():
                        # Try to extract short hash
                        parts = line.split()
                        for part in parts:
                            if len(part) == 7 and all(c in '0123456789abcdef' for c in part):
                                commit_hash = part
                                break

                if commit_hash:
                    return True, f"✓ Created checkpoint commit {commit_hash} with {len(changed_files)} file(s)"
                else:
                    return True, f"✓ Created checkpoint commit with {len(changed_files)} file(s)"
            else:
                return False, f"⛔ Failed to create commit: {result.stderr}"

        except Exception as e:
            return False, f"⛔ Error creating commit: {str(e)}"


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
        'git_checkpoint': {
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

        # Initialize checkpointer
        checkpointer = GitCheckpointer(project_dir, config)

        # Create checkpoint
        success, message = checkpointer.create_checkpoint()

        # Output result
        if message:
            if success:
                output = {
                    "systemMessage": message,
                    "suppressOutput": False
                }
                print(json.dumps(output))
            else:
                # Blocking error
                output = {
                    "decision": "block",
                    "reason": message,
                    "systemMessage": message
                }
                print(json.dumps(output), file=sys.stderr)

        # Exit with appropriate code
        # Exit 0 = success
        # Exit 2 = blocking error (merge conflicts)
        sys.exit(0 if success else 2)

    except Exception as e:
        # Unexpected error - block to be safe
        error_output = {
            "decision": "block",
            "reason": f"Git checkpoint hook error: {str(e)}",
            "systemMessage": f"⛔ Git checkpoint hook error: {str(e)}"
        }
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
