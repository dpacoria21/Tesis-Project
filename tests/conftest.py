from pathlib import Path
import pytest
from tutor.config import Settings
from tutor.service import TutorService
from tests.doubles import TestEmbeddings, TestProvider


@pytest.fixture
def service(tmp_path):
    settings = Settings(_env_file=None,data_dir=tmp_path,corpus_path=Path("corpus/demo.json"),embedding_model="test-only-hash",embedding_revision="test-v1")
    service = TutorService(settings,TestProvider(),TestEmbeddings())
    service.retriever.ingest()
    yield service
    service.close()


@pytest.fixture
def student_session(service):
    student = service.store.create_student("Ana",["variables","bucles","condicionales","aritmetica"])
    session = service.start_session(student["id"],"arr-01")
    return student["id"],session["id"]
