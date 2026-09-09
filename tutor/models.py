from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Example(StrictModel):
    input: str
    output: str


class Provenance(StrictModel):
    kind: Literal["original_demo", "external"]
    platform: str
    external_id: str | None = None
    url: str | None = None
    review_status: str
    license_note: str

    @model_validator(mode="after")
    def external_source(self):
        if self.kind == "external" and (not self.external_id or not self.url or not self.url.startswith("https://")):
            raise ValueError("El material externo requiere identificador real y URL HTTPS de procedencia.")
        return self


class PublicProblem(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    title: str
    statement: str
    constraints: str
    input_format: str
    output_format: str
    examples: list[Example] = Field(min_length=1)
    topics: list[str]
    prerequisites: list[str]
    difficulty: int = Field(ge=1, le=5)
    difficulty_scale: str = "demo_local_1_5"
    language: str = "es"
    programming_language: str = "C++17"
    provenance: Provenance


class Guidance(StrictModel):
    level: int = Field(ge=0, le=3)
    text: str
    step: str


class Problem(PublicProblem):
    explanation: str
    reference_strategy: str
    reference_cpp: str
    common_errors: list[str]
    tests: list[Example] = Field(min_length=2)
    guidance: list[Guidance] = Field(min_length=4)
    concept_ids: list[str]

    @model_validator(mode="after")
    def complete_guidance(self):
        if set(g.level for g in self.guidance) != {0, 1, 2, 3}:
            raise ValueError("Se requiere orientación N0, N1, N2 y N3.")
        return self

    def public(self) -> PublicProblem:
        return PublicProblem.model_validate(self.model_dump(include=set(PublicProblem.model_fields)))


class Concept(StrictModel):
    id: str
    title: str
    text: str
    topics: list[str]
    language: str = "es"
    min_level: int = Field(2, ge=0, le=3)
    provenance: Provenance


class Corpus(StrictModel):
    schema_version: Literal[1] = 1
    problems: list[Problem]
    concepts: list[Concept]

    @model_validator(mode="after")
    def references(self):
        ids = [p.id for p in self.problems] + [c.id for c in self.concepts]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificadores duplicados en el corpus.")
        concepts = {c.id for c in self.concepts}
        if any(set(p.concept_ids) - concepts for p in self.problems):
            raise ValueError("Relación a un concepto inexistente.")
        return self


Need = Literal["comprension", "concepto", "idea", "depuracion", "practica"]


class Attempt(StrictModel):
    message: str = Field(min_length=1, max_length=12000)
    code: str | None = Field(None, max_length=40000)
    reported_result: str | None = Field(None, max_length=2000)
    need: Need | None = None
    request_execution: bool = False
    practice_goal: str | None = Field(None,max_length=100)


class CheckResult(StrictModel):
    status: Literal["no ejecutado", "error de compilación", "no supera las pruebas disponibles", "supera las pruebas disponibles"] = "no ejecutado"
    origin: Literal["prototipo", "ninguna"] = "ninguna"
    detail: str = "La ejecución aislada está desactivada."
    passed: int = 0
    total: int = 0


class Citation(StrictModel):
    chunk_id: str
    title: str
    provenance: Provenance


class TurnResponse(StrictModel):
    interaction_id: str
    message: str
    intervention: Need
    help_level: int | None = Field(None, ge=0, le=3)
    sources: list[Citation]
    checks: CheckResult
    reported_result: str | None = None
    code_observation: str | None = None


class Draft(StrictModel):
    message: str = Field(min_length=1, max_length=1800)
    used_chunk_ids: list[str] = Field(min_length=1,max_length=6,description="Al menos un ID exacto de evidence que realmente sustenta el mensaje; nunca inventar IDs.")
    code_observation: str | None = Field(None, max_length=500)


class Observation(StrictModel):
    concept: str
    kind: Literal["demostracion", "dificultad", "estrategia"]
    quote: str = Field(min_length=8, max_length=500)
    note: str = Field(max_length=300)


class Review(StrictModel):
    correct: bool = Field(description="Las afirmaciones que sí hace el TUTOR son correctas. Una pista parcial puede omitir otras condiciones o pasos. No evalúa completitud de la solución ni corrección del estudiante.")
    relevant: bool = Field(description="draft atiende la necesidad actual al nivel indicado; no exige resolver todo el problema.")
    supported: bool = Field(description="Las afirmaciones de draft están respaldadas por la evidencia y las citas usadas.")
    safe_disclosure: bool = Field(description="draft junto al historial conserva trabajo significativo y respeta el nivel.")
    non_repetitive: bool = Field(description="draft no repite una pista ya entregada.")
    used_chunk_ids: list[str]
    issue: str = Field(max_length=300,description="Cadena vacía si todos los controles son true; en otro caso defecto concreto del tutor. No exigir que una pista entregue la corrección completa. No incluir razonamiento privado.")

    @model_validator(mode="after")
    def consistent_verdict(self):
        if all((self.correct,self.relevant,self.supported,self.safe_disclosure,self.non_repetitive)) and self.issue.strip():
            raise ValueError("Una aprobación completa requiere issue vacío; si detectas un defecto marca el control correspondiente false")
        return self


class Assessment(StrictModel):
    observation: Observation | None = None
    status: Literal["insufficient","supported","misconception","uncertain","strategy_observed"]
    action: Literal["clarify","acknowledge","probe","correct"]

    @model_validator(mode="after")
    def evidence_required(self):
        expected_action={"supported":"acknowledge","misconception":"correct"}
        if self.status in expected_action and self.action!=expected_action[self.status]:
            raise ValueError("La acción debe concordar con la evaluación")
        if self.status in {"insufficient","uncertain"} and self.observation is not None:
            raise ValueError("Una evaluación incierta no crea evidencia de progreso")
        if self.status in {"supported","misconception","strategy_observed"} and self.observation is None:
            raise ValueError("Una conclusión sobre el estudiante requiere evidencia textual")
        if self.status=="supported" and self.observation.kind!="demostracion":
            raise ValueError("supported requiere una demostración")
        if self.status=="misconception" and self.observation.kind!="dificultad":
            raise ValueError("misconception requiere una dificultad concreta")
        if self.status=="strategy_observed" and (self.observation.kind!="estrategia" or self.action!="probe"):
            raise ValueError("strategy_observed requiere una estrategia declarada y action=probe; no certifica corrección")
        return self


class StudentView(StrictModel):
    id: str
    name: str
    basics: list[str]
    created: str


class SessionHead(StrictModel):
    id: str
    student_id: str
    problem_id: str
    created: str


class InteractionView(StrictModel):
    id: str
    created: str
    attempt: Attempt
    response: TurnResponse | None
    status: Literal["completed","failed"]


class SessionView(SessionHead):
    interactions: list[InteractionView]


class ProfileObservation(StrictModel):
    id: str
    student_id: str
    interaction_id: str
    concept: str
    kind: Literal["demostracion","dificultad","estrategia"]
    quote: str
    note: str
    created: str
    status: Literal["provisional","confirmado"]
    help_level: int | None = Field(ge=0,le=3)


class ProfileView(StrictModel):
    student_id: str
    declared_basics: list[str]
    observations: list[ProfileObservation]


class RecommendationItem(StrictModel):
    problem: PublicProblem
    reason: str


class RecommendationView(StrictModel):
    items: list[RecommendationItem]
    message: str


class HealthView(StrictModel):
    status: Literal["ok"]
    catalog_problems: int
    index_ready: bool
    llm_configured: bool
    execution_enabled: bool
