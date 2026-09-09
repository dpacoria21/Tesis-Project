"""El control numérico no debe confundir preguntas o requisitos con salidas afirmadas."""
import pytest

from tutor.reasoning_checks import check_tie_update_claims


STUDENT = "Mi idea actualiza la posición cuando el valor nuevo es mayor o igual."


@pytest.mark.parametrize("subject", ["regla", "código", "método", "algoritmo", "condición", "propuesta"])
def test_explicit_wrong_result_is_blocked_for_student_method(subject):
    issues = check_tie_update_claims("arr-02", f"En [-2,-2,-5], tu {subject} devolvería la posición 1.", STUDENT)
    assert issues
    assert "posición 2" in issues[0]


@pytest.mark.parametrize("message", [
    "En [5,5,1], tu regla no devolvería 1: conservaría el último empate.",
    "En [5,5,1], no es cierto que tu regla devolvería 1.",
    "En [5,5,1], tu regla nunca elegiría la primera posición.",
    "En [5,5,1], ¿tu regla devolvería 1 o 2?",
    "Para [5,5,1], tu regla devolvería 1 o 2?",
    "En [5,5,1], el enunciado elegiría la primera posición; tu regla conservaría la segunda.",
    "En [5,5,1], el resultado esperado sería 1, pero tu regla devolvería 2.",
    "En [5,5,1], el primer máximo sería en posición 1.",
    "En [5,5,1], tu regla devolvería 1 si corriges el tratamiento de los empates.",
    "Si cambiaras la comparación, en [5,5,1] tu código devolvería 1.",
    "En [5,5,1], tu regla corregida devolvería 1.",
    'En [5,5,1], el estudiante escribió "tu regla devolvería 1".',
    "En [5,5,1], quizás tu algoritmo devolvería 1.",
])
def test_non_assertive_or_different_claim_is_left_for_semantic_review(message):
    assert check_tie_update_claims("arr-02", message, STUDENT) == []


def test_true_expected_result_does_not_hide_separate_wrong_method_claim():
    message = "En [5,5,1], el enunciado elegiría la primera posición. Tu regla devolvería 1."
    assert check_tie_update_claims("arr-02", message, STUDENT)


@pytest.mark.parametrize("message", [
    "En [5,5,1], tu regla devolvería 2.",
    "En [-2,-2,-5], tu método actual elegiría la segunda posición.",
    "En [4,1,4,4], tu algoritmo conservaría la cuarta posición.",
])
def test_actual_result_of_equal_update_is_allowed(message):
    assert check_tie_update_claims("arr-02", message, STUDENT) == []
