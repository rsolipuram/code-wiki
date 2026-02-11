#!/usr/bin/env python3
"""
Simple script to analyze Claude Code session data.

Usage:
    python3 analyze-sessions.py
"""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime

def analyze_sessions():
    """Analyze all session files in the observability directory."""
    sessions_dir = Path(__file__).parent / 'sessions'

    if not sessions_dir.exists():
        print("❌ No sessions directory found yet")
        return

    session_files = list(sessions_dir.glob('session-*.json'))

    if not session_files:
        print("📊 No sessions recorded yet")
        print("\nStart using Claude Code with the dev-plugin to begin tracking!")
        return

    # Load all sessions
    sessions = []
    for session_file in session_files:
        try:
            sessions.append(json.loads(session_file.read_text()))
        except Exception as e:
            print(f"⚠️  Error reading {session_file.name}: {e}")

    if not sessions:
        print("❌ No valid sessions found")
        return

    print(f"📊 Session Analytics")
    print(f"{'=' * 60}\n")

    # Total sessions
    print(f"📈 Total Sessions: {len(sessions)}")

    # Total tools used
    all_tools = []
    for s in sessions:
        for tool in s.get('tools_used', []):
            all_tools.append(tool['tool'])

    print(f"\n🔧 Tool Usage:")
    print(f"   Total tool calls: {len(all_tools)}")
    print(f"   Unique tools: {len(set(all_tools))}")

    # Most used tools
    print(f"\n🏆 Top 10 Most Used Tools:")
    for tool, count in Counter(all_tools).most_common(10):
        bar = '█' * (count // max(1, max(Counter(all_tools).values()) // 20))
        print(f"   {tool:20} {count:4} {bar}")

    # Session durations
    durations = [s.get('duration_seconds', 0) for s in sessions if 'duration_seconds' in s]
    if durations:
        avg_duration = sum(durations) / len(durations)
        total_duration = sum(durations)
        print(f"\n⏱️  Session Duration:")
        print(f"   Average: {avg_duration / 60:.1f} minutes")
        print(f"   Total: {total_duration / 3600:.1f} hours")
        print(f"   Longest: {max(durations) / 60:.1f} minutes")
        print(f"   Shortest: {min(durations) / 60:.1f} minutes")

    # Files modified
    all_files_modified = []
    all_files_created = []
    for s in sessions:
        all_files_modified.extend(s.get('files_modified', []))
        all_files_created.extend(s.get('files_created', []))

    print(f"\n📝 File Operations:")
    print(f"   Files modified: {len(all_files_modified)} ({len(set(all_files_modified))} unique)")
    print(f"   Files created: {len(all_files_created)} ({len(set(all_files_created))} unique)")

    # Most modified files
    if all_files_modified:
        print(f"\n📁 Most Modified Files:")
        for file, count in Counter(all_files_modified).most_common(5):
            print(f"   {count:2}x {file}")

    # Projects
    projects = [s.get('project_name', 'Unknown') for s in sessions]
    print(f"\n🗂️  Projects:")
    for project, count in Counter(projects).most_common():
        print(f"   {project}: {count} sessions")

    # Timeline
    print(f"\n📅 Timeline:")
    for s in sorted(sessions, key=lambda x: x.get('start_time', ''), reverse=True)[:5]:
        start = s.get('start_time', 'Unknown')
        duration = s.get('duration_seconds', 0)
        tools = s.get('total_tool_calls', 0)
        project = s.get('project_name', 'Unknown')

        try:
            timestamp = datetime.fromisoformat(start).strftime('%Y-%m-%d %H:%M')
        except:
            timestamp = start[:16] if len(start) > 16 else start

        print(f"   {timestamp} | {project:15} | {duration/60:5.1f}min | {tools:3} tools")

    print(f"\n{'=' * 60}")
    print(f"\n💡 Tip: View individual sessions with:")
    print(f"   cat .claude/observability/sessions/session-*.json | jq .")

if __name__ == '__main__':
    analyze_sessions()
