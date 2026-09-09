"""Regresión determinista de los controles, no evaluación pedagógica del LLM.

Los proveedores controlados existen únicamente en este archivo de pruebas. Las
instantáneas copian el payload al producirse cada llamada para distinguir la
primera generación de cualquier modificación hecha durante la regeneración.
"""

from copy import deepcopy
import json
import re

import pytest
from pydantic import ValidationError

from tutor.models import Draft, Observation, Provenance, Review, Attempt
from tutor.pedagogy import Decision, disclosure_review, student_proposed_prefix_formula
from tutor.response_contract import ResponseContract, contract_review, select_contract
from tutor.reasoning_checks import check_array_examples, check_tie_update_claims


class RecordingProvider:
    def __init__(self, fallback, handler=None):
        self.fallback = fallback
        self.handler = handler
        self.calls = []

    def generate(self, system, payload, schema):
        self.calls.append({"schema": schema.__name__, "system": system, "payload": deepcopy(payload)})
        result = self.handler(system, payload, schema) if self.handler else None
        return result if result is not None else self.fallback.generate(system, payload, schema)

    def named(self, schema_name):
        return [call for call in self.calls if call["schema"] == schema_name]


def start(service, problem_id):
    student = service.store.create_student("Regresión de controles", ["variables", "bucles", "condicionales", "arreglos"])
    session = service.start_session(student["id"], problem_id)
    return student["id"], session["id"]


def record_calls(service, handler=None):
    provider = RecordingProvider(service.provider, handler)
    service.provider = provider
    return provider


def difficulty(message):
    return Observation(concept="arreglos", kind="dificultad", quote=message,
                       note="NOTA_PRIVADA_SENTINELA: el intento sustituye la primera aparición al empatar.")


def test_misconception_selects_contrast_before_first_generation_and_scopes_private_context(service):
    sid, session_id = start(service, "arr-02")
    service.turn(sid, session_id, Attempt(message="¿Las posiciones empiezan en cero?"))
    message = "Mi idea actualiza la posición siempre que el nuevo valor sea mayor o igual."
    observation = difficulty(message)
    service.provider.observation = observation
    provider = record_calls(service)

    result = service.turn(sid, session_id, Attempt(message=message))

    assert [call["schema"] for call in provider.calls] == ["Assessment", "Draft", "Review"]
    generation = provider.named("Draft")[0]
    review = provider.named("Review")[0]
    assessment = {"status": "misconception", "action": "correct", "student_quote": message}
    assert generation["payload"]["response_contract"]["mode"] == "contrast_attempt"
    assert "mostrar una consecuencia problemática" in generation["system"]
    assert generation["payload"]["student_assessment"] == assessment
    assert "revision_request" not in generation["payload"]
    assert "internal_reference" not in generation["payload"]
    for field in ("reference_strategy", "reference_cpp", "common_errors", "tests", "explanation"):
        assert field not in generation["payload"]["problem"]
    assert observation.note not in json.dumps(generation["payload"], ensure_ascii=False)
    assert "observation" not in generation["payload"]["student_assessment"]
    assert review["payload"]["student_assessment"] == assessment
    assert review["payload"]["response_contract"]["mode"] == "contrast_attempt"
    assert review["payload"]["internal_reference"]["strategy"] == service.catalog.problem("arr-02").reference_strategy
    trace = service.store.session(sid, session_id, internal=True)["interactions"][-1]["trace"]
    assert trace["student_assessment"]["observation"]["quote"] == message
    assert trace["response_contract"]["mode"] == "contrast_attempt"
    assert result.help_level == 1


@pytest.mark.parametrize("initial,hint_request,blocked", [
    ("No entiendo qué es un prefijo.", "Otra pista",
     "Sigo bloqueado: para [2,5,-1] mis prefijos son [0,2,7,6], pero no sé cómo aislar un intervalo."),
    ("No entiendo qué es una suma de prefijo. ¿Qué representa cada entrada?", "Otra pista por favor",
     "Sigo bloqueado: para [4,-2,7] calculé los prefijos [0,4,2,9], pero no sé qué parte se repite al intentar obtener un intervalo interior."),
])
def test_complete_prefix_history_reaches_n3_with_boundary_focus(service, initial, hint_request, blocked):
    sid, session_id = start(service, "arr-04")
    first = service.turn(sid, session_id, Attempt(message=initial))
    second = service.turn(sid, session_id, Attempt(message=hint_request))
    provider = record_calls(service)

    response = service.turn(sid, session_id, Attempt(message=blocked))

    assert (first.help_level, second.help_level, response.help_level) == (2, 2, 3)
    first_payload = provider.named("Draft")[0]["payload"]
    assert [turn["attempt"]["message"] for turn in first_payload["history"]] == [initial, hint_request]
    assert [turn["response"]["message"] for turn in first_payload["history"]] == [first.message, second.message]
    assert first_payload["response_contract"] == {"mode": "prefix_boundary", "focus_source_id": "arr-04:hint:3"}
    assert first_payload["focus_evidence"]["id"] == "arr-04:hint:3"
    assert first_payload["focus_evidence"] in first_payload["evidence"]
    assert first_payload["decision"]["level"] == 3
    assert "No indiques a la vez los dos prefijos" in provider.named("Draft")[0]["system"]
    assert provider.named("Review")[0]["payload"]["response_contract"]["mode"] == "prefix_boundary"
    assert len(service.store.session(sid, session_id)["interactions"]) == 3


def test_prefix_contract_uses_concept_for_imported_material_and_only_available_focus(service):
    original = service.catalog.problem("arr-04")
    imported = original.model_copy(update={
        "id": "imported-prefix-fixture",
        "provenance": Provenance(kind="external", platform="Fuente de prueba",
                                 external_id="fixture-prefix-1", url="https://example.test/prefix-1",
                                 review_status="Solo prueba determinista", license_note="Fixture de prueba"),
    })
    decision = Decision("concepto", 3, "Bloqueo concreto con intento nuevo")
    allowed = [{"id": "imported-prefix-fixture:statement"}, {"id": "imported-prefix-fixture:hint:3"}]
    contract = select_contract(decision, None, imported, allowed, "Mis prefijos son [0,4,2,9]; no sé aislar el intervalo.")
    assert contract.mode == "prefix_boundary"
    assert contract.focus_source_id == "imported-prefix-fixture:hint:3"
    without_hint = select_contract(decision, None, imported, allowed[:1], "No sé aislar el intervalo.")
    assert without_hint.mode == "prefix_boundary"
    assert without_hint.focus_source_id is None


def test_student_proposed_formula_uses_one_step_without_disabling_disclosure_guard(service):
    sid, session_id = start(service, "arr-04")
    service.turn(sid, session_id, Attempt(message="No entiendo qué es un prefijo."))
    service.turn(sid, session_id, Attempt(message="Otra pista"))
    provider = record_calls(service)
    proposed = "Sigo bloqueado: para una consulta propongo usar mis prefijos con P[r] - P[l-1], pero todavía no sé comprobar el caso que empieza en el primer elemento."

    response = service.turn(sid, session_id, Attempt(message=proposed))

    payload = provider.named("Draft")[0]["payload"]
    assert response.help_level == 3
    assert payload["response_contract"] == {"mode": "one_step", "focus_source_id": "arr-04:hint:3"}
    assert student_proposed_prefix_formula(proposed)
    candidate_formula = "Revisa tu propuesta P[r] - P[l-1] para un intervalo que empiece en el primer elemento."
    assert disclosure_review("arr-04", candidate_formula, proposed) == []
    assert disclosure_review("arr-04", candidate_formula, "No sé cómo aislar un intervalo con mis prefijos.")
    # Elegir otro contrato no da permiso general al generador para revelar fórmulas.
    assert provider.named("Review")[0]["payload"]["response_contract"]["mode"] == "one_step"


@pytest.mark.parametrize("rejection_kind", ["structural", "semantic_review"])
def test_regeneration_preserves_delivered_history_and_reviews_new_candidate(service, rejection_kind):
    sid, session_id = start(service, "arr-02")
    first = service.turn(sid, session_id, Attempt(message="¿Las posiciones empiezan en cero?"))
    message = "Mi idea actualiza la posición siempre que el nuevo valor sea mayor o igual."
    service.provider.observation = difficulty(message)
    rejected = (
        "```cpp\nint main(){return 0;}\n```" if rejection_kind == "structural" else
        "Tu planteamiento funciona correctamente: también puedes sustituir la posición cuando aparece otra altura igual."
    )
    corrected = "Con dos alturas máximas iguales, tu condición reemplaza la posición guardada. ¿Eso conserva la primera aparición que pide el enunciado?"
    issued_drafts = []

    def handler(system, payload, schema):
        if schema is Draft:
            text = rejected if not issued_drafts else corrected
            issued_drafts.append(text)
            return Draft(message=text, used_chunk_ids=[payload["evidence"][0]["id"]])
        if schema is Review and payload["draft"]["message"] == rejected:
            # Control semántico simulado: prueba que la decisión del revisor se
            # cumple aunque la paráfrasis no coincida con la regex literal.
            return Review(correct=False, relevant=True, supported=True, safe_disclosure=True,
                          non_repetitive=True, used_chunk_ids=payload["draft"]["used_chunk_ids"],
                          issue="La respuesta valida globalmente el criterio que pierde la primera aparición.")
        return None

    provider = record_calls(service, handler)
    response = service.turn(sid, session_id, Attempt(message=message))

    drafts = provider.named("Draft")
    reviews = provider.named("Review")
    assert len(drafts) == 2
    assert issued_drafts == [rejected, corrected]
    assert response.message == corrected
    assert "revision_request" not in drafts[0]["payload"]
    assert "revision_request" in drafts[1]["payload"]
    assert drafts[0]["payload"]["history"] == drafts[1]["payload"]["history"]
    assert drafts[0]["payload"]["decision"] == drafts[1]["payload"]["decision"]
    assert response.help_level == drafts[0]["payload"]["decision"]["level"] == 1
    for call in drafts:
        payload = call["payload"]
        assert "previous_draft" not in payload
        assert payload["response_contract"]["mode"] == "contrast_attempt"
        assert len(payload["history"]) == 1
        assert payload["history"][0]["response"]["message"] == first.message
        assert rejected not in json.dumps(payload, ensure_ascii=False)
    if rejection_kind == "structural":
        assert len(reviews) == 1
        assert "structural_corrections" in drafts[1]["payload"]
    else:
        assert not re.search(r"\btu idea es correcta\b", rejected, re.I)
        assert len(reviews) == 2
        assert reviews[0]["payload"]["draft"]["message"] == rejected
        assert drafts[1]["payload"]["rejected_checks"] == ["correct"]
    assert reviews[-1]["payload"]["draft"]["message"] == corrected
    persisted = service.store.session(sid, session_id, internal=True)
    assert len(persisted["interactions"]) == 2
    assert persisted["interactions"][-1]["response"]["message"] == corrected
    trace = persisted["interactions"][-1]["trace"]
    assert trace["reviews"][0]["candidate"]["message"] == rejected
    assert trace["reviews"][0]["issues"]
    assert trace["reviews"][1]["candidate"]["message"] == corrected
    assert trace["reviews"][1]["issues"] == []


def test_review_cannot_approve_all_checks_while_reporting_a_defect():
    verdict = dict(correct=True, relevant=True, supported=True, safe_disclosure=True,
                   non_repetitive=True, used_chunk_ids=["arr-02:statement"],
                   issue="La respuesta valida una condición que pierde la primera aparición.")
    with pytest.raises(ValidationError, match="aprobación completa requiere issue vacío"):
        Review.model_validate(verdict)
    rejection = Review.model_validate({**verdict, "correct": False})
    assert rejection.correct is False
    assert rejection.issue == verdict["issue"]
    acceptance = Review.model_validate({**verdict, "issue": ""})
    assert acceptance.correct is True
    assert acceptance.issue == ""


@pytest.mark.parametrize("content,proposed", [
    ("¿Qué significan r y l-1 cuando aparecen en los índices de los prefijos?", False),
    ("Estoy mirando P[r] y P[l-1], pero todavía no sé cómo relacionarlos.", False),
    ("Mi propuesta es P[fin] - P[inicio-1].", True),
    ("Propongo prefijo[derecha] − prefijo[izquierda − 1].", True),
    ("Mi propuesta es P[r] + P[l-1].", False),
    ("Mi propuesta mezcla P[r] - Q[l-1].", False),
])
def test_formula_permission_requires_a_complete_difference_of_the_same_prefix(content, proposed):
    assert student_proposed_prefix_formula(content) is proposed


@pytest.mark.parametrize("values,first_position,equal_update_position", [
    ([5, 5, 1], 1, 2),
    ([-2, -2, -5], 1, 2),
    ([1, 7, 3], 2, 2),
])
def test_first_max_checks_distinguish_equal_updates_only_when_requested(values, first_position, equal_update_position):
    message = f"Para {values} quiero conservar la primera aparición del máximo."
    ordinary = check_array_examples("arr-02", [message])
    reviewer_facts = check_array_examples("arr-02", [message], include_alternative=True)
    assert len(ordinary) == len(reviewer_facts) == 1
    assert ordinary[0]["values"] == values
    assert ordinary[0]["first_max_position"] == first_position
    assert "update_on_equal_position" not in ordinary[0]
    assert reviewer_facts[0]["first_max_position"] == first_position
    assert reviewer_facts[0]["update_on_equal_position"] == equal_update_position
    assert "no ejecución de código" in reviewer_facts[0]["origin"]


def test_public_worked_example_is_separate_from_private_reviewer_checks(service):
    sid, session_id = start(service, "arr-02")
    message = "Mi idea cambia la posición ante un valor mayor o igual; para [5,5,1] elegiría la posición 2."
    service.provider.observation = difficulty(message)
    provider = record_calls(service)

    service.turn(sid, session_id, Attempt(message=message))

    assessment = provider.named("Assessment")[0]["payload"]
    generation = provider.named("Draft")[0]["payload"]
    review = provider.named("Review")[0]["payload"]
    assert assessment["example_checks"][0]["first_max_position"] == 1
    assert "update_on_equal_position" not in json.dumps(assessment)
    assert "example_checks" not in generation
    assert "internal_reference" not in generation
    assert generation["worked_example"]["values"] == [5, 5, 1]
    assert generation["worked_example"]["first_max_position"] == 1
    assert generation["worked_example"]["update_on_equal_position"] == 2
    assert "no ejecución de código" in generation["worked_example"]["origin"]
    assert review["example_checks"][0]["first_max_position"] == 1
    assert review["example_checks"][0]["update_on_equal_position"] == 2


def test_initializing_maximum_at_zero_does_not_receive_an_equal_update_example(service):
    sid, session_id = start(service, "arr-02")
    message = "Mi idea inicializa el máximo en 0 antes de leer las alturas, incluso para [-3,-7,-4]."
    service.provider.observation = Observation(
        concept="arreglos", kind="dificultad", quote=message,
        note="La inicialización propuesta supone que existe una altura no negativa.",
    )
    provider = record_calls(service)

    service.turn(sid, session_id, Attempt(message=message))

    generation = provider.named("Draft")[0]["payload"]
    assert generation["response_contract"]["mode"] == "contrast_attempt"
    assert generation["student_assessment"]["status"] == "misconception"
    assert "worked_example" not in generation
    trace = service.store.session(sid, session_id, internal=True)["interactions"][-1]["trace"]
    assert "worked_example" not in trace


@pytest.mark.parametrize("candidate", [
    "Para [5,5,1], tu código devolvería 1.",
    "Con [-2,-2,-5], tu condición elegiría la primera posición.",
])
def test_tie_guard_rejects_inverted_result_of_equal_update(candidate):
    issues = check_tie_update_claims("arr-02", candidate, "Mi idea actualiza cuando el valor es mayor o igual.")
    assert issues
    assert "posición 2" in issues[0]


@pytest.mark.parametrize("candidate,student", [
    ("Para [5,5,1], tu código devolvería la posición 2.", "Actualizo si el nuevo valor es mayor o igual."),
    ("Con [-2,-2,-5], tu condición elegiría la segunda posición.", "Cambio la posición si es igual o más grande."),
    ("En [1,7,3], tu propuesta seleccionaría 2.", "Mi comparación usa >=."),
])
def test_tie_guard_accepts_the_actual_result_of_equal_update(candidate, student):
    assert check_tie_update_claims("arr-02", candidate, student) == []


@pytest.mark.parametrize("problem,candidate,student", [
    ("arr-01", "Para [5,5,1], tu código devolvería 1.", "Uso mayor o igual."),
    ("arr-02", "Para [5,5,1], tu código devolvería 1.", "Solo actualizo con un máximo estrictamente mayor."),
    ("arr-02", "Tu código devolvería 1.", "Uso mayor o igual para [5,5,1]."),
    ("arr-02", "Compara [5,5,1] y [2,2,0]; tu código devolvería 1.", "Uso >=."),
    ("arr-02", "Para [5,5,1], ¿qué posición conservarías?", "Uso mayor o igual."),
])
def test_tie_guard_does_not_claim_to_interpret_cases_outside_its_scope(problem, candidate, student):
    assert check_tie_update_claims(problem, candidate, student) == []


def test_boundary_contract_rejects_a_complete_prefix_list_without_identified_entry():
    contract = ResponseContract("prefix_boundary", "arr-04:hint:3")
    issues = contract_review(contract, "Para el intervalo [2,2], observa la lista de prefijos [0,2,7,6]. ¿Qué parte queda fuera?")
    assert issues
    assert "Identifica el prefijo hasta un día concreto" in issues[0]


def test_boundary_contract_rejects_a_day_without_an_explicit_target_interval():
    issues = contract_review(ResponseContract("prefix_boundary", "arr-04:hint:3"),
                             "Observa el prefijo hasta el día 2. ¿Qué día queda fuera del intervalo?")
    assert issues
    assert "Declara primero el intervalo objetivo" in issues[0]


@pytest.mark.parametrize("message", [
    "Para el intervalo [2,2], observa el prefijo hasta el día 2. ¿Qué día contiene que queda fuera del intervalo?",
    "Para el intervalo [2,2], revisa la posición 2 de tus sumas acumuladas. ¿Qué elemento contribuye pero queda fuera?",
    "Para el intervalo [2,2], observa el índice 2 del prefijo. ¿Qué día abarca que no pertenece al intervalo?",
    "Para el intervalo [2,2], piensa qué contiene P[2]. ¿Qué día contiene que queda fuera del intervalo?",
])
def test_boundary_contract_accepts_one_explicit_numeric_boundary(message):
    assert contract_review(ResponseContract("prefix_boundary", "arr-04:hint:3"), message) == []


def test_numeric_boundary_requirement_does_not_apply_to_other_response_contracts():
    assert contract_review(ResponseContract("define_concept", "arr-04:hint:2"),
                           "Una suma de prefijo acumula los valores desde el principio.") == []
