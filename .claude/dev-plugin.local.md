---
# Development Plugin Configuration

# Observability tracking (ENABLED)
observability:
  enabled: true  # Track all Claude Code sessions
  langfuse:
    enabled: false  # Local-only tracking (no Langfuse for now)
    host: http://localhost:3000
    public_key: ""
    secret_key: ""

# Code quality checks
# (Will auto-detect project type)

# Auto-formatting
autoformat:
  enabled: true

# Git checkpointing
git_checkpoint:
  enabled: true

# Completion notifications
notifications:
  enabled: true
  mac_notification: true
  tts: true
---

# Dev Plugin Settings

This configuration enables all dev-plugin features including the new observability tracking.

## Observability

Session data will be saved to `.claude/observability/sessions/` with detailed metrics:
- Tool usage tracking
- File operations
- Session duration
- Summary statistics

No external services - everything stays local on your machine.

## To Enable Langfuse Later

1. Install: `pip install langfuse`
2. Set up local Langfuse (see plugin README)
3. Update `langfuse.enabled: true` and add your API keys
