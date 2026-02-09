# Development Plugin for Claude Code

An intelligent code quality plugin that automatically detects your project type and runs appropriate checks when Claude Code sessions end, ensuring high-quality, error-free code.

## Features

- 🎯 **Intelligent Detection**: Automatically identifies TypeScript, Python, Go, Rust projects
- ✅ **Multi-Language Support**: Works with TypeScript, Python, Go, Rust (more coming!)
- 🔒 **Blocking Enforcement**: Prevents session end if quality issues exist
- 🤖 **Auto-Fix Integration**: Feeds errors to Claude's context for automatic fixing
- ⚙️ **Fully Configurable**: Customize commands for each language
- 🚀 **Zero Config**: Works out of the box with sensible defaults
- 🎨 **Extensible**: Easy to add new language support

## Supported Languages

| Language | Detection | Default Checker | Additional Tools |
|----------|-----------|-----------------|------------------|
| **TypeScript** | `tsconfig.json` | `tsc --noEmit` | ESLint (planned) |
| **Python** | `pyproject.toml`, `setup.py`, etc. | `mypy` | `ruff`, `pylint` |
| **Go** | `go.mod` | `go build ./...` | `golangci-lint` (planned) |
| **Rust** | `Cargo.toml` | `cargo check` | `clippy` (planned) |

More languages coming soon: Java, C++, Ruby, PHP, and more!

## How It Works

When you finish working with Claude Code:

1. **Detection Phase**: Plugin scans for project indicators
2. **Check Phase**: Runs appropriate quality checks for each detected language
3. **Error Phase** (if issues found):
   - **Blocks** session end
   - Shows errors to Claude with file:line:column references
   - Claude automatically fixes the issues
   - Checks run again automatically
4. **Success Phase**: If no errors, session ends normally with success message

## Prerequisites

### Core
- Python 3.7+ (for the plugin itself)
- Claude Code

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

See `.claude-dev-plugin.local.md.example` for more configuration examples.

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
