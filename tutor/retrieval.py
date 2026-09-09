import json
import re
import unicodedata
from pathlib import Path
from rank_bm25 import BM25Okapi


class IndexUnavailable(RuntimeError):
    pass


def tokens(text):
    text = "".join(c for c in unicodedata.normalize("NFKD",text.lower()) if not unicodedata.combining(c))
    return re.findall(r"\w+",text)


class MultilingualEmbeddings:
    def __init__(self, settings):
        self.settings = settings
        self._model = None

    def encode(self, texts):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.settings.embedding_model,revision=self.settings.embedding_revision,
                device="cpu",trust_remote_code=False)
        return self._model.encode(texts,normalize_embeddings=True,show_progress_bar=False).tolist()


class HybridRetriever:
    def __init__(self, catalog, settings, embeddings=None):
        self.catalog, self.settings = catalog, settings
        self.embeddings = embeddings or MultilingualEmbeddings(settings)
        self.path = settings.data_dir / "chroma"
        self.manifest_path = settings.data_dir / "index.json"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            self._client = chromadb.PersistentClient(path=str(self.path),settings=ChromaSettings(anonymized_telemetry=False))
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def config(self):
        return dict(model=self.settings.embedding_model,revision=self.settings.embedding_revision,normalize=True,
                    chunk_schema=1,corpus=self.catalog.fingerprint())

    def ready(self):
        try:
            manifest=json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if manifest["config"] != self.config():
                return False
            collection=self.client.get_collection(manifest["collection"],embedding_function=None)
            return collection.count()==manifest["count"]
        except Exception:
            return False

    def ingest(self, rebuild=False):
        configuration = self.config()
        if self.manifest_path.exists():
            old = json.loads(self.manifest_path.read_text(encoding="utf-8"))["config"]
            changed_model = any(old.get(k) != configuration[k] for k in ["model","revision","normalize","chunk_schema"])
            if changed_model and not rebuild:
                raise IndexUnavailable("Cambió el modelo o fragmentación. Ejecuta ingest --rebuild.")
        rows = self.catalog.chunks()
        if not rows:
            raise IndexUnavailable("Catálogo vacío")
        # Colecciones nuevas por configuración permiten cambiar dimensiones sin borrar otros datos.
        import hashlib
        name = "corpus-"+hashlib.sha256(json.dumps({k:v for k,v in configuration.items() if k != "corpus"},sort_keys=True).encode()).hexdigest()[:16]
        collection = self.client.get_or_create_collection(name,metadata={"hnsw:space":"cosine"},embedding_function=None)
        vectors = self.embeddings.encode([r["text"] for r in rows])
        collection.upsert(ids=[r["id"] for r in rows],documents=[r["text"] for r in rows],embeddings=vectors,
            metadatas=[dict(chunk_id=r["id"],problem_id=r["problem_id"],kind=r["kind"],language=r["language"],min_level=r["min_level"]) for r in rows])
        stale = set(collection.get()["ids"]) - {r["id"] for r in rows}
        if stale:
            collection.delete(ids=sorted(stale))
        manifest = dict(config=configuration,collection=name,count=len(rows),dimension=len(vectors[0]))
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        temp.replace(self.manifest_path)
        return manifest

    def search(self, query, *, problem_id=None, kinds=None, topic=None, language=None, max_level=3, k=None, related_ids=None):
        try:
            return self._search(query,problem_id=problem_id,kinds=kinds,topic=topic,language=language,max_level=max_level,k=k,related_ids=related_ids)
        except IndexUnavailable:
            raise
        except Exception:
            raise IndexUnavailable("Falló la recuperación real. Revisa el modelo de embeddings y la integridad del índice; no se utilizó evidencia simulada.") from None

    def _search(self, query, *, problem_id=None, kinds=None, topic=None, language=None, max_level=3, k=None, related_ids=None):
        if not self.ready():
            raise IndexUnavailable("Índice ausente o desactualizado. Ejecuta tutor ingest.")
        rows = [r for r in self.catalog.chunks() if r["min_level"] <= max_level
            and (problem_id is None or r["problem_id"] == problem_id)
            and (not kinds or r["kind"] in kinds) and (topic is None or topic in r["topics"])
            and (language is None or r["language"] == language)
            and (related_ids is None or r["id"] in related_ids)]
        if not rows:
            return dict(hits=[],lexical=[],vector=[],strategy="BM25+Chroma/cosine/RRF")
        count = min(k or self.settings.retrieval_k,len(rows))
        bm25 = BM25Okapi([tokens(r["text"]) for r in rows])
        scores = bm25.get_scores(tokens(query))
        lexical = sorted([(r["id"],float(s)) for r,s in zip(rows,scores) if s>0], key=lambda x:(-x[1],x[0]))[:max(count,10)]
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        collection = self.client.get_collection(manifest["collection"],embedding_function=None)
        result = collection.query(query_embeddings=self.embeddings.encode([query]),n_results=min(max(count,10),len(rows)),
                                  where={"chunk_id":{"$in":[r["id"] for r in rows]}},include=["distances"])
        vector = list(zip(result["ids"][0],result["distances"][0]))
        fused = {}
        for ranking in [lexical,vector]:
            for rank,(chunk_id,_) in enumerate(ranking,1):
                fused[chunk_id] = fused.get(chunk_id,0)+1/(self.settings.rrf_constant+rank)
        by_id = {r["id"]:r for r in rows}
        hits = [dict(by_id[cid],rrf_score=score) for cid,score in sorted(fused.items(),key=lambda x:(-x[1],x[0]))[:count]]
        return dict(hits=hits,lexical=lexical,vector=vector,strategy="BM25+Chroma/cosine/RRF")
