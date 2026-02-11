# Development Plugin for Claude Code

An intelligent development automation plugin that ensures code quality, maintains clean code style, tracks changes with git checkpoints, and provides completion notifications — all automatically integrated into your Claude Code workflow.

## Features

### 🎯 Code Quality Enforcement
- **Intelligent Detection**: Automatically identifies TypeScript, Python, Go, Rust projects
- **Multi-Language Support**: Works with TypeScript, Python, Go, Rust (more coming!)
- **Blocking Enforcement**: Prevents session end if quality issues exist
- **Auto-Fix Integration**: Feeds errors to Claude's context for automatic fixing

### ✨ Auto-Formatting (NEW)
- **Automatic Code Formatting**: Auto-formats files after edits with prettier (TypeScript/JavaScript)
- **Project-Aware**: Only runs formatters for detected project types
- **Non-Blocking**: Warns on failure but doesn't block workflow
- **Configurable**: Enable/disable per project or globally

### 🔒 Safety Validations (NEW)
- **Dangerous Command Blocking**: Prevents destructive rm commands (`rm -rf *`, `rm -rf /`, etc.)
- **Intelligent Validation**: AI-powered command safety analysis
- **Pre-Execution Checks**: Validates before commands run

### 📦 Git Checkpointing (NEW)
- **Automatic Commits**: Creates detailed git commits at session end
- **Smart Summaries**: Includes file changes and diff statistics in commit messages
- **Conflict Detection**: Blocks commits if merge conflicts exist
- **Auto-Staging**: Automatically stages modified files

### 🔔 Completion Notifications (NEW)
- **Mac Notifications**: Desktop alerts when sessions complete
- **Text-to-Speech**: Voice announcements with session summary
- **Detailed Summaries**: Shows files modified, created, and deleted
- **Fully Configurable**: Enable/disable notifications and TTS independently

### 📊 Session Observability (NEW)
- **Automatic Tracking**: Records all tool usage and file operations
- **Session Metrics**: Duration, tool counts, files modified, errors
- **Local Storage**: Sessions saved to `.claude/observability/sessions/`
- **Langfuse Integration**: Optional integration with local or remote Langfuse
- **Privacy-First**: Tracks metadata only, no code/PII stored
- **Visual Analytics**: View session data in Langfuse dashboard

### ⚙️ Configuration & Control
- **Fully Configurable**: Customize all features via YAML settings
- **Global + Project Overrides**: Set defaults globally, override per project
- **Zero Config Default**: Works out of the box with sensible defaults
- **Extensible**: Easy to add new language support and features

---

## Quick Start

### 1. Install the Plugin

```bash
# Option 1: Project-specific
mkdir -p .claude-plugin
cp -r /path/to/dev-plugin .claude-plugin/

# Option 2: Global (all projects)
mkdir -p ~/.claude/plugins
cp -r /path/to/dev-plugin ~/.claude/plugins/

# Option 3: Test first
claude --plugin-dir /path/to/dev-plugin
```

### 2. Optional: Enable Observability

```bash
# Install Langfuse SDK
pip install langfuse pyyaml

# Create configuration
cat > .claude/dev-plugin.local.md << 'EOF'
---
observability:
  enabled: true
  langfuse:
    enabled: false  # Set to true if using Langfuse
---
EOF
```

### 3. Use Claude Code

```bash
# Start Claude Code
claude

# Your sessions are now tracked!
# - Quality checks run automatically
# - Files auto-format on edit
# - Git commits at session end
# - Notifications on completion
# - Sessions tracked in .claude/observability/sessions/
```

### 4. View Your Data

```bash
# See local session files
ls -lh .claude/observability/sessions/

# Analyze with jq
cat .claude/observability/sessions/*.json | jq '.summary'

# Or set up Langfuse for visual dashboard (optional)
```

---

## Supported Languages

| Language | Detection | Default Checker | Additional Tools |
|----------|-----------|-----------------|------------------|
| **TypeScript** | `tsconfig.json` | `tsc --noEmit` | ESLint (planned) |
| **Python** | `pyproject.toml`, `setup.py`, etc. | `mypy` | `ruff`, `pylint` |
| **Go** | `go.mod` | `go build ./...` | `golangci-lint` (planned) |
| **Rust** | `Cargo.toml` | `cargo check` | `clippy` (planned) |

More languages coming soon: Java, C++, Ruby, PHP, and more!

## How It Works

### During Editing (PostToolUse)

When Claude edits or creates files:

1. **Auto-Formatting**:
   - Detects file type (TypeScript/JavaScript currently supported)
   - Runs prettier if applicable
   - Formats code automatically
   - Warns if formatting fails (non-blocking)

### Before Dangerous Commands (PreToolUse)

When Claude attempts to run bash commands:

1. **Safety Validation**:
   - AI analyzes command for dangerous patterns
   - Blocks destructive rm commands (`rm -rf *`, `rm -rf /`, etc.)
   - Allows safe commands through
   - Provides explanation if blocked

### At Session End (Stop)

When Claude Code session completes:

1. **Quality Checks**:
   - Detects project type(s)
   - Runs appropriate quality checks
   - If errors found: blocks and auto-fixes
   - If clean: proceeds to next step

2. **Git Checkpointing**:
   - Checks for git repository
   - Detects merge conflicts (blocks if found)
   - Auto-stages modified files
   - Creates detailed commit with diff summary
   - Skips silently if not a git repo

3. **Completion Notifications**:
   - Analyzes session changes
   - Sends Mac notification with summary
   - Announces completion via text-to-speech
   - Reports files modified/created/deleted

4. **Session End**: All checks passed, session ends successfully

## Prerequisites

### Core
- Python 3.7+ (for the plugin itself)
- Claude Code
- PyYAML (recommended): `pip install pyyaml` - For configuration file parsing

### Optional (for Observability)
- Langfuse SDK: `pip install langfuse` - For session tracking with Langfuse
- Docker: For running local Langfuse instance

### Language-Specific

**TypeScript**:
- Node.js with `npx`
- TypeScript: `npm install -D typescript`

**Python**:
- MyPy: `pip install mypy` (optional but recommended)
- Ruff: `pip install ruff` (optional)

**Go**:
- Go 1.16+ with `go` command

**Rust**:
- Rust with `cargo` command

Only install tools for languages you use. The plugin gracefully skips checks for unavailable tools.

## Installation

### Option 1: Project Plugin

Copy this plugin to your project's plugin directory:

```bash
mkdir -p .claude-plugin
cp -r plugins/dev-plugin .claude-plugin/
```

### Option 2: Global Plugin

Install as a global plugin for all projects:

```bash
mkdir -p ~/.claude/plugins
cp -r plugins/dev-plugin ~/.claude/plugins/
```

### Option 3: Test Locally

Test the plugin before installing:

```bash
cc --plugin-dir /path/to/plugins/dev-plugin
```

## Configuration

Create `.claude/dev-plugin.local.md` to customize behavior:

### Basic Configuration

```yaml
---
enabled: true
---
```

### TypeScript Configuration

```yaml
---
typescript:
  command: npx tsc --noEmit --strict
---
```

### Python Configuration

```yaml
---
python:
  mypy_command: mypy --strict src/
  ruff_command: ruff check --select E,F,I src/
---
```

### Multi-Language Project

```yaml
---
typescript:
  command: npx tsc --noEmit
python:
  mypy_command: mypy backend/
  ruff_command: ruff check backend/
go:
  command: go build ./cmd/... ./pkg/...
---
```

### Disable Temporarily

```yaml
---
enabled: false
---
```

### Auto-Formatting Configuration

```yaml
---
autoformat:
  enabled: true  # Enable/disable auto-formatting
---
```

**Note**: Currently supports TypeScript/JavaScript with prettier. Auto-detects project type and only runs if applicable.

### Git Checkpointing Configuration

```yaml
---
git_checkpoint:
  enabled: true  # Enable/disable automatic git commits at session end
---
```

**Behavior**:
- Commits at end of session (Stop event)
- Auto-stages modified files
- Generates detailed commit messages with diff summary
- Skips silently if not a git repo
- Blocks if merge conflicts detected

### Notification Configuration

```yaml
---
notifications:
  enabled: true            # Master switch for all notifications
  mac_notification: true   # Desktop notification center alerts
  tts: true               # Text-to-speech announcements
---
```

**Notification Content**:
- Simple summary if no changes detected
- Detailed summary with files modified/created/deleted
- TTS uses first sentence only for brevity

### Observability Configuration

```yaml
---
observability:
  enabled: true          # Enable session tracking
  langfuse:
    enabled: false       # Set to true to send to Langfuse
    host: http://localhost:3000
    public_key: ""       # Your Langfuse public key
    secret_key: ""       # Your Langfuse secret key
---
```

**Local-Only Tracking** (no Langfuse):
- Set `observability.enabled: true` and `langfuse.enabled: false`
- Sessions saved to `.claude/observability/sessions/`
- Each session as JSON file with all metrics

**With Langfuse Integration**:
- Install: `pip install langfuse`
- Set up local Langfuse: See "Setting Up Langfuse" section below
- Configure keys in settings
- View sessions in Langfuse dashboard at `http://localhost:3000`

### Complete Configuration Example

```yaml
---
# Code quality checks (existing feature)
typescript:
  command: npx tsc --noEmit

# Auto-formatting (new)
autoformat:
  enabled: true

# Git checkpointing (new)
git_checkpoint:
  enabled: true

# Completion notifications (new)
notifications:
  enabled: true
  mac_notification: true
  tts: true
---
```

See `.claude-dev-plugin.local.md.example` for more configuration examples.

---

## Setting Up Langfuse (Optional)

To visualize session data with Langfuse, you can run it locally:

### Quick Start with Docker

```bash
# 1. Create directory for Langfuse
mkdir -p ~/langfuse && cd ~/langfuse

# 2. Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/langfuse
      - NEXTAUTH_URL=http://localhost:3000
      - NEXTAUTH_SECRET=your-secret-key-change-this
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=langfuse
    volumes:
      - langfuse-db:/var/lib/postgresql/data

volumes:
  langfuse-db:
EOF

# 3. Start Langfuse
docker compose up -d

# 4. Access at http://localhost:3000
```

### Get API Keys

1. Open `http://localhost:3000` in browser
2. Create account (first user is admin)
3. Go to Settings → API Keys
4. Create new key pair
5. Copy `public_key` (pk-lf-...) and `secret_key` (sk-lf-...)

### Configure Plugin

Update `.claude/dev-plugin.local.md`:

```yaml
---
observability:
  enabled: true
  langfuse:
    enabled: true
    host: http://localhost:3000
    public_key: pk-lf-xxxxxxxx  # From Langfuse dashboard
    secret_key: sk-lf-xxxxxxxx  # From Langfuse dashboard
---
```

### Install Langfuse SDK

```bash
pip install langfuse
```

Done! Your sessions will now be tracked in Langfuse.

---

## Usage

Once installed, the plugin works automatically:

1. Work with Claude Code as normal
2. Make changes to your code
3. When Claude tries to Stop:
   - Plugin detects project type(s)
   - Runs appropriate quality checks
   - If errors exist, Claude receives them and fixes automatically
   - If no errors, session ends

### Example: TypeScript Project

```
Claude makes changes to TypeScript files
→ Session tries to end
→ Plugin detects TypeScript (tsconfig.json)
→ Runs: npx tsc --noEmit
→ Finds 2 type errors
→ Blocks session, sends errors to Claude
→ Claude fixes the errors
→ Check passes
→ Session ends successfully
```

### Example: Multi-Language Project

```
Project structure:
  frontend/ (TypeScript)
  backend/ (Python)
  services/ (Go)

→ Plugin detects all three languages
→ Runs TypeScript, Python, and Go checks
→ All must pass for session to end
```

## Example Output

### When Errors Found

```
TypeScript check failed with 2 error(s):

src/utils/helper.ts:15:3 - error TS2322: Type 'string' is not assignable to type 'number'.
src/components/Button.tsx:42:10 - error TS2339: Property 'onClick' does not exist on type 'Props'.

Python MyPy found 1 type error(s):

backend/api.py:25: error: Argument 1 to "process" has incompatible type "str"; expected "int"

The errors above must be resolved to ensure code quality.
```

Claude then automatically fixes these issues.

### When Checks Pass

```
[OK] Code quality checks passed for: TypeScript, Python, Go
```

Session ends normally.

---

## Viewing Observability Data

### Local JSON Files

Sessions are saved to `.claude/observability/sessions/`:

```bash
# View latest session
cat .claude/observability/sessions/session-*.json | jq .

# See all sessions
ls -lh .claude/observability/sessions/

# Analyze sessions with jq
cat .claude/observability/sessions/*.json | jq '.summary'
```

**Session Data Structure:**
```json
{
  "session_id": "abc123...",
  "project_name": "my-project",
  "start_time": "2026-02-10T20:00:00",
  "end_time": "2026-02-10T20:15:00",
  "duration_seconds": 900,
  "tools_used": [
    {"tool": "Read", "timestamp": "...", "success": true},
    {"tool": "Edit", "timestamp": "...", "success": true}
  ],
  "files_modified": ["src/app.ts", "src/utils.ts"],
  "files_created": ["src/new-feature.ts"],
  "total_tool_calls": 25,
  "summary": {
    "total_tools": 25,
    "unique_tools": 5,
    "files_modified": 2,
    "files_created": 1,
    "errors": 0,
    "duration_minutes": 15.0
  }
}
```

### Langfuse Dashboard

If Langfuse integration is enabled:

1. **View Sessions**: `http://localhost:3000/traces`
2. **Session Details**: Click on any session to see:
   - Complete timeline of tool usage
   - File operations breakdown
   - Performance metrics
   - Error tracking
3. **Analytics**: Built-in charts for:
   - Tools usage over time
   - Session duration trends
   - Files modified patterns
   - Error rates

### Simple Analytics Script

Create a quick analysis script:

```python
# analyze-sessions.py
import json
from pathlib import Path
from collections import Counter

sessions_dir = Path('.claude/observability/sessions')
sessions = [json.loads(f.read_text()) for f in sessions_dir.glob('*.json')]

# Total sessions
print(f"Total sessions: {len(sessions)}")

# Most used tools
all_tools = [t['tool'] for s in sessions for t in s['tools_used']]
print("\nMost used tools:")
for tool, count in Counter(all_tools).most_common(10):
    print(f"  {tool}: {count}")

# Average session duration
avg_duration = sum(s.get('duration_seconds', 0) for s in sessions) / len(sessions)
print(f"\nAverage session: {avg_duration / 60:.1f} minutes")
```

---

## Project Detection

The plugin automatically detects project types by looking for indicator files:

### TypeScript
- `tsconfig.json` → Runs TypeScript compiler

### Python
- `pyproject.toml` → Modern Python project
- `setup.py` → Traditional Python package
- `requirements.txt` → Python dependencies
- `Pipfile` → Pipenv project
- `poetry.lock` → Poetry project

### Go
- `go.mod` → Go module

### Rust
- `Cargo.toml` → Cargo project

**Smart Behavior**: If a project has multiple languages (e.g., TypeScript frontend + Python backend), the plugin detects and checks all of them.

## Troubleshooting

### Plugin Not Running

**Check**:
1. Verify plugin is installed and enabled in Claude Code
2. Ensure Python 3.7+ is available: `python3 --version`
3. Look for indicator files in your project (tsconfig.json, go.mod, etc.)

### No Project Type Detected

**Message**: `No recognized project type detected`

**Solution**: Add an indicator file:
- TypeScript: Create `tsconfig.json`
- Python: Create `pyproject.toml` or `requirements.txt`
- Go: Run `go mod init`
- Rust: Run `cargo init`

### Tool Not Found

**Message**: `TypeScript not found, skipping check`

**Solution**: Install the required tool:
```bash
# TypeScript
npm install -D typescript

# Python
pip install mypy ruff

# Go
# Install Go from https://go.dev

# Rust
# Install Rust from https://rustup.rs
```

### Checks Taking Too Long

**Solution**: Reduce scope or increase timeout in `hooks.json`:
```json
{
  "timeout": 120
}
```

Or configure faster checks:
```yaml
---
typescript:
  command: npx tsc --noEmit --skipLibCheck
python:
  mypy_command: mypy --fast src/
---
```

### Disable for Specific Projects

Create `.claude/dev-plugin.local.md`:
```yaml
---
enabled: false
---
```

## Development

### File Structure

```
dev-plugin/
├── .claude-plugin/
│   └── plugin.json                        # Plugin manifest
├── hooks/
│   ├── hooks.json                         # Hook configuration
│   └── scripts/
│       └── quality-check.py               # Intelligent checker script
├── .claude-dev-plugin.local.md.example    # Settings template
├── .gitignore                             # Git exclusions
└── README.md                              # This file
```

### Testing the Script

Test the quality check script directly:

```bash
cd /path/to/your/project
export CLAUDE_PROJECT_DIR=$(pwd)
echo '{}' | python3 /path/to/quality-check.py
echo "Exit code: $?"
```

Exit codes:
- `0` - Success (no errors)
- `2` - Blocking error (quality issues found)

### Adding New Languages

To add support for a new language, edit `quality-check.py`:

1. Add detector method
2. Add checker method
3. Add to run_all_checks

Contributions welcome!

## License

MIT
