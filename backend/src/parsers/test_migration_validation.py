from pathlib import Path

from src.parsers.extractor import extract_entities


def test_t25_parser_parity_baseline_names(tmp_path: Path) -> None:
    """T2.5 parity artifact: verify canonical entities are still extracted."""
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "service.py").write_text(
        "class Greeter:\n"
        "    def hello(self):\n"
        "        helper()\n\n"
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (repo / "client.ts").write_text(
        "class Service {\n"
        "  run() { helper(); }\n"
        "}\n"
        "function helper() { return 1; }\n",
        encoding="utf-8",
    )
    (repo / "engine.rs").write_text(
        "struct Engine;\n"
        "impl Engine {\n"
        "    fn run(&self) { helper(); }\n"
        "}\n"
        "fn helper() {}\n",
        encoding="utf-8",
    )

    entities = extract_entities(str(repo))
    scoped_entities = [e for e in entities if e.entity_type != "module"]
    qnames = {e.qualified_name for e in scoped_entities}

    expected_qname_suffixes = {
        "service.Greeter",
        "service.Greeter.hello",
        "service.helper",
        "client.Service",
        "client.Service.run",
        "client.helper",
        "engine.Engine",
        "engine.Engine.run",
        "engine.helper",
    }

    assert all(any(name.endswith(suffix) for name in qnames) for suffix in expected_qname_suffixes)

    baseline_count = len(expected_qname_suffixes)
    tolerance = max(1, int(baseline_count * 0.10))
    assert abs(len(scoped_entities) - baseline_count) <= tolerance

    helper_callers = [e for e in scoped_entities if "helper" in e.calls]
    assert helper_callers, "Expected at least one helper call edge from extracted entities"


def test_t51_pipeline_smoke_extract_entities_filtered_repo(tmp_path: Path) -> None:
    """T5.1 smoke artifact: extraction pipeline completes and filters build outputs."""
    repo = tmp_path / "smoke-repo"
    src = repo / "src"
    dist = repo / "dist"
    src.mkdir(parents=True)
    dist.mkdir(parents=True)

    (src / "app.py").write_text(
        "from util import helper\n\n"
        "def run():\n"
        "    helper()\n",
        encoding="utf-8",
    )
    (src / "util.py").write_text(
        "def helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    (dist / "bundle.js").write_text("function x(){return 1};" * 800, encoding="utf-8")

    entities = extract_entities(str(repo), build_output_dirs=("dist",))
    assert entities, "Expected non-empty entity extraction for smoke repository"

    file_paths = {Path(e.file_path).as_posix() for e in entities}
    assert all("/dist/" not in path for path in file_paths)

    functions = [e for e in entities if e.entity_type in {"function", "method"}]
    assert any(e.name == "run" for e in functions)
    assert any(e.name == "helper" for e in functions)


def test_rust_trait_impl_owner_resolves_to_concrete_type(tmp_path: Path) -> None:
    repo = tmp_path / "rust-owner-repo"
    repo.mkdir()
    (repo / "engine.rs").write_text(
        "trait Runner { fn run(&self); }\n"
        "struct Engine;\n"
        "impl Runner for Engine {\n"
        "    fn run(&self) { helper(); }\n"
        "}\n"
        "fn helper() {}\n",
        encoding="utf-8",
    )

    entities = extract_entities(str(repo))
    qnames = {e.qualified_name for e in entities if e.entity_type == "method"}
    assert "engine.Engine.run" in qnames
    assert "engine.Runner.run" not in qnames


def test_rust_inherent_impl_owner_not_affected_by_for_loop(tmp_path: Path) -> None:
    repo = tmp_path / "rust-loop-owner-repo"
    repo.mkdir()
    (repo / "engine.rs").write_text(
        "struct Engine;\n"
        "impl Engine {\n"
        "    fn run(&self) {\n"
        "        for item in [1, 2, 3] { let _x = item; }\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    entities = extract_entities(str(repo))
    qnames = {e.qualified_name for e in entities if e.entity_type == "method"}
    assert "engine.Engine.run" in qnames
    assert "engine.item.run" not in qnames
