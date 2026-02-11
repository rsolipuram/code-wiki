#!/usr/bin/env python3
"""
Observability tracker for Claude Code sessions.
Integrates with Langfuse (or any compatible observability backend) to track:
- Session metadata (duration, project, timestamps)
- Tool usage (which tools, frequency, performance)
- File operations (modified, created, deleted)
- Errors and outcomes

Supports local Langfuse instance or remote deployment.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import hashlib


class ObservabilityTracker:
    """Tracks Claude Code session activity for observability."""

    def __init__(self, project_dir: Path, config: Optional[Dict] = None):
        self.project_dir = project_dir
        self.config = config or {}
        self.session_file = None
        self.session_data = {}

    def initialize_session(self, hook_input: Dict) -> None:
        """Initialize session tracking (SessionStart hook)."""
        # Check if observability is enabled
        if not self.config.get('observability', {}).get('enabled', False):
            return

        # Generate session ID
        session_id = hook_input.get('session_id', self._generate_session_id())

        # Create session data structure
        self.session_data = {
            'session_id': session_id,
            'project_dir': str(self.project_dir),
            'project_name': self.project_dir.name,
            'start_time': datetime.now().isoformat(),
            'tools_used': [],
            'files_modified': [],
            'files_created': [],
            'files_deleted': [],
            'errors': [],
            'total_tool_calls': 0,
            'hook_event': 'SessionStart'
        }

        # Save to session file
        self._save_session()

        # Output for Claude
        output = {
            "systemMessage": f"📊 Session tracking initialized: {session_id[:8]}",
            "suppressOutput": False
        }
        print(json.dumps(output))

    def track_tool_usage(self, hook_input: Dict) -> None:
        """Track tool usage (PostToolUse hook)."""
        if not self.config.get('observability', {}).get('enabled', False):
            return

        # Load current session
        self._load_session()

        if not self.session_data:
            # Session not initialized, skip
            return

        # Extract tool information
        tool_name = hook_input.get('tool_name', 'Unknown')
        tool_input_data = hook_input.get('tool_input', {})
        tool_result = hook_input.get('tool_result', {})

        # Track tool usage
        tool_record = {
            'tool': tool_name,
            'timestamp': datetime.now().isoformat(),
            'success': not isinstance(tool_result, dict) or not tool_result.get('error')
        }

        # Track file operations
        if tool_name in ['Edit', 'Write']:
            file_path = tool_input_data.get('file_path', '')
            if file_path:
                if tool_name == 'Edit':
                    if file_path not in self.session_data['files_modified']:
                        self.session_data['files_modified'].append(file_path)
                elif tool_name == 'Write':
                    if file_path not in self.session_data['files_created']:
                        self.session_data['files_created'].append(file_path)

        # Add to tools used
        self.session_data['tools_used'].append(tool_record)
        self.session_data['total_tool_calls'] += 1

        # Save session
        self._save_session()

    def track_user_prompt(self, hook_input: Dict) -> None:
        """Track user prompt submission (UserPromptSubmit hook)."""
        if not self.config.get('observability', {}).get('enabled', False):
            return

        # Load current session
        self._load_session()

        if not self.session_data:
            # Initialize if not exists
            self.initialize_session(hook_input)

        # Track prompt (without storing actual content for privacy)
        if 'prompts_submitted' not in self.session_data:
            self.session_data['prompts_submitted'] = 0

        self.session_data['prompts_submitted'] += 1
        self.session_data['last_prompt_time'] = datetime.now().isoformat()

        # Save session
        self._save_session()

    def finalize_session(self, hook_input: Dict) -> None:
        """Finalize session tracking (Stop hook)."""
        if not self.config.get('observability', {}).get('enabled', False):
            return

        # Load current session
        self._load_session()

        if not self.session_data:
            # No session to finalize
            return

        # Add end time and duration
        self.session_data['end_time'] = datetime.now().isoformat()

        start = datetime.fromisoformat(self.session_data['start_time'])
        end = datetime.fromisoformat(self.session_data['end_time'])
        duration = (end - start).total_seconds()
        self.session_data['duration_seconds'] = duration

        # Calculate summary statistics
        self.session_data['summary'] = {
            'total_tools': self.session_data['total_tool_calls'],
            'unique_tools': len(set(t['tool'] for t in self.session_data['tools_used'])),
            'files_modified': len(self.session_data['files_modified']),
            'files_created': len(self.session_data['files_created']),
            'errors': len(self.session_data['errors']),
            'duration_minutes': round(duration / 60, 2)
        }

        # Save final session
        self._save_session()

        # Send to Langfuse if configured
        self._send_to_langfuse()

        # Output summary
        summary = self.session_data['summary']
        output = {
            "systemMessage": f"📊 Session complete: {summary['total_tools']} tools, {summary['files_modified']} files modified, {summary['duration_minutes']}min",
            "suppressOutput": False
        }
        print(json.dumps(output))

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().isoformat()
        random_data = os.urandom(8).hex()
        return hashlib.sha256(f"{timestamp}{random_data}".encode()).hexdigest()[:16]

    def _get_session_file(self) -> Path:
        """Get path to current session file."""
        if self.session_file:
            return self.session_file

        # Store sessions in .claude/observability/
        obs_dir = self.project_dir / '.claude' / 'observability'
        obs_dir.mkdir(parents=True, exist_ok=True)

        # Use a temporary file for current session
        self.session_file = obs_dir / 'current-session.json'
        return self.session_file

    def _save_session(self) -> None:
        """Save session data to file."""
        session_file = self._get_session_file()
        session_file.write_text(json.dumps(self.session_data, indent=2))

    def _load_session(self) -> None:
        """Load session data from file."""
        session_file = self._get_session_file()
        if session_file.exists():
            try:
                self.session_data = json.loads(session_file.read_text())
            except Exception:
                self.session_data = {}

    def _send_to_langfuse(self) -> None:
        """Send session data to Langfuse."""
        langfuse_config = self.config.get('observability', {}).get('langfuse', {})

        if not langfuse_config.get('enabled', False):
            # Save to local archive instead
            self._archive_session()
            return

        try:
            # Import Langfuse SDK
            from langfuse import Langfuse

            # Initialize client
            langfuse = Langfuse(
                host=langfuse_config.get('host', 'http://localhost:3000'),
                public_key=langfuse_config.get('public_key', ''),
                secret_key=langfuse_config.get('secret_key', '')
            )

            # Create trace
            trace = langfuse.trace(
                name="claude-code-session",
                id=self.session_data['session_id'],
                metadata={
                    'project': self.session_data['project_name'],
                    'project_dir': self.session_data['project_dir'],
                    'duration_seconds': self.session_data.get('duration_seconds', 0),
                    'summary': self.session_data.get('summary', {})
                },
                input={
                    'prompts_submitted': self.session_data.get('prompts_submitted', 0)
                },
                output={
                    'files_modified': self.session_data['files_modified'],
                    'files_created': self.session_data['files_created'],
                    'total_tools': self.session_data['total_tool_calls']
                }
            )

            # Add tool usage spans
            for tool_record in self.session_data['tools_used']:
                trace.span(
                    name=f"tool_{tool_record['tool']}",
                    start_time=datetime.fromisoformat(tool_record['timestamp']),
                    metadata={
                        'success': tool_record['success']
                    }
                )

            # Flush data
            langfuse.flush()

            # Archive session locally as backup
            self._archive_session()

        except ImportError:
            # Langfuse not installed, save locally
            self._archive_session()
        except Exception as e:
            # Error sending to Langfuse, save locally
            self.session_data['langfuse_error'] = str(e)
            self._archive_session()

    def _archive_session(self) -> None:
        """Archive completed session to local storage."""
        obs_dir = self.project_dir / '.claude' / 'observability' / 'sessions'
        obs_dir.mkdir(parents=True, exist_ok=True)

        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        session_id = self.session_data.get('session_id', 'unknown')[:8]
        archive_file = obs_dir / f'session-{timestamp}-{session_id}.json'

        # Save session
        archive_file.write_text(json.dumps(self.session_data, indent=2))

        # Clean up current session file
        session_file = self._get_session_file()
        if session_file.exists():
            session_file.unlink()


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
        'observability': {
            'enabled': False,
            'langfuse': {
                'enabled': False,
                'host': 'http://localhost:3000',
                'public_key': '',
                'secret_key': ''
            }
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

        # Initialize tracker
        tracker = ObservabilityTracker(project_dir, config)

        # Determine hook event
        hook_event = hook_input.get('hook_event_name', '')

        if hook_event == 'SessionStart':
            tracker.initialize_session(hook_input)
        elif hook_event == 'PostToolUse':
            tracker.track_tool_usage(hook_input)
        elif hook_event == 'UserPromptSubmit':
            tracker.track_user_prompt(hook_input)
        elif hook_event == 'Stop':
            tracker.finalize_session(hook_input)

        # Always exit 0 - observability should never block
        sys.exit(0)

    except Exception as e:
        # Log error but don't block
        error_output = {
            "systemMessage": f"⚠ Observability tracker error: {str(e)}",
            "suppressOutput": False
        }
        print(json.dumps(error_output), file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
