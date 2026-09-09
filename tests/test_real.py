"""Pruebas reales explícitas; se distinguen de los dobles deterministas."""
from pathlib import Path
import pytest
from tutor.config import Settings
from tutor.models import Attempt
from tutor.service import TutorService


@pytest.mark.real_embeddings
def test_real_embeddings_reingestion_semantics_and_persistence(tmp_path):
    cfg=Settings(_env_file=None,data_dir=tmp_path,corpus_path=Path("corpus/demo.json"))
    service=TutorService(cfg)
    first=service.retriever.ingest()
    second=service.retriever.ingest()
    assert first==second and first["dimension"]==384 and first["count"]==80
    result=service.retriever.search("sumas de prefijos cancelar parte compartida",kinds=["concept"],max_level=2)
    assert result["lexical"] and result["vector"]
    assert result["hits"][0]["id"]=="c-prefijos"
    semantic=service.retriever.search("find a threshold in a sorted sequence",kinds=["concept"],max_level=2)
    assert "c-binaria" in [cid for cid,_ in semantic["vector"][:3]]
    restarted=TutorService(cfg)
    assert restarted.retriever.ready()
    again=restarted.retriever.search("sumas de prefijos cancelar parte compartida",kinds=["concept"],max_level=2)
    assert again["hits"][0]["id"]=="c-prefijos"


@pytest.mark.live
def test_live_multiturn_llm_and_real_embeddings(tmp_path):
    cfg=Settings(data_dir=tmp_path)
    if cfg.llm_provider=="disabled" or not cfg.llm_model:
        pytest.skip("Proveedor real pendiente de configuración por decisión del usuario")
    service=TutorService(cfg)
    assert cfg.llm_model in service.provider.models()
    service.retriever.ingest()
    sid=service.store.create_student("Integración real",["variables","bucles","condicionales","aritmetica"])["id"]
    session=service.start_session(sid,"arr-03")["id"]
    responses=[]
    for message in ["¿Qué quiere decir días consecutivos?","Mi idea compara todos los pares de días porque cualquier aumento me parece una subida. ¿Es válido?","Ahora comparo solo vecinos: para [1,3,3,2] cuento una subida, porque la igualdad no es un aumento estricto."]:
        responses.append(service.turn(sid,session,Attempt(message=message)))
    assert all(r.message and r.sources for r in responses)
    assert len({r.message for r in responses})==3
    restarted=TutorService(cfg)
    assert len(restarted.store.session(sid,session)["interactions"])==3
    assert all(r.checks.status=="no ejecutado" for r in responses)
    observations=restarted.store.profile(sid)["observations"]
    assert any(o["kind"]=="demostracion" and o["interaction_id"]==responses[-1].interaction_id
               and o["status"]=="provisional" for o in observations)
    assert all(o["status"]=="provisional" for o in observations)
    assert [r.help_level for r in responses]==[0,1,1]
    import json
    Path("reports").mkdir(exist_ok=True)
    Path("reports/live-test-session.json").write_text(json.dumps(dict(
        provider=cfg.llm_provider,model=cfg.llm_model,revision=cfg.llm_revision,
        session=restarted.store.session(sid,session),profile=restarted.store.profile(sid),
        review="Prueba integral automática; revisión docente pendiente"),ensure_ascii=False,indent=2),encoding="utf-8")
    service.close()
    restarted.close()


@pytest.mark.docker
def test_real_isolated_reference_execution(tmp_path):
    cfg=Settings(data_dir=tmp_path)
    service=TutorService(cfg)
    if not service.runner.availability()[0]:
        pytest.skip("Aislamiento Docker no disponible")
    p=service.catalog.problem("arr-01")
    result=service.runner.run(p.reference_cpp,p.tests)
    assert result.status=="supera las pruebas disponibles"
    hang=service.runner.run("int main(){for(;;){}}",p.tests[:1])
    assert hang.status=="no supera las pruebas disponibles"


@pytest.mark.docker
@pytest.mark.parametrize("code,expected",[
    ("int main(){return 0;}","no supera las pruebas disponibles"),
    ("this is not valid C++", "error de compilación"),
    ('#include <cstdio>\nint main(){for(int i=0;i<100000;i++) puts("exceso");}',"no supera las pruebas disponibles"),
])
def test_real_sandbox_rejects_bad_programs(tmp_path,code,expected):
    service=TutorService(Settings(data_dir=tmp_path))
    if not service.runner.availability()[0]:
        pytest.skip("Aislamiento Docker no disponible")
    result=service.runner.run(code,service.catalog.problem("arr-01").tests[:1])
    assert result.status==expected
    assert result.origin=="prototipo"
