import hashlib
import json
from pathlib import Path
from tutor.models import Concept, Corpus, Problem


class Catalog:
    def __init__(self, store):
        self.store = store

    def ingest(self, path: Path):
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            body = {"schema_version":1,"problems":[r["data"] for r in rows if r["kind"] == "problem"],
                    "concepts":[r["data"] for r in rows if r["kind"] == "concept"]}
            if any(r["kind"] not in {"problem","concept"} for r in rows):
                raise ValueError("Tipo JSONL desconocido")
        else:
            body = json.loads(text)
        # Valida relaciones contra todo el catálogo, para importaciones incrementales.
        merged = {p.id:p.model_dump() for p in self.problems()}
        concepts = {c.id:c.model_dump() for c in self.concepts()}
        for p in body["problems"]:
            merged[p["id"]] = p
        for c in body["concepts"]:
            concepts[c["id"]] = c
        # Validación de duplicados en la entrada antes de mezclar.
        ids = [r["id"] for r in body["problems"]+body["concepts"]]
        if len(set(ids)) != len(ids):
            raise ValueError("Identificador duplicado en la importación")
        parsed = Corpus.model_validate(dict(schema_version=body.get("schema_version",1),problems=list(merged.values()),concepts=list(concepts.values())))
        with self.store.connect() as db:
            for kind, rows in [("problem",parsed.problems),("concept",parsed.concepts)]:
                db.executemany("INSERT INTO materials VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,body=excluded.body",
                               [(r.id,kind,r.model_dump_json()) for r in rows])
        return dict(problems=len(parsed.problems),concepts=len(parsed.concepts))

    def problems(self):
        with self.store.connect() as db:
            return [Problem.model_validate_json(r[0]) for r in db.execute("SELECT body FROM materials WHERE kind='problem' ORDER BY id")]

    def concepts(self):
        with self.store.connect() as db:
            return [Concept.model_validate_json(r[0]) for r in db.execute("SELECT body FROM materials WHERE kind='concept' ORDER BY id")]

    def problem(self, problem_id):
        with self.store.connect() as db:
            row = db.execute("SELECT body FROM materials WHERE kind='problem' AND id=?", (problem_id,)).fetchone()
        if not row:
            raise KeyError("Problema inexistente")
        return Problem.model_validate_json(row[0])

    def fingerprint(self):
        with self.store.connect() as db:
            payload = json.dumps([tuple(r) for r in db.execute("SELECT * FROM materials ORDER BY id")],ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def chunks(self):
        rows = []
        for p in self.problems():
            common = dict(problem_id=p.id,title=p.title,topics=p.topics,language=p.language,provenance=p.provenance.model_dump())
            rows.append(dict(common,id=f"{p.id}:statement",kind="statement",min_level=0,
                             text=p.public().model_dump_json(),step="statement"))
            for h in p.guidance:
                rows.append(dict(common,id=f"{p.id}:hint:{h.level}",kind="hint",min_level=h.level,text=h.text,step=h.step))
            rows.append(dict(common,id=f"{p.id}:editorial",kind="editorial",min_level=99,text=p.explanation+"\n"+p.reference_strategy,step="internal"))
        for c in self.concepts():
            rows.append(dict(id=c.id,problem_id="",title=c.title,topics=c.topics,language=c.language,kind="concept",
                             min_level=c.min_level,text=c.text,step=c.id,provenance=c.provenance.model_dump()))
        return rows
