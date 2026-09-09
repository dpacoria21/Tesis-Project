"""Objetivos de generación elegidos por el servicio; no contienen respuestas al alumno.

Las instrucciones de este módulo son código de política. El corpus, las citas del
alumno y los borradores siguen siendo datos no confiables en el mensaje de usuario.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseContract:
    mode: str
    focus_source_id: str | None

    def instruction(self):
        return INSTRUCTIONS[self.mode]


INSTRUCTIONS = {
    "standard": "Atiende la necesidad y el nivel indicados sin añadir otros pasos.",
    "contrast_attempt": (
        "OBJETIVO OBLIGATORIO DE ESTE TURNO: mostrar una consecuencia problemática de la propuesta actual. "
        "El estado misconception significa que hay un error concreto; la acción correct significa señalarlo, "
        "NO declarar correcta la idea ni entregar el algoritmo corregido. "
        "Redacta dos frases: una observación de UN caso pequeño y del requisito del enunciado, "
        "seguida de una pregunta sobre qué decisión necesita revisar. "
        "Si recibes worked_example, sus posiciones empiezan en 1: first_max_position es la posición "
        "que pide el enunciado y update_on_equal_position la que conserva actualizar también al empatar. "
        "Usa esos hechos comprobados para contrastar UN caso; no inviertas las dos posiciones. "
        "Llama 'posición guardada por tu regla' al resultado del método; no la llames 'primer máximo', "
        "pues la primera aparición real no cambia con la regla utilizada. "
        "No preguntes por un resultado que ya diste; deja al alumno reparar su decisión. "
        "No abras con un veredicto global ni elogies la propuesta. Puedes reconocer una parte correcta "
        "solo si la distingues del error. No sustituyas el intento por una versión corregida para aprobarla."
    ),
    "define_concept": (
        "OBJETIVO OBLIGATORIO DE ESTE TURNO: definir únicamente el concepto solicitado. "
        "Escribe una frase de definición y un solo ejemplo numérico mínimo que ilustre su significado. "
        "No apliques el concepto a resolver el problema ni expliques el siguiente paso. "
        "En prefijos, explica qué contiene una suma acumulada y detente ahí: "
        "no hables de restas, de consultas ni de cómo obtener un intervalo."
    ),
    "one_step": (
        "OBJETIVO OBLIGATORIO DE ESTE TURNO: orientar UNA tarea concreta todavía no resuelta. "
        "Desarrolla únicamente el foco de focus_evidence, si está disponible, utilizando los datos "
        "que ya aportó el estudiante. Señala una parte o frontera específica que debe examinar "
        "y pregunta qué representa o qué debe conservarse/cancelarse. "
        "No resuelvas esa tarea ni generalices a todas las entradas. No repitas la definición del concepto. "
        "Deja al alumno efectuar el cálculo, elegir las fronteras y deducir la regla general."
    ),
    "prefix_boundary": (
        "OBJETIVO OBLIGATORIO DE ESTE TURNO: una única tarea de frontera usando los prefijos del alumno. "
        "Primero declara un intervalo objetivo pequeño en formato [número, número], dentro del arreglo. "
        "Señala el prefijo que termina en UN día concreto, "
        "escribiendo el número del día, y pregunta qué días abarca y cuál queda fuera del intervalo. "
        "La pregunta se refiere a un día INCLUIDO en ese prefijo pero EXCLUIDO del intervalo objetivo "
        "que acabas de declarar; no a días posteriores al propio prefijo. "
        "Una entrada de las sumas acumuladas corresponde a un prefijo: no llames prefijo a toda "
        "la lista de sumas ni preguntes qué entrada representa ya la suma del intervalo. "
        "Termina con una pregunta concreta sin resolverla. Deja al alumno elegir el otro prefijo, "
        "efectuar la resta y deducir la regla general. No cambies ni alargues su arreglo. "
        "No entregues la fórmula general de consulta, ni con símbolos ni explicándola en prosa. "
        "No indiques a la vez los dos prefijos que debe restar. No vuelvas a definir qué es un prefijo."
    ),
    "acknowledge": (
        "OBJETIVO DE ESTE TURNO: reconocer brevemente la propiedad que el alumno acaba de justificar. "
        "No repitas su algoritmo ni los ejemplos anteriores; no es obligatorio dar otra pista o pregunta. "
        "No declares dominio global. Deja la implementación y comprobación a su cargo."
    ),
}


def select_contract(decision, assessment, problem, allowed, student_content):
    hint = next((row["id"] for row in allowed
                 if row["id"] == f"{problem.id}:hint:{decision.level}"), None)
    if assessment and assessment.status == "misconception":
        mode = "contrast_attempt"
    elif assessment and assessment.status == "supported":
        mode = "acknowledge"
    elif decision.need == "concepto" and decision.level == 2:
        mode = "define_concept"
    elif decision.level == 3:
        # Misma política para materiales importados enlazados al concepto de prefijos.
        from tutor.pedagogy import student_proposed_prefix_formula
        mode = "prefix_boundary" if "prefijos" in problem.topics and not student_proposed_prefix_formula(student_content) else "one_step"
    else:
        mode = "standard"
    return ResponseContract(mode, hint)


def contract_review(contract, message):
    """Control acotado del foco observable; la revisión semántica sigue siendo necesaria."""
    import re
    if contract.mode != "prefix_boundary":
        return []
    day = re.search(r"\b(?:d[ií]a|posici[oó]n|[ií]ndice)\s+\d+\b", message, re.I)
    entry = re.search(r"\b\w+\[\s*\d+\s*\]", message)
    interval = re.search(r"\bintervalo\s+(?:objetivo\s+)?\[\s*\d+\s*,\s*\d+\s*\]",message,re.I)
    if not interval:
        return ["Declara primero el intervalo objetivo en formato [número, número]. Luego señala el prefijo hasta un día concreto y pregunta por un día incluido en él pero fuera del intervalo objetivo."]
    if not day and not entry:
        return ["Identifica el prefijo hasta un día concreto escribiendo su número; pregunta qué días abarca y cuál queda fuera. No trates la lista completa de sumas como un solo prefijo."]
    return []
