"""Config file detector for the Repo Reconnaissance layer.

Identifies common infrastructure, build, and package management config files
by filename and path patterns. Zero LLM calls.
"""

import fnmatch
from pathlib import Path


# Pattern → config type mappings (ordered: more specific first)
_PATTERNS: list[tuple[str, str]] = [
    # CI/CD
    (".github/workflows/*.yml", "github_actions"),
    (".github/workflows/*.yaml", "github_actions"),
    (".circleci/config.yml", "circleci"),
    ("Jenkinsfile", "jenkins"),
    (".travis.yml", "travis_ci"),
    ("bitbucket-pipelines.yml", "bitbucket_pipelines"),
    ("azure-pipelines.yml", "azure_devops"),
    (".gitlab-ci.yml", "gitlab_ci"),

    # Containerization
    ("Dockerfile", "dockerfile"),
    ("Dockerfile.*", "dockerfile"),
    ("docker-compose.yml", "docker_compose"),
    ("docker-compose.yaml", "docker_compose"),
    ("docker-compose.*.yml", "docker_compose"),

    # IaC
    ("*.tf", "terraform"),
    ("*.tfvars", "terraform"),
    ("helm/**", "helm"),
    ("Chart.yaml", "helm"),
    ("*.k8s.yaml", "kubernetes"),
    ("kubernetes/**/*.yaml", "kubernetes"),
    ("k8s/**/*.yaml", "kubernetes"),
    ("deploy/**/*.yaml", "kubernetes"),

    # Package manifests
    ("package.json", "npm"),
    ("package-lock.json", "npm"),
    ("yarn.lock", "yarn"),
    ("pnpm-lock.yaml", "pnpm"),
    ("pyproject.toml", "python_pyproject"),
    ("requirements*.txt", "python_requirements"),
    ("setup.py", "python_setuptools"),
    ("setup.cfg", "python_setuptools"),
    ("Pipfile", "pipenv"),
    ("go.mod", "go_modules"),
    ("go.sum", "go_modules"),
    ("Cargo.toml", "cargo"),
    ("Cargo.lock", "cargo"),
    ("pom.xml", "maven"),
    ("build.gradle", "gradle"),
    ("build.gradle.kts", "gradle"),
    ("Gemfile", "bundler"),
    ("composer.json", "composer"),

    # Linting / formatting
    (".eslintrc*", "eslint"),
    ("eslint.config.*", "eslint"),
    (".prettierrc*", "prettier"),
    ("tsconfig*.json", "typescript"),

    # Testing
    ("jest.config.*", "jest"),
    ("pytest.ini", "pytest"),
    ("pyproject.toml", "pytest"),  # may overlap, listed for completeness
    ("vitest.config.*", "vitest"),

    # Misc
    ("Makefile", "makefile"),
    ("*.env.example", "dotenv"),
    (".env.example", "dotenv"),
]


def detect_configs(repo_path: str) -> dict[str, list[str]]:
    """Scan a repository and categorize all detected config files.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        Dict mapping config_type → list of matching relative file paths.
        Handles repos with no matching configs gracefully (empty dict).
    """
    root = Path(repo_path)
    result: dict[str, list[str]] = {}

    if not root.exists():
        return result

    # Collect all files (no depth limit — but skip very deep dirs)
    all_files: list[Path] = []
    try:
        for p in root.rglob("*"):
            if p.is_file() and not any(
                part.startswith(".") and part not in {".github", ".circleci", ".gitlab-ci.yml"}
                for part in p.parts[len(root.parts) + 1:]
                if part != p.name  # allow hidden root-level files like .travis.yml
            ):
                all_files.append(p)
    except PermissionError:
        pass

    for file_path in all_files:
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        for pattern, config_type in _PATTERNS:
            if _matches(rel, pattern):
                result.setdefault(config_type, []).append(rel)
                break  # first match wins per file

    return result


def _matches(rel_path: str, pattern: str) -> bool:
    """Check if a relative path matches a glob pattern."""
    # Match against the full path or just the filename
    filename = rel_path.split("/")[-1]
    return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(filename, pattern)
