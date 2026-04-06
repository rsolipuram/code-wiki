"""Layer 0: Repo Reconnaissance Agent.

Scans a repository's file tree to produce a RepoFingerprint with zero LLM calls.
Targets: < 2 seconds for 50k LOC repositories.
"""

import json
import logging
from pathlib import Path
from typing import Counter

from src.recon.config_detector import detect_configs
from src.recon.fingerprint import RepoFingerprint

logger = logging.getLogger(__name__)

# Map file extension → language name
_EXT_TO_LANG: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".scala": "Scala",
    ".r": "R",
    ".R": "R",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    ".less": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".lua": "Lua",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".nim": "Nim",
    ".cr": "Crystal",
    ".jl": "Julia",
    ".tf": "HCL",
    ".tfvars": "HCL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
}

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "out", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "target", "vendor", ".gradle", ".idea",
    ".vscode", "*.egg-info",
}

# Tools detected from presence of certain config files
_TOOL_INDICATORS: dict[str, str] = {
    "github_actions": "GitHub Actions",
    "circleci": "CircleCI",
    "jenkins": "Jenkins",
    "travis_ci": "Travis CI",
    "gitlab_ci": "GitLab CI",
    "docker_compose": "Docker Compose",
    "dockerfile": "Docker",
    "terraform": "Terraform",
    "helm": "Helm",
    "kubernetes": "Kubernetes",
    "npm": "npm",
    "yarn": "Yarn",
    "pnpm": "pnpm",
    "python_pyproject": "Poetry/Hatch",
    "python_requirements": "pip",
    "pipenv": "Pipenv",
    "go_modules": "Go Modules",
    "cargo": "Cargo",
    "maven": "Maven",
    "gradle": "Gradle",
    "jest": "Jest",
    "pytest": "pytest",
    "typescript": "TypeScript",
}


def run(repo_path: str) -> RepoFingerprint:
    """Scan a repository and produce a RepoFingerprint.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        RepoFingerprint (immutable, JSON-serializable).
    """
    root = Path(repo_path)
    lang_counter: Counter[str] = Counter()
    file_count = 0
    loc = 0

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(skip in file_path.parts for skip in _SKIP_DIRS):
            continue

        ext = file_path.suffix.lower()
        lang = _EXT_TO_LANG.get(ext) or _EXT_TO_LANG.get(file_path.suffix)
        if lang:
            lang_counter[lang] += 1
            file_count += 1
            if file_count % 1000 == 0:
                logger.debug("RepoRecon: scanned %d files so far...", file_count)
            # Count lines (fast read)
            try:
                loc += sum(1 for _ in file_path.open("rb"))
            except OSError:
                pass

    # Sort languages by file count (descending)
    languages = [lang for lang, _ in lang_counter.most_common()]
    primary_language = languages[0] if languages else None

    # Detect config files
    config_files = detect_configs(repo_path)
    logger.debug("RepoRecon: detected %d config types", len(config_files))

    # Derive tools list from detected configs
    tools_present = sorted({
        _TOOL_INDICATORS[cfg_type]
        for cfg_type in config_files
        if cfg_type in _TOOL_INDICATORS
    })

    # Heuristic system type classification
    system_type, manifest_data = _classify_system(root, config_files, languages)

    # Extract project metadata from manifests
    project_name, project_description, entry_points = _extract_project_metadata(
        root, manifest_data
    )

    # Detect source roots and build output directories
    source_roots = _detect_source_roots(root, config_files)
    build_output_dirs = _detect_build_outputs(root, config_files)
    logger.debug(
        "RepoRecon metadata: project=%s, primary_lang=%s, source_roots=%s, build_dirs=%s",
        project_name or "(none)", primary_language, source_roots, build_output_dirs,
    )

    fingerprint = RepoFingerprint(
        languages=languages,
        primary_language=primary_language,
        system_type=system_type,
        tools_present=tools_present,
        file_count=file_count,
        loc=loc,
        config_files=config_files,
        project_name=project_name,
        project_description=project_description,
        source_roots=source_roots,
        build_output_dirs=build_output_dirs,
        entry_points=entry_points,
    )

    logger.info(
        "RepoRecon complete: %d files, %d LOC, primary=%s, system_type=%s",
        file_count, loc, primary_language, system_type,
    )
    return fingerprint


def _classify_system(
    root: Path,
    config_files: dict[str, list[str]],
    languages: list[str],
) -> tuple[str, dict]:
    """Classify the repository system type from structural signals.

    Returns (system_type, manifest_data) where manifest_data is the parsed
    package manifest (if any) for reuse by _extract_project_metadata.
    """
    manifest_data: dict = {}

    # Microservices: multiple Dockerfiles at different depths, or helm charts
    dockerfiles = config_files.get("dockerfile", [])
    if len(dockerfiles) > 2 or "helm" in config_files:
        return "microservices", manifest_data

    # Library: has setup.py / pyproject.toml / Cargo.toml / package.json at root but no Dockerfile
    root_files = {p.name for p in root.iterdir() if p.is_file()}
    if any(f in root_files for f in {"setup.py", "pyproject.toml", "Cargo.toml"}) and not dockerfiles:
        return "library", manifest_data

    if "package.json" in root_files and not dockerfiles:
        pkg_json = root / "package.json"
        try:
            manifest_data = json.loads(pkg_json.read_text())
            if "bin" in manifest_data:
                return "cli", manifest_data
            return "library", manifest_data
        except Exception:
            return "library", manifest_data

    # CLI: bin/ directory or Makefile-heavy
    if (root / "bin").is_dir() or "makefile" in config_files:
        return "cli", manifest_data

    # Default: monolith
    return "monolith", manifest_data


def _extract_project_metadata(
    root: Path,
    manifest_data: dict,
) -> tuple[str, str, tuple[str, ...]]:
    """Extract project name, description, and entry points from manifests.

    Checks package.json, pyproject.toml, Cargo.toml, go.mod in priority order.
    Returns (project_name, project_description, entry_points).
    """
    project_name = ""
    project_description = ""
    entry_points: list[str] = []

    # If we already have manifest_data from _classify_system (package.json)
    if manifest_data:
        project_name = manifest_data.get("name", "")
        project_description = manifest_data.get("description", "")
        # Entry points from package.json
        if "main" in manifest_data:
            entry_points.append(manifest_data["main"])
        if "bin" in manifest_data:
            bin_val = manifest_data["bin"]
            if isinstance(bin_val, str):
                entry_points.append(bin_val)
            elif isinstance(bin_val, dict):
                entry_points.extend(bin_val.values())
        if "exports" in manifest_data and isinstance(manifest_data["exports"], str):
            entry_points.append(manifest_data["exports"])
        return project_name, project_description, tuple(entry_points)

    # Try package.json if not already read
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text())
            project_name = pkg.get("name", "")
            project_description = pkg.get("description", "")
            if "main" in pkg:
                entry_points.append(pkg["main"])
            if "bin" in pkg:
                bin_val = pkg["bin"]
                if isinstance(bin_val, str):
                    entry_points.append(bin_val)
                elif isinstance(bin_val, dict):
                    entry_points.extend(bin_val.values())
            return project_name, project_description, tuple(entry_points)
        except Exception:
            pass

    # Try pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib
            data = tomllib.loads(pyproject.read_text())
            project = data.get("project", {})
            project_name = project.get("name", "")
            project_description = project.get("description", "")
            scripts = project.get("scripts", {})
            entry_points.extend(scripts.values())
            return project_name, project_description, tuple(entry_points)
        except Exception:
            pass

    # Try Cargo.toml
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        try:
            import tomllib
            data = tomllib.loads(cargo.read_text())
            package = data.get("package", {})
            project_name = package.get("name", "")
            project_description = package.get("description", "")
            return project_name, project_description, ()
        except Exception:
            pass

    # Try go.mod (name only)
    gomod = root / "go.mod"
    if gomod.is_file():
        try:
            first_line = gomod.read_text().splitlines()[0]
            if first_line.startswith("module "):
                project_name = first_line.split()[-1].split("/")[-1]
            return project_name, "", ()
        except Exception:
            pass

    return project_name, project_description, tuple(entry_points)


def _detect_source_roots(
    root: Path,
    config_files: dict[str, list[str]],
) -> tuple[str, ...]:
    """Detect source root directories (deterministic, no LLM).

    Checks tsconfig rootDir, then falls back to src/lib/ heuristic.
    """
    source_roots: list[str] = []

    # Check tsconfig.json for rootDir
    tsconfig = root / "tsconfig.json"
    if tsconfig.is_file():
        try:
            data = json.loads(tsconfig.read_text())
            root_dir = data.get("compilerOptions", {}).get("rootDir")
            if root_dir:
                source_roots.append(root_dir.strip("./"))
        except Exception:
            pass

    # Heuristic: common source directories that contain code files
    for candidate in ("src", "lib", "app", "packages", "ui", "frontend", "client"):
        candidate_path = root / candidate
        if candidate_path.is_dir() and candidate not in source_roots:
            # Verify it contains code files (not just config)
            has_code = any(
                f.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}
                for f in candidate_path.rglob("*")
                if f.is_file()
            )
            if has_code:
                source_roots.append(candidate)

    return tuple(source_roots)


def _detect_build_outputs(
    root: Path,
    config_files: dict[str, list[str]],
) -> tuple[str, ...]:
    """Detect build output directories (deterministic, no LLM).

    Checks tsconfig outDir, .gitignore patterns, and scans for minified files.
    Avoids false positives by checking that candidate dirs don't contain
    significant source code (a bundled .min.js inside a source tree is not
    evidence that the entire tree is build output).
    """
    build_dirs: set[str] = set()

    # tsconfig outDir
    tsconfig = root / "tsconfig.json"
    if tsconfig.is_file():
        try:
            data = json.loads(tsconfig.read_text())
            out_dir = data.get("compilerOptions", {}).get("outDir")
            if out_dir:
                build_dirs.add(out_dir.strip("./"))
        except Exception:
            pass

    # Well-known build output directories
    for candidate in ("dist", "build", "out", ".next", "coverage", "target"):
        if (root / candidate).is_dir():
            build_dirs.add(candidate)

    # Scan for directories containing minified files (avg line length > 300).
    # Only flag the top-level dir as build output when it has MANY minified
    # files relative to source — a few vendored .min.js in an otherwise
    # source-heavy tree is NOT a build output directory.
    _SOURCE_EXTS = {".py", ".ts", ".tsx", ".rs", ".go", ".java", ".jsx"}
    minified_dirs: dict[str, int] = {}  # top-dir → count of minified files
    for js_file in root.rglob("*.js"):
        if any(skip in js_file.parts for skip in _SKIP_DIRS):
            continue
        try:
            chunk = js_file.read_bytes()[:4096]
            lines = chunk.split(b"\n")
            is_minified = False
            if len(lines) <= 2 and len(chunk) > 10240:
                is_minified = True
            elif lines:
                avg_len = len(chunk) / max(len(lines), 1)
                if avg_len > 300:
                    is_minified = True
            if is_minified:
                rel = js_file.relative_to(root)
                top = rel.parts[0]
                minified_dirs[top] = minified_dirs.get(top, 0) + 1
        except (OSError, ValueError):
            pass

    # Only add a minified-file dir if it doesn't contain real source files.
    for top, _count in minified_dirs.items():
        top_path = root / top
        has_source = False
        for src_ext in _SOURCE_EXTS:
            if any(True for _ in top_path.rglob(f"*{src_ext}")):
                has_source = True
                break
        if not has_source:
            build_dirs.add(top)

    return tuple(sorted(build_dirs))
