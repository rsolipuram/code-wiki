#!/usr/bin/env python3
"""
Completion notification hook for Claude Code.
Sends Mac notifications and text-to-speech when sessions complete.

Features:
- Mac notification center alerts
- Text-to-speech (TTS) with default macOS voice
- Detailed summary of changes (files modified, tests run, etc.)
- Configurable (can disable in settings)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class CompletionNotifier:
    """Manages completion notifications for Claude Code sessions."""

    def __init__(self, project_dir: Path, config: Optional[Dict] = None):
        self.project_dir = project_dir
        self.config = config or {}

    def get_session_summary(self) -> Dict[str, any]:
        """Generate a summary of the session's changes."""
        summary = {
            'files_modified': [],
            'files_created': [],
            'files_deleted': [],
            'total_changes': 0
        }

        try:
            # Get git status if available
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue

                    status = line[:2]
                    filename = line[3:]

                    # M = modified, A = added, D = deleted, ?? = untracked
                    if 'M' in status:
                        summary['files_modified'].append(filename)
                    elif 'A' in status or '??' == status:
                        summary['files_created'].append(filename)
                    elif 'D' in status:
                        summary['files_deleted'].append(filename)

                summary['total_changes'] = (
                    len(summary['files_modified']) +
                    len(summary['files_created']) +
                    len(summary['files_deleted'])
                )

        except Exception:
            # If git is not available or fails, return empty summary
            pass

        return summary

    def format_summary_message(self, summary: Dict[str, any]) -> str:
        """Format session summary into a readable message."""
        if summary['total_changes'] == 0:
            return "Claude Code session completed (no file changes detected)"

        parts = []

        if summary['files_modified']:
            count = len(summary['files_modified'])
            files_str = ', '.join(summary['files_modified'][:3])
            if count > 3:
                files_str += f" and {count - 3} more"
            parts.append(f"Modified: {files_str}")

        if summary['files_created']:
            count = len(summary['files_created'])
            files_str = ', '.join(summary['files_created'][:3])
            if count > 3:
                files_str += f" and {count - 3} more"
            parts.append(f"Created: {files_str}")

        if summary['files_deleted']:
            count = len(summary['files_deleted'])
            files_str = ', '.join(summary['files_deleted'][:3])
            if count > 3:
                files_str += f" and {count - 3} more"
            parts.append(f"Deleted: {files_str}")

        return "Claude Code session completed. " + "; ".join(parts)

    def send_mac_notification(self, message: str, title: str = "Claude Code") -> Tuple[bool, str]:
        """Send notification via macOS notification center."""
        try:
            # Use osascript to send notification
            script = f'''
display notification "{message}" with title "{title}"
'''
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                return True, "Notification sent"
            else:
                return False, f"Failed to send notification: {result.stderr}"

        except FileNotFoundError:
            return False, "osascript not found (macOS required)"
        except Exception as e:
            return False, f"Error sending notification: {str(e)}"

    def speak_message(self, message: str) -> Tuple[bool, str]:
        """Speak message using macOS text-to-speech."""
        try:
            # Use 'say' command for TTS
            # Keep message concise for TTS
            tts_message = message.split('.')[0]  # First sentence only

            result = subprocess.run(
                ['say', tts_message],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return True, "TTS completed"
            else:
                return False, f"TTS failed: {result.stderr}"

        except FileNotFoundError:
            return False, "say command not found (macOS required)"
        except Exception as e:
            return False, f"Error with TTS: {str(e)}"

    def send_notifications(self) -> Tuple[bool, str]:
        """Send completion notifications based on configuration."""
        # Check if notifications are enabled
        notif_config = self.config.get('notifications', {})

        if not notif_config.get('enabled', True):
            return True, "Notifications disabled in config"

        # Get session summary
        summary = self.get_session_summary()
        message = self.format_summary_message(summary)

        results = []

        # Send Mac notification if enabled
        if notif_config.get('mac_notification', True):
            success, msg = self.send_mac_notification(message)
            if success:
                results.append("✓ Mac notification sent")
            else:
                results.append(f"⚠ Mac notification failed: {msg}")

        # Send TTS if enabled
        if notif_config.get('tts', True):
            success, msg = self.speak_message(message)
            if success:
                results.append("✓ TTS announcement completed")
            else:
                results.append(f"⚠ TTS failed: {msg}")

        if results:
            return True, ' | '.join(results)
        else:
            return True, "No notifications configured"


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
        'notifications': {
            'enabled': True,
            'mac_notification': True,
            'tts': True
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

        # Initialize notifier
        notifier = CompletionNotifier(project_dir, config)

        # Send notifications
        success, message = notifier.send_notifications()

        # Output result
        if message:
            output = {
                "systemMessage": message,
                "suppressOutput": False
            }
            print(json.dumps(output))

        # Always exit 0 - notifications should never block
        sys.exit(0)

    except Exception as e:
        # Unexpected error - don't block
        error_output = {
            "systemMessage": f"⚠ Notification hook error: {str(e)}",
            "suppressOutput": False
        }
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(0)  # Don't block on notification errors


if __name__ == '__main__':
    main()
