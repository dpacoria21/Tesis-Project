import json
import pytest
from tutor.models import Corpus
from tutor.reference import solve
from tutor.retrieval import HybridRetriever, IndexUnavailable
from tests.doubles import TestEmbeddings


def test_corpus_independent_expected_outputs():
    corpus = Corpus.model_validate_json(open("corpus/demo.json",encoding="utf-8").read())
    expected = {"sim-01":["8","0","2999999999"],"sim-02":["3","0","4"],"sim-03":["0 2","0 -1","0 0"],
        "sim-04":["2","0","0"],"arr-01":["5","-7","3000000000"],"arr-02":["2","1","2"],
        "arr-03":["1","0","4"],"arr-04":["9 5 4","-9","0 0"],"bus-01":["1","-1","1"],
        "bus-02":["2","-1","1"],"bus-03":["2","0","3"],"bus-04":["3","1","1000000","1000000"]}
    assert len(corpus.problems)==12 and len(corpus.concepts)==8
    for p in corpus.problems:
        assert len(p.tests)==len(expected[p.id])
        for case,wanted in zip(p.tests,expected[p.id]):
            assert case.output.split()==wanted.split()
            assert solve(p.id,case.input).split()==wanted.split()
        assert p.examples[0] == p.tests[0]
        assert p.provenance.url is None
        assert "pendiente" in p.provenance.review_status


def test_idempotent_ingest_and_shared_ids(service):
    initial = service.retriever.ingest()
    service.catalog.ingest(service.settings.corpus_path)
    second = service.retriever.ingest()
    assert initial == second
    collection=service.retriever.client.get_collection(second["collection"],embedding_function=None)
    assert collection.count()==80
    result=service.retriever.search("prefijos sumas fronteras",kinds=["concept"],max_level=2)
    assert result["lexical"] and result["vector"]
    ids={r["id"] for r in service.catalog.chunks()}
    assert {cid for cid,_ in result["lexical"]+result["vector"]} <= ids
    winner=result["hits"][0]
    expected=sum(1/(60+i) for ranking in [result["lexical"],result["vector"]] for i,(cid,_) in enumerate(ranking,1) if cid==winner["id"])
    assert winner["rrf_score"]==pytest.approx(expected)


def test_filters_and_internal_exclusion(service):
    result=service.retriever.search("suma",problem_id="arr-01",language="es",topic="acumulacion",kinds=["hint"],max_level=1)
    assert result["hits"]
    assert all(h["problem_id"]=="arr-01" and h["min_level"]<=1 and h["kind"]=="hint" for h in result["hits"])
    assert service.retriever.search("suma",language="xx")["hits"]==[]
    assert not service.retriever.search("editorial",kinds=["editorial"],max_level=3)["hits"]


def test_embedding_change_requires_explicit_rebuild(service):
    service.settings.embedding_revision="test-v2"
    assert not service.retriever.ready()
    with pytest.raises(IndexUnavailable): service.retriever.ingest()
    service.retriever.ingest(rebuild=True)
    assert service.retriever.ready()


def test_import_preserves_external_ids_and_urls(service,tmp_path):
    raw=service.catalog.problem("arr-01").model_dump()
    raw.update(id="external-fixture",difficulty_scale="external-not-comparable")
    # Fixture URL is deliberately on example.org and never described as scraped platform content.
    raw["provenance"].update(kind="external",platform="Test fixture",external_id="fixture-7",url="https://example.org/fixture-7")
    path=tmp_path/"import.jsonl"
    path.write_text(json.dumps({"kind":"problem","data":raw}),encoding="utf-8")
    service.catalog.ingest(path)
    service.catalog.ingest(path)
    imported=service.catalog.problem("external-fixture")
    assert imported.provenance.url=="https://example.org/fixture-7" and imported.provenance.external_id=="fixture-7"
    assert len(service.catalog.problems())==13 and not service.retriever.ready()


def test_reject_import_dangling_relationship_atomically(service,tmp_path):
    raw=service.catalog.problem("arr-01").model_dump()
    raw.update(id="bad",concept_ids=["absent"])
    path=tmp_path/"bad.json"
    path.write_text(json.dumps(dict(schema_version=1,problems=[raw],concepts=[])),encoding="utf-8")
    with pytest.raises(ValueError): service.catalog.ingest(path)
    assert len(service.catalog.problems())==12


def test_manifest_alone_does_not_claim_index_ready(service):
    manifest=json.loads(service.retriever.manifest_path.read_text(encoding="utf-8"))
    service.retriever.client.delete_collection(manifest["collection"])
    assert not service.retriever.ready()
    with pytest.raises(IndexUnavailable): service.retriever.search("suma")
