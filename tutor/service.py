import threading
import time
import re
from tutor.config import Settings
from tutor.corpus import Catalog
from tutor.execution import DockerRunner
from tutor.models import Attempt, CheckResult, Citation, Draft, Review, TurnResponse, Assessment
from tutor.pedagogy import GENERATOR_SYSTEM, REVIEW_SYSTEM, ASSESSMENT_SYSTEM, decide, structural_review, disclosure_review, uncovered_application
from tutor.provider import create_provider, ProviderError
from tutor.recommend import recommend
from tutor.retrieval import HybridRetriever, IndexUnavailable, tokens
from tutor.storage import Store, TurnBusy, uid
from tutor.reasoning_checks import check_array_examples,check_pair_claims,check_prefix_interval_claims,check_tie_update_claims
from tutor.response_contract import select_contract,contract_review


class TutorService:
    def __init__(self, settings=None, provider=None, embeddings=None):
        self.settings = settings or Settings()
        self.store = Store(self.settings.data_dir / "tutor.sqlite3")
        self.catalog = Catalog(self.store)
        if not self.catalog.problems():
            self.catalog.ingest(self.settings.corpus_path)
        self.retriever = HybridRetriever(self.catalog,self.settings,embeddings)
        self.provider = provider or create_provider(self.settings)
        self.runner = DockerRunner(self.settings)
        # Serializa lectura-decisión-registro: un único proceso de servicio en este prototipo.
        self.turn_lock = threading.Lock()

    def close(self):
        self.retriever.close()
        if hasattr(self.provider,"close"):
            self.provider.close()

    def start_session(self, student_id, problem_id):
        self.catalog.problem(problem_id)
        return self.store.create_session(student_id,problem_id)

    def recommendations(self, student_id, goal=None, max_difficulty=3):
        return recommend(self.catalog,self.store,student_id,goal,max_difficulty)

    def turn(self, student_id, session_id, attempt: Attempt):
        with self.turn_lock:
            try:
                with self.store.turn_guard():
                    return self._turn(student_id,session_id,attempt)
            except TurnBusy:
                raise ProviderError("Hay otro turno en curso. Espera a que termine y vuelve a enviar este intento.","busy") from None

    def _turn(self, student_id, session_id, attempt):
        started = time.monotonic()
        session = self.store.session(student_id,session_id,internal=True)
        history = session["interactions"]
        profile = self.store.profile(student_id)
        problem = self.catalog.problem(session["problem_id"])
        decision = decide(attempt,history,profile,self.settings.max_hint_level)
        public_material=problem.statement+" "+" ".join(c.text for c in self.catalog.concepts() if c.id in problem.concept_ids)
        if not decision.question and uncovered_application(attempt.message,public_material):
            decision.question="El material disponible de este problema no respalda esa aplicación. Explica qué relación buscas entre ese concepto y el enunciado para poder revisar la conexión."
            decision.reason="Cobertura léxica insuficiente para una aplicación solicitada; se pide contexto, sin afirmar irrelevancia semántica"
        interaction_id = uid()
        checks = self.runner.run(attempt.code,problem.tests) if attempt.request_execution and attempt.code else CheckResult(detail="No se solicitó ejecución de código." if not attempt.request_execution else "Falta código para ejecutar.")
        trace = dict(problem_exact=problem.id,decision=vars(decision),provider=self.settings.llm_provider,
                     model=self.settings.llm_model,model_revision=self.settings.llm_revision,embedding=self.retriever.config(),checks=checks.model_dump())
        trace["generation_config"]=dict(temperature=self.settings.llm_temperature,max_tokens=self.settings.llm_max_tokens,timeout=self.settings.llm_timeout,retries=self.settings.llm_retries,response_format=self.settings.llm_response_format)
        observation = None
        try:
            if decision.need == "practica":
                goal = attempt.practice_goal
                normalized_message = " ".join(tokens(attempt.message))
                if not goal:
                    known_topics={topic for p in self.catalog.problems() for topic in p.topics}
                    goal=next((topic for topic in sorted(known_topics,key=len,reverse=True) if topic.replace("_"," ") in normalized_message),None)
                if not goal:
                    match=re.search(r"(?:sobre|practicar|ejercicios de)\s+([a-z_]+)",normalized_message)
                    goal=match.group(1) if match else None
                recommendations = self.recommendations(student_id,goal)
                message = "\n".join(f"{r['problem']['id']} — {r['problem']['title']}: {r['reason']}." for r in recommendations["items"]) or recommendations["message"]
                response = TurnResponse(interaction_id=interaction_id,message=message,intervention=decision.need,help_level=None,sources=[],checks=checks,reported_result=attempt.reported_result)
                trace["mode"] = "regla_recomendacion"
            elif decision.question:
                response = TurnResponse(interaction_id=interaction_id,message=decision.question,intervention=decision.need,help_level=decision.level,sources=[],checks=checks,reported_result=attempt.reported_result)
                trace["mode"] = "regla_pedagogica"
            else:
                # La ficha exacta siempre se obtiene por ID. El ranking es evidencia adicional.
                used_hint_ids = {cid for turn in history for cid in turn.get("trace",{}).get("used_chunk_ids",[]) if ":hint:" in cid}
                allowed_ids = set(problem.concept_ids) | {f"{problem.id}:hint:{decision.level}"}
                allowed_ids -= used_hint_ids
                retrieval = self.retriever.search(attempt.message+" "+" ".join(problem.topics),
                    kinds=["concept","hint"],max_level=decision.level,related_ids=allowed_ids)
                exact = next(r for r in self.catalog.chunks() if r["id"] == f"{problem.id}:statement")
                allowed = [exact]+retrieval["hits"]
                trace["retrieval"] = retrieval
                # Material público exacto y únicamente contenido permitido: nunca editorial, C++ de referencia ni pruebas reservadas.
                compact_history = [dict(attempt=h["attempt"],response=h["response"]) for h in history]
                if sum(len(str(h)) for h in compact_history) > 60000:
                    raise ProviderError("La sesión alcanzó el límite de contexto seguro. Inicia otra sesión; el historial permanece guardado.","context_limit")
                payload = dict(problem=problem.public().model_dump(),attempt=attempt.model_dump(),history=compact_history,
                    profile=profile,decision=vars(decision),evidence=allowed,checks=checks.model_dump(),
                    allowed_source_ids=[h["id"] for h in allowed],
                    instruction="Si no hay una nueva pista permitida, solicita aplicar una anterior a un caso concreto, sin repetirla.")
                reference=dict(strategy=problem.reference_strategy,common_errors=problem.common_errors,
                    concepts=[c.text for c in self.catalog.concepts() if c.id in problem.concept_ids])
                assessment = None
                if decision.need in {"idea","depuracion"}:
                    assessment=self.provider.generate(ASSESSMENT_SYSTEM,dict(problem=problem.public().model_dump(),
                        current_student_attempt=attempt.model_dump(),tutor_history=[h["response"] for h in compact_history],
                        internal_reference=reference,allowed_concepts=problem.topics,
                        example_checks=check_array_examples(problem.id,[attempt.message])),Assessment)
                    observation=assessment.observation
                    student_content=attempt.message+"\n"+(attempt.code or "")
                    if observation and (observation.quote not in student_content or observation.concept not in problem.topics):
                        observation=None
                        assessment=Assessment(status="uncertain",action="probe")
                    trace["student_assessment"]=assessment.model_dump()
                    payload["student_assessment"]={"status":assessment.status,"action":assessment.action,
                        "student_quote":observation.quote if observation else None}
                    if assessment.action=="acknowledge":
                        payload["response_goal"]="Reconoce brevemente la propiedad que acaba de justificar el estudiante. No enumeres pasos ni repitas ejemplos; no es necesario dar otra pista ni proponer otro caso."
                        payload["instruction"]="El alumno ya aportó evidencia nueva. Basta una devolución breve sobre esa evidencia; deja la implementación y sus pruebas a su cargo."
                student_content=attempt.message+"\n"+(attempt.code or "")
                contract=select_contract(decision,assessment,problem,allowed,student_content)
                payload["response_contract"]=dict(mode=contract.mode,focus_source_id=contract.focus_source_id)
                payload["focus_evidence"]=next((row for row in allowed if row["id"]==contract.focus_source_id),None)
                trace["response_contract"]=payload["response_contract"]
                if problem.id=="arr-02" and contract.mode=="contrast_attempt" and re.search(r"mayor o igual|igual o m[aá]s grande|>=",student_content,re.I):
                    # Un contraejemplo numérico público, no la estrategia de solución.
                    examples=check_array_examples(problem.id,[attempt.message,(payload["focus_evidence"] or {}).get("text","")],include_alternative=True)
                    payload["worked_example"]=examples[0] if examples else None
                    trace["worked_example"]=payload["worked_example"]
                # Solo instrucciones del código, nunca texto del corpus/estudiante, adquieren autoridad de sistema.
                generation_system=GENERATOR_SYSTEM+"\n"+contract.instruction()
                accepted = False
                for content_attempt in range(2):
                    review=None
                    draft = self.provider.generate(generation_system,payload,Draft)
                    issues = structural_review(draft,allowed,history,decision.level)
                    issues+=contract_review(contract,draft.message)
                    student_content=attempt.message+"\n"+(attempt.code or "")
                    issues+=disclosure_review(problem.id,draft.message,student_content)
                    if payload.get("student_assessment",{}).get("status")=="misconception" and re.search(r"\btu idea es correcta\b",draft.message,re.I):
                        issues.append("Valida como correcta una idea con un error concreto identificado")
                    numeric_issues=check_pair_claims(problem.id,draft.message)+check_prefix_interval_claims(problem.id,draft.message)+check_tie_update_claims(problem.id,draft.message,student_content)
                    issues+=numeric_issues
                    structural_issues=list(issues)
                    if not issues:
                        example_checks=check_array_examples(problem.id,[attempt.message,draft.message],include_alternative=True)
                        review_context={key:payload[key] for key in ("problem","attempt","history","decision","evidence","checks","allowed_source_ids")}
                        review_context["response_contract"]=payload["response_contract"]
                        if assessment:
                            review_context["student_assessment"]=payload["student_assessment"]
                        review = self.provider.generate(REVIEW_SYSTEM,dict(review_context,draft=draft.model_dump(),allowed_concepts=problem.topics,
                            internal_reference=reference,example_checks=example_checks),Review)
                        trace["example_checks"]=example_checks
                        if not (review.correct and review.relevant and review.supported and review.safe_disclosure and review.non_repetitive):
                            issues.append(review.issue or "La revisión de contenido no aprobó la respuesta")
                        if set(review.used_chunk_ids) != set(draft.used_chunk_ids):
                            issues.append("El revisor no verificó todas las citas utilizadas")
                    trace.setdefault("reviews",[]).append(dict(attempt=content_attempt,issues=issues,candidate=draft.model_dump(),content_review=review.model_dump() if review else None))
                    if not issues:
                        accepted = True
                        break
                    # La regeneración conserva el historial ENTREGADO, nunca el candidato rechazado.
                    # Así no se induce al modelo a copiar el mismo texto con cambios superficiales.
                    # Nunca devolver al generador una explicación privada del revisor que pueda revelar la referencia.
                    payload["revision_request"] = "Genera una respuesta nueva conforme al objetivo: verifica afirmaciones, ejemplos y citas; respeta el nivel y evita repetición o revelación de la solución."
                    generation_system=GENERATOR_SYSTEM+"\n"+contract.instruction()+"\nLa primera propuesta no superó los controles. Genera desde cero otra formulación que cumpla este objetivo. No aumentes el nivel de ayuda."
                    if review:
                        payload["rejected_checks"]=[name for name in ("correct","relevant","supported","safe_disclosure","non_repetitive") if not getattr(review,name)]
                    if numeric_issues:
                        payload["numeric_correction"]=numeric_issues
                    if structural_issues:
                        payload["structural_corrections"]=structural_issues
                        if any("repetid" in issue.lower() or "Repite" in issue for issue in structural_issues):
                            payload.pop("previous_draft",None)
                            payload["revision_request"]="Genera una devolución nueva y breve, sin reutilizar ejemplos o explicaciones del historial. No es obligatorio agregar otra pista."
                if not accepted:
                    raise ProviderError("La respuesta no superó la revisión de contenido. Tu intento quedó guardado; reformula el bloqueo o solicita otra revisión.","review_rejected")
                if observation:
                    student_content = attempt.message+"\n"+(attempt.code or "")
                    if observation.quote not in student_content or observation.concept not in problem.topics:
                        observation = None
                    # Pide justificación concreta; las preguntas y los resultados sin explicación no bastan.
                    elif observation.kind == "demostracion" and ("?" in observation.quote or len(observation.quote.split()) < 8):
                        observation = None
                trace["used_chunk_ids"] = draft.used_chunk_ids
                response = TurnResponse(interaction_id=interaction_id,message=draft.message,intervention=decision.need,help_level=decision.level,
                    sources=[Citation(chunk_id=h["id"],title=h["title"],provenance=h["provenance"]) for h in allowed if h["id"] in draft.used_chunk_ids],
                    checks=checks,reported_result=attempt.reported_result,code_observation=draft.code_observation if attempt.code else None)
                trace["progress"] = observation.model_dump() if observation else None
            trace["duration_ms"] = round((time.monotonic()-started)*1000)
            self.store.record(interaction_id,session_id,attempt.model_dump(),response.model_dump(),trace,"completed",observation,decision.level)
            return response
        except (ProviderError,IndexUnavailable) as exc:
            trace.update(error_code=getattr(exc,"code","index_unavailable"),duration_ms=round((time.monotonic()-started)*1000))
            if getattr(exc,"validation_errors",None):
                trace["schema_errors"]=dict(schema=exc.schema_name,errors=exc.validation_errors)
            self.store.record(interaction_id,session_id,attempt.model_dump(),None,trace,"failed")
            raise
