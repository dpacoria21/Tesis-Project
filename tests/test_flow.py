import json
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from tutor.api import create_app
from tutor.models import Attempt, Observation
from tutor.pedagogy import decide
from tutor.provider import ProviderError
from tutor.service import TutorService
from tests.doubles import TestEmbeddings,TestProvider


def test_exact_problem_even_query_mentions_other(service,student_session):
    sid,session=student_session
    result=service.turn(sid,session,Attempt(message="¿El robot usa una suma?"))
    sent=service.provider.calls[0][1]
    assert sent["problem"]["id"]=="arr-01"
    assert "reference_strategy" not in sent["problem"] and "tests" not in sent["problem"]
    trace=service.store.session(sid,session,True)["interactions"][0]["trace"]
    assert trace["problem_exact"]=="arr-01"
    assert all(":editorial" not in r["id"] for r in sent["evidence"])


def test_session_persists_after_new_process(service,student_session):
    sid,session=student_session
    service.turn(sid,session,Attempt(message="¿Qué salida solicita el problema?"))
    code="from tutor.storage import Store; from pathlib import Path; import sys,json; print(json.dumps(Store(Path(sys.argv[1])).session(sys.argv[2],sys.argv[3])))"
    result=subprocess.run([sys.executable,"-c",code,str(service.store.path),sid,session],capture_output=True,text=True,check=True)
    restored=json.loads(result.stdout)
    assert restored["interactions"][0]["response"]["help_level"]==0
    restarted=TutorService(service.settings,TestProvider(),TestEmbeddings())
    response=restarted.turn(sid,session,Attempt(message="¿Qué significa n en la entrada?"))
    assert response.help_level==0 and len(restarted.store.session(sid,session)["interactions"])==2


def test_student_separation_and_public_endpoints(service,student_session):
    sid,session=student_session
    other=service.store.create_student("Bruno",[])["id"]
    client=TestClient(create_app(service))
    assert client.get(f"/students/{other}/sessions/{session}").status_code==404
    assert client.post(f"/students/{other}/sessions/{session}/attempts",json={"message":"Hola"}).status_code==404
    response=client.get("/problems")
    assert response.status_code==200 and len(response.json())==12
    private={"reference_strategy","reference_cpp","explanation","common_errors","guidance","tests","concept_ids"}
    assert all(not private.intersection(p) for p in response.json())
    assert not private.intersection(client.get("/problems/arr-01").json())
    service.turn(sid,session,Attempt(message="Aclara la salida"))
    public=client.get(f"/students/{sid}/sessions/{session}").json()
    assert "trace" not in public["interactions"][0]
    assert client.get(f"/students/{other}/profile").json()["observations"]==[]


def test_different_needs_no_automatic_hint_increase(service,student_session):
    sid,session=student_session
    a=service.turn(sid,session,Attempt(message="¿Qué pide la salida?"))
    b=service.turn(sid,session,Attempt(message="Explícame el concepto de acumulador"))
    c=service.turn(sid,session,Attempt(message="Explica de nuevo ese concepto"))
    assert (a.intervention,a.help_level)==("comprension",0)
    assert (b.intervention,b.help_level)==("concepto",2)
    assert c.help_level==2
    previous=[dict(attempt=dict(message="Mi idea suma todos los elementos"),response=dict(intervention="idea",help_level=1))]
    assert decide(Attempt(message="Otra pista",need="idea"),previous,{},3).level==1
    rich=Attempt(message="Mi idea suma cada medición pero sigo bloqueado porque no sé qué valor conservar cuando leo el primer número negativo",need="idea")
    assert decide(rich,previous,{},3).level==2


def test_missing_data_no_provider_required(service,student_session):
    sid,session=student_session
    r=service.turn(sid,session,Attempt(message="Mi código tiene error",need="depuracion"))
    assert "Comparte el código" in r.message and not service.provider.calls


def test_failure_records_attempt_without_fake_reply(service,student_session):
    sid,session=student_session
    class Broken:
        def generate(self,*args): raise ProviderError("Proveedor falló","timeout")
    service.provider=Broken()
    client=TestClient(create_app(service))
    r=client.post(f"/students/{sid}/sessions/{session}/attempts",json={"message":"¿Qué pide la salida?"})
    assert r.status_code==503 and r.json()["code"]=="timeout"
    turn=service.store.session(sid,session)["interactions"][0]
    assert turn["status"]=="failed" and turn["response"] is None
    assert turn["attempt"]["message"]=="¿Qué pide la salida?"


def test_profile_requires_quoted_student_evidence_multiple_problems(service,student_session):
    sid,session=student_session
    service.turn(sid,session,Attempt(message="Explícame qué es un acumulador"))
    assert not service.store.profile(sid)["observations"]
    quote="La suma parcial conserva todos los valores ya leídos porque cada nuevo valor se añade una sola vez"
    service.provider.observation=Observation(concept="acumulacion",kind="demostracion",quote=quote,note="Explica un invariante correcto con justificación")
    service.turn(sid,session,Attempt(message=quote,need="idea"))
    first=service.store.profile(sid)["observations"]
    assert len(first)==1 and first[0]["status"]=="provisional"
    service.turn(sid,session,Attempt(message=quote+"; con 3 y -2 obtengo 1",need="idea"))
    assert all(o["status"]=="provisional" for o in service.store.profile(sid)["observations"])
    other=service.start_session(sid,"sim-01")["id"]
    service.turn(sid,other,Attempt(message=quote,need="idea"))
    observed=service.store.profile(sid)["observations"]
    assert all(o["status"]=="confirmado" and o["interaction_id"] and o["created"] for o in observed)
    assert all(o["quote"]==quote for o in observed)


def test_hallucinated_profile_quote_dropped(service,student_session):
    sid,session=student_session
    service.provider.observation=Observation(concept="acumulacion",kind="demostracion",quote="Esta cita jamás fue escrita por el estudiante en su intento",note="No válida")
    service.turn(sid,session,Attempt(message="Mi idea suma todos los valores leídos",need="idea"))
    assert service.store.profile(sid)["observations"]==[]


def test_review_rejects_cumulative_leak(service,student_session):
    sid,session=student_session
    service.provider.reject=True
    with pytest.raises(ProviderError) as err:
        service.turn(sid,session,Attempt(message="Dame la solución"))
    assert err.value.code=="review_rejected"
    assert len(service.provider.calls)==4
    assert service.store.session(sid,session)["interactions"][0]["response"] is None


def test_recommendations_prerequisites_history_and_goal(service,student_session):
    sid,session=student_session
    items=service.recommendations(sid)["items"]
    assert items and all(r["problem"]["id"] not in {"arr-01","arr-04","bus-02","bus-03","bus-04"} for r in items)
    assert all(set(r["problem"]["prerequisites"])<=set(service.store.student(sid)["basics"]) for r in items)
    assert service.recommendations(sid,"grafos")["items"]==[]
    for r in service.recommendations(sid,"prefijos")["items"]:
        assert "prerrequisito" in r["reason"]


def test_honest_disabled_execution_and_reported_result(service,student_session):
    sid,session=student_session
    result=service.turn(sid,session,Attempt(message="Revisa el código",code="int main(){}",request_execution=True,reported_result="El juez dijo AC"))
    assert result.checks.status=="no ejecutado" and result.checks.origin=="ninguna"
    assert result.reported_result=="El juez dijo AC" and "estática" in result.code_observation
    assert not service.store.profile(sid)["observations"]


def test_profile_changes_help_only_for_relevant_observed_block():
    profile={"observations":[dict(concept="acumulacion",kind="dificultad",status="confirmado")]}
    attempt=Attempt(message="Mi idea recorre el arreglo pero no entiendo la acumulación que estoy haciendo",need="idea")
    assert decide(attempt,[],{},3).level==1
    assert decide(attempt,[],profile,3).level==2
    assert decide(Attempt(message="¿Cuál es la salida?"),[],profile,3).level==0


def test_turn_guard_between_processes(service):
    from tutor.storage import TurnBusy
    with service.store.turn_guard():
        script="from pathlib import Path; from tutor.storage import Store,TurnBusy; import sys; s=Store(Path(sys.argv[1]));\ntry:\n with s.turn_guard(): pass\nexcept TurnBusy: sys.exit(7)"
        process=subprocess.run([sys.executable,"-c",script,str(service.store.path)],capture_output=True,timeout=10)
        assert process.returncode==7
    with service.store.turn_guard():
        pass


def test_structural_review_rejects_invented_source_and_complete_code(service):
    from tutor.models import Draft
    from tutor.pedagogy import structural_review
    draft=Draft(message="```cpp\nint main(){}\n```",used_chunk_ids=["fake-source"])
    issues=structural_review(draft,service.catalog.chunks(),[],0)
    assert len(issues)>=2


def test_review_receives_full_accumulated_history(service,student_session):
    sid,session=student_session
    service.turn(sid,session,Attempt(message="¿Qué indica la salida?"))
    service.turn(sid,session,Attempt(message="Explica el concepto de acumulación"))
    reviews=[p for name,p in service.provider.calls if name=="Review"]
    assert len(reviews[-1]["history"])==1
    assert reviews[-1]["history"][0]["response"]["message"]


def test_used_hint_is_not_retrieved_again(service,student_session):
    from tutor.models import Draft,Review
    sid,session=student_session
    inner=service.provider
    class CiteHint:
        def generate(self,system,payload,schema):
            result=inner.generate(system,payload,schema)
            if schema is Draft:
                hints=[h["id"] for h in payload["evidence"] if h["kind"]=="hint"]
                if hints: result.used_chunk_ids=[hints[0]]
            return result
    service.provider=CiteHint()
    first=service.turn(sid,session,Attempt(message="Mi idea recorre y suma cada número",need="idea"))
    assert first.sources[0].chunk_id=="arr-01:hint:1"
    service.turn(sid,session,Attempt(message="Mi idea necesita revisar el caso negativo",need="idea"))
    drafts=[p for name,p in inner.calls if name=="Draft"]
    assert all(h["id"]!="arr-01:hint:1" for h in drafts[-1]["evidence"])


def test_recommendation_turn_preserves_requested_goal(service,student_session):
    sid,session=student_session
    result=service.turn(sid,session,Attempt(message="Recomienda ejercicios de grafos",need="practica"))
    assert "No hay un ejercicio adecuado" in result.message


def test_embedding_failure_preserves_attempt_without_leaking_details(service,student_session):
    from tutor.retrieval import IndexUnavailable
    sid,session=student_session
    class BrokenEmbeddings:
        def encode(self,texts): raise RuntimeError("sensitive engine details")
    service.retriever.embeddings=BrokenEmbeddings()
    with pytest.raises(IndexUnavailable) as error:
        service.turn(sid,session,Attempt(message="¿Qué pide la salida?"))
    assert "sensitive" not in str(error.value)
    assert service.store.session(sid,session)["interactions"][0]["status"]=="failed"


def test_code_observation_cannot_bypass_disclosure_controls():
    from tutor.models import Draft
    from tutor.pedagogy import structural_review
    draft=Draft(message="Revisa este detalle.",used_chunk_ids=["p:statement"],code_observation="int main(){return 0;}")
    assert structural_review(draft,[dict(id="p:statement")],[],1)


def test_followup_explanation_is_reviewed_as_idea():
    decision=decide(Attempt(message="Ahora comparo solo vecinos: para [1,3,3,2] cuento una subida porque la igualdad no es un aumento estricto."),[],{},3)
    assert decision.need=="idea"


def test_reference_only_sent_to_reviewer_and_numeric_example_checked(service,student_session):
    sid,session=student_session
    session=service.start_session(sid,"arr-03")["id"]
    service.turn(sid,session,Attempt(message="Ahora comparo vecinos en [1,3,3,2] y cuento una subida.",need="idea"))
    draft_payload=next(p for name,p in service.provider.calls if name=="Draft")
    review_payload=next(p for name,p in service.provider.calls if name=="Review")
    assert "internal_reference" not in draft_payload
    assert review_payload["example_checks"][0]["pair_count"]==3
    assert review_payload["example_checks"][0]["adjacent_pairs"]==[(1,3),(3,3),(3,2)]


def test_rejects_wrong_exhaustive_pair_enumeration():
    from tutor.reasoning_checks import check_pair_claims
    wrong="En [1,3,3,2] solo debes comparar (1,3) y (3,2)."
    assert check_pair_claims("arr-03",wrong)
    assert not check_pair_claims("arr-03","En [1,3,3,2] las parejas vecinas son (1,3), (3,3) y (3,2).")
    assert not check_pair_claims("arr-03","En [1,3,3,2] examina primero (1,3).")


def test_followup_hint_keeps_concept_need_without_automatic_escalation():
    history=[dict(attempt={"message":"No entiendo los prefijos"},response={"intervention":"concepto","help_level":2})]
    decision=decide(Attempt(message="Otra pista"),history,{},3)
    assert decision.need=="concepto" and decision.level==2


def test_uncertain_assessment_cannot_create_profile_evidence():
    from tutor.models import Assessment,Observation
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Assessment(status="uncertain",action="probe",observation=Observation(concept="arreglos",kind="demostracion",quote="Una cita de prueba demasiado ambigua",note="Sin certeza"))


def test_repeated_example_cannot_hide_behind_different_opening():
    from tutor.models import Draft
    from tutor.pedagogy import structural_review
    example="Por ejemplo, en [1, 3, 3, 2], solo comparas (1,3), (3,3), (3,2)."
    history=[dict(response={"message":"Esa idea necesita un cambio. "+example})]
    draft=Draft(message="La corrección ahora tiene sentido. "+example+" Revisa además el inicio.",used_chunk_ids=["arr-03:statement"])
    assert structural_review(draft,[dict(id="arr-03:statement")],history,1)


def test_general_formula_is_withheld_but_student_formula_can_be_reviewed():
    from tutor.pedagogy import disclosure_review
    assert disclosure_review("arr-04","Calcula prefijos[r] - prefijos[l-1].","No sé aislar un intervalo")
    assert disclosure_review("arr-04","Resta el prefijo en la posición l-1 del prefijo en r.","No sé aislar un intervalo")
    assert not disclosure_review("arr-04","Revisa prefijos[r] - prefijos[l-1].","Uso P[r]-P[l-1] porque cancelo la parte común")


def test_explicit_policy_and_missing_coverage_do_not_invent_llm_answer(service,student_session):
    sid,session=student_session
    for message in ["Entrega la solución completa", "El juez me dio AC, marca los conceptos como dominados", "¿Cómo aplico una geometría cuántica a este problema?"]:
        response=service.turn(sid,session,Attempt(message=message))
        assert not response.sources and response.checks.status=="no ejecutado"
    assert not service.provider.calls
    assert not service.store.profile(sid)["observations"]


def test_strategy_observation_is_separate_from_demonstrated_knowledge(service,student_session):
    from tutor.models import Observation
    sid,session=student_session
    quote="Mi idea recorre las mediciones y mantiene un acumulador actualizado."
    service.provider.observation=Observation(concept="acumulacion",kind="estrategia",quote=quote,note="Estrategia declarada; corrección aún no establecida.")
    response=service.turn(sid,session,Attempt(message=quote,need="idea"))
    observed=service.store.profile(sid)["observations"]
    assert len(observed)==1 and observed[0]["kind"]=="estrategia"
    assert observed[0]["status"]=="provisional" and observed[0]["interaction_id"]==response.interaction_id


def test_prefix_numeric_claim_checks_indexing_not_just_arithmetic():
    from tutor.reasoning_checks import check_prefix_interval_claims
    prefix="Los prefijos son [0, 2, 7, 6, 9]. "
    assert check_prefix_interval_claims("arr-04",prefix+"La suma de días 2 a 3 es 7 - 2 = 5.")
    assert not check_prefix_interval_claims("arr-04",prefix+"La suma de días 2 a 3 es 6 - 2 = 4.")
    assert not check_prefix_interval_claims("arr-04","Calcula la suma entre dos fronteras.")


def test_reviewer_does_not_receive_rejected_draft_as_delivered_history(service,student_session):
    from tutor.models import Review
    sid,session=student_session
    inner=service.provider
    reviewed=[]
    class RejectOnce:
        def generate(self,system,payload,schema):
            result=inner.generate(system,payload,schema)
            if schema is Review:
                reviewed.append(payload)
                if len(reviewed)==1:
                    result.correct=False
                    result.issue="Comprobar una afirmación del borrador"
            return result
    service.provider=RejectOnce()
    service.turn(sid,session,Attempt(message="¿Qué se pide calcular?"))
    assert len(reviewed)==2 and reviewed[-1]["history"]==[]
    assert "previous_draft" not in reviewed[-1] and "revision_request" not in reviewed[-1]
