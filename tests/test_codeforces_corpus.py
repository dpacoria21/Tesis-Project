"""Corpus oficial enlazado, adaptaciones propias y referencias internas verificables."""
from pathlib import Path
import shutil
import subprocess

import pytest

from tutor.corpus import Catalog
from tutor.models import Corpus
from tutor.storage import Store


CORPUS_PATH = Path(__file__).resolve().parents[1] / "corpus" / "codeforces.json"


@pytest.fixture(scope="module")
def codeforces_corpus():
    return Corpus.model_validate_json(CORPUS_PATH.read_text(encoding="utf-8"))


def test_codeforces_standalone_schema_and_provenance(codeforces_corpus):
    expected = {
        "cf-4A": ("4A", "https://codeforces.com/problemset/problem/4/A"),
        "cf-71A": ("71A", "https://codeforces.com/problemset/problem/71/A"),
    }
    assert {p.id for p in codeforces_corpus.problems} == set(expected)
    for problem in codeforces_corpus.problems:
        assert (problem.provenance.external_id, problem.provenance.url) == expected[problem.id]
        assert problem.provenance.kind == "external"
        assert problem.provenance.platform == "Codeforces"
        assert "revisión docente pendiente" in problem.provenance.review_status
        assert "Adaptación" in problem.statement
        assert problem.difficulty_scale != "demo_local_1_5"
        assert len(problem.guidance) == 4
        assert len({hint.step for hint in problem.guidance}) == 4
        assert problem.examples[0] == problem.tests[0]
        assert not {"reference_cpp", "explanation", "guidance", "tests"} & problem.public().model_dump().keys()


def test_codeforces_import_idempotent_and_preserves_demo(tmp_path):
    catalog = Catalog(Store(tmp_path / "catalog.sqlite3"))
    assert catalog.ingest(CORPUS_PATH) == {"problems": 2, "concepts": 2}
    original_fingerprint = catalog.fingerprint()
    catalog.ingest(CORPUS_PATH)
    assert catalog.fingerprint() == original_fingerprint

    catalog.ingest(CORPUS_PATH.with_name("demo.json"))
    assert catalog.ingest(CORPUS_PATH) == {"problems": 14, "concepts": 10}
    assert catalog.problem("arr-01").provenance.kind == "original_demo"
    for problem in (catalog.problem("cf-4A"), catalog.problem("cf-71A")):
        chunks = [row for row in catalog.chunks() if row["problem_id"] == problem.id]
        assert {row["min_level"] for row in chunks if row["kind"] == "hint"} == {0, 1, 2, 3}
        assert all(row["min_level"] > 3 for row in chunks if row["kind"] == "editorial")
        assert all(problem.reference_cpp not in row["text"] for row in chunks)


def test_codeforces_cases_match_independent_expected_results(codeforces_corpus):
    by_id = {p.id: p for p in codeforces_corpus.problems}
    watermelon = by_id["cf-4A"]
    # Enumerate actual legal splits instead of repeating the reference's shortcut.
    for case in watermelon.tests + watermelon.examples:
        weight = int(case.input)
        assert 1 <= weight <= 100
        possible = any(left % 2 == 0 and (weight-left) % 2 == 0 for left in range(1, weight))
        assert case.output.strip() == ("YES" if possible else "NO")

    words = by_id["cf-71A"]
    expected = [
        ["word", "l10n", "i18n", "p43s"],
        ["a"],
        ["abcdefghi", "abcdefghij", "a9k"],
        ["a10l", "z"],
        ["a98a"],
    ]
    assert len(words.tests) == len(expected)
    for case, wanted in zip(words.tests, expected):
        count, *items = case.input.split()
        assert len(items) == int(count)
        assert all(1 <= len(word) <= 100 and word.isascii() and word.islower() for word in items)
        assert case.output.splitlines() == wanted
    assert len(words.tests[-1].input.split()[1]) == 100


def test_original_cpp_references_against_boundaries(codeforces_corpus, tmp_path):
    # Only compile the two repository-authored references, never imported/student code.
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("g++ no está instalado; esquema e importación se verifican sin compilador")
    for problem in codeforces_corpus.problems:
        source = tmp_path / (problem.id + ".cpp")
        binary = tmp_path / (problem.id + ".exe")
        source.write_text(problem.reference_cpp, encoding="utf-8")
        subprocess.run(
            [compiler, "-std=c++17", "-O2", str(source), "-o", str(binary)],
            check=True, capture_output=True, timeout=30,
        )
        cases = [(case.input, case.output) for case in problem.tests + problem.examples]
        if problem.id == "cf-4A":
            for weight in range(1, 101):
                possible = any(
                    left % 2 == 0 and (weight-left) % 2 == 0
                    for left in range(1, weight)
                )
                cases.append((f"{weight}\n", "YES\n" if possible else "NO\n"))
        elif problem.id == "cf-71A":
            # Every allowed length and the maximum batch size, with distinct endpoints.
            items = ["a" if length == 1 else "a" + "b"*(length-2) + "z" for length in range(1, 101)]
            expected = items[:10] + [f"a{interior}z" for interior in range(9, 99)]
            cases.append(("100\n" + "\n".join(items) + "\n", "\n".join(expected) + "\n"))
        for raw, expected in cases:
            result = subprocess.run(
                [str(binary)], input=raw, text=True, capture_output=True, check=True, timeout=3,
            )
            assert result.stdout.splitlines() == expected.splitlines(), (problem.id, raw)
