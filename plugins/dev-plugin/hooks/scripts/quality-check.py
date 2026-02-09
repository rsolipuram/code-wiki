#!/usr/bin/env python3
"""
Intelligent code quality checker for Claude Code.
Automatically detects project type and runs appropriate checks.

Supported languages:
- TypeScript/JavaScript (tsc, eslint)
- Python (mypy, ruff, pylint)
- Go (go build)
- Rust (cargo check)
- More coming soon...
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ProjectDetector:
    """Detects project type and available tools."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    def detect_typescript(self) -> bool:
        """Check if this is a TypeScript project."""
        return (self.project_dir / "tsconfig.json").exists()

    def detect_python(self) -> bool:
        """Check if this is a Python project."""
        indicators = [
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Pipfile",
            "poetry.lock"
        ]
        return any((self.project_dir / ind).exists() for ind in indicators)

    def detect_go(self) -> bool:
        """Check if this is a Go project."""
        return (self.project_dir / "go.mod").exists()

    def detect_rust(self) -> bool:
        """Check if this is a Rust project."""
        return (self.project_dir / "Cargo.toml").exists()

    def has_tool(self, tool: str) -> bool:
        """Check if a tool is available."""
        try:
            subprocess.run(
                ["which", tool],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False


class QualityChecker:
    """Runs quality checks for different project types."""

    def __init__(self, project_dir: Path, config: Dict):
        self.project_dir = project_dir
        self.config = config
        self.detector = ProjectDetector(project_dir)

    def check_typescript(self) -> Tuple[bool, str, int]:
        """Run TypeScript type checking."""
        if not self.detector.detect_typescript():
            return True, "", 0

        # Get custom command from config
        cmd = self.config.get("typescript", {}).get("command", "npx tsc --noEmit")

        try:
            result = subprocess.run(
                cmd.split(),
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return True, "", 0

            # Parse TypeScript errors
            output = result.stdout + result.stderr
            error_count = output.count("error TS")

            return False, output, error_count

        except FileNotFoundError:
            return True, "TypeScript not found, skipping check", 0
        except subprocess.TimeoutExpired:
            return False, "TypeScript check timed out", 0

    def check_python(self) -> Tuple[bool, str, int]:
        """Run Python type checking and linting."""
        if not self.detector.detect_python():
            return True, "", 0

        errors = []
        total_errors = 0

        # Check with mypy if available
        if self.detector.has_tool("mypy"):
            cmd = self.config.get("python", {}).get("mypy_command", "mypy .")
            try:
                result = subprocess.run(
                    cmd.split(),
                    cwd=self.project_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    output = result.stdout + result.stderr
                    error_count = output.count("error:")
                    errors.append(f"MyPy found {error_count} type error(s):\n{output}")
                    total_errors += error_count
            except Exception as e:
                errors.append(f"MyPy check failed: {e}")

        # Check with ruff if available
        if self.detector.has_tool("ruff"):
            cmd = self.config.get("python", {}).get("ruff_command", "ruff check .")
            try:
                result = subprocess.run(
                    cmd.split(),
                    cwd=self.project_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    output = result.stdout + result.stderr
                    errors.append(f"Ruff linting issues:\n{output}")
                    total_errors += 1
            except Exception:
                pass

        if errors:
            return False, "\n\n".join(errors), total_errors

        return True, "", 0

    def check_go(self) -> Tuple[bool, str, int]:
        """Run Go build check."""
        if not self.detector.detect_go():
            return True, "", 0

        if not self.detector.has_tool("go"):
            return True, "Go not found, skipping check", 0

        try:
            result = subprocess.run(
                ["go", "build", "./..."],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return True, "", 0

            output = result.stdout + result.stderr
            error_count = output.count("error:")

            return False, output, error_count

        except Exception as e:
            return False, f"Go check failed: {e}", 0

    def check_rust(self) -> Tuple[bool, str, int]:
        """Run Rust cargo check."""
        if not self.detector.detect_rust():
            return True, "", 0

        if not self.detector.has_tool("cargo"):
            return True, "Cargo not found, skipping check", 0

        try:
            result = subprocess.run(
                ["cargo", "check"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return True, "", 0

            output = result.stdout + result.stderr
            error_count = output.count("error:")

            return False, output, error_count

        except Exception as e:
            return False, f"Rust check failed: {e}", 0

    def run_all_checks(self) -> Tuple[bool, List[str]]:
        """Run all applicable checks."""
        results = []
        all_passed = True

        # TypeScript
        passed, output, count = self.check_typescript()
        if not passed:
            all_passed = False
            results.append(f"TypeScript check failed with {count} error(s):\n{output}")
        elif output:
            results.append(output)

        # Python
        passed, output, count = self.check_python()
        if not passed:
            all_passed = False
            results.append(output)
        elif output:
            results.append(output)

        # Go
        passed, output, count = self.check_go()
        if not passed:
            all_passed = False
            results.append(f"Go build failed with {count} error(s):\n{output}")
        elif output:
            results.append(output)

        # Rust
        passed, output, count = self.check_rust()
        if not passed:
            all_passed = False
            results.append(f"Rust check failed with {count} error(s):\n{output}")
        elif output:
            results.append(output)

        return all_passed, results


def load_config(project_dir: Path) -> Dict:
    """Load configuration from .claude/dev-plugin.local.md."""
    config_file = project_dir / ".claude" / "dev-plugin.local.md"

    if not config_file.exists():
        return {"enabled": True}

    try:
        content = config_file.read_text()

        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    config = yaml.safe_load(parts[1])
                    return config if config else {"enabled": True}
                except ImportError:
                    # Fallback to simple parsing if PyYAML not available
                    config = {}
                    for line in parts[1].strip().split("\n"):
                        if ":" in line:
                            key, value = line.split(":", 1)
                            key = key.strip()
                            value = value.strip()

                            # Handle boolean values
                            if value.lower() in ("true", "false"):
                                value = value.lower() == "true"

                            config[key] = value

                    return config if config else {"enabled": True}
    except Exception:
        pass

    return {"enabled": True}


def main():
    """Main entry point."""
    # Read input JSON (available but not used for Stop event)
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        input_data = {}

    # Get project directory
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

    # Load configuration
    config = load_config(project_dir)

    # Check if enabled
    if not config.get("enabled", True):
        result = {
            "systemMessage": "Code quality checking disabled via settings"
        }
        print(json.dumps(result))
        sys.exit(0)

    # Detect project types
    detector = ProjectDetector(project_dir)
    detected_types = []

    if detector.detect_typescript():
        detected_types.append("TypeScript")
    if detector.detect_python():
        detected_types.append("Python")
    if detector.detect_go():
        detected_types.append("Go")
    if detector.detect_rust():
        detected_types.append("Rust")

    # No recognized project types
    if not detected_types:
        result = {
            "systemMessage": "No recognized project type detected (TypeScript, Python, Go, Rust), skipping quality checks"
        }
        print(json.dumps(result))
        sys.exit(0)

    # Run checks
    checker = QualityChecker(project_dir, config)
    all_passed, messages = checker.run_all_checks()

    if all_passed:
        # Success
        detected_str = ", ".join(detected_types)
        result = {
            "systemMessage": f"[OK] Code quality checks passed for: {detected_str}"
        }
        print(json.dumps(result))
        sys.exit(0)
    else:
        # Errors found - block and send to Claude
        error_message = "\n\n".join(messages)
        result = {
            "decision": "block",
            "reason": "Code quality checks failed",
            "systemMessage": f"Code quality issues detected. Please fix the following errors before stopping:\n\n{error_message}\n\nThe errors above must be resolved to ensure code quality."
        }
        print(json.dumps(result), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
