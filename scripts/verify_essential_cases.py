"""Regresión real, repetida y auditable de los dos rechazos esenciales.

Ejemplo desde la raíz del proyecto:
    uv run python scripts/verify_essential_cases.py --repeats 3

Cada ejecución crea subdirectorios únicos de datos y resultados. No reutiliza
perfiles, no sustituye proveedores y no altera la configuración de credenciales.
Salida 0 significa únicamente que pasaron los controles automáticos declarados:
las expresiones regulares no demuestran corrección ni calidad pedagógica general.
Las transcripciones y trazas quedan disponibles para una revisión independiente.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata
from uuid import uuid4

from tutor.config import Settings
from tutor.models import Attempt
from tutor.provider import ProviderError
from tutor.retrieval import IndexUnavailable
from tutor.service import TutorService


ROOT = Path(__file__).resolve().parents[1]
BASICS = ["variables", "bucles", "condicionales", "aritmetica", "arreglos"]


def normalized(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    ).replace("−", "-").replace("–", "-")


def general_prefix_formula(message: str) -> bool:
    """Señales conocidas de revelación; no detector semántico exhaustivo."""
    text = normalized(message)
    symbolic = [
        r"\w+\s*\[\s*r\s*\]\s*-\s*\w+\s*\[\s*l\s*-\s*1\s*\]",
        r"\w+\s*\(\s*r\s*\)\s*-\s*\w+\s*\(\s*l\s*-\s*1\s*\)",
        r"\w+_?\{?r\}?\s*-\s*\w+_?\{?l\s*-\s*1\}?",
    ]
    if any(re.search(pattern, text) for pattern in symbolic):
        return True
    prefix = bool(re.search(r"\bprefij\w*|\bacumulad\w*", text))
    left_boundary = bool(re.search(
        r"\bl\s*-\s*1\b|\bantes de l\b|\banterior a l\b|"
        r"(?:antes|anterior)\s+(?:de|a|al|del)\s+(?:la\s+)?(?:posicion\s+)?"
        r"(?:inicio|inicial|izquierd\w*)", text
    ))
    right_boundary = bool(re.search(r"\br\b|\bextremo derecho\b|\blimite derecho\b|\bfinal\b", text))
    return prefix and left_boundary and right_boundary


def erroneous_confirmation(message: str) -> bool:
    """Confirma globalmente la idea errónea del turno de empate conocido."""
    text = normalized(message)
    patterns = [
        r"\b(?:tu|esa|esta|la|ese|este|el)\s+"
        r"(?:idea|propuesta|enfoque|metodo|criterio|procedimiento|razonamiento)\s+"
        r"(?:(?:es|resulta|esta)\s+)?(?:correct[oa]|bien|valid[oa]|adecuad[oa])\b",
        r"^\s*(?:correcto|exacto|perfecto)[.!,:]",
        r"\b(?:es correcto|esta bien)\s+(?:que\s+)?(?:actualices|actualizar|cambies|cambiar)\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def inspect_turn(case, spec, response, trace, previous_turns, previous_messages, catalog_ids):
    """Controles observables con límites explícitos, separados de la rúbrica."""
    failures = []
    text = response.message + "\n" + (response.code_observation or "")
    if not response.message.strip():
        failures.append("empty_response")
    if spec["sources_required"] and not response.sources:
        failures.append("missing_sources")
    if not spec["sources_required"] and not response.sources:
        if trace.get("mode") != "regla_pedagogica":
            failures.append("missing_sources_outside_declared_clarification")
    for citation in response.sources:
        if citation.chunk_id not in catalog_ids or ":editorial" in citation.chunk_id:
            failures.append("non_public_or_unknown_source")
    # Las entradas de esta batería no aportan código ni solicitan ejecución.
    if response.checks.status != "no ejecutado":
        failures.append("unrequested_execution_claim")
    if re.search(r"```|#include|\b(?:int|signed|auto)\s+main\s*\(|"
                 r"using\s+namespace|\bfor\s*\(|\bwhile\s*\(", text, re.I):
        failures.append("structured_code_or_complete_program_signature")
    if case["problem_id"] == "arr-04":
        proposed = any(general_prefix_formula(message) for message in previous_messages + [spec["message"]])
        if general_prefix_formula(text) and not proposed:
            failures.append("unproposed_general_prefix_formula")
    if spec["expectation"] == "reject_equal_update" and erroneous_confirmation(text):
        failures.append("incorrect_global_confirmation_of_equal_update")
    if spec["expectation"] == "request_attempt" and previous_turns:
        previous = previous_turns[-1].get("response")
        if previous and response.help_level != previous["help_level"]:
            failures.append("help_level_changed_without_new_attempt")
    return sorted(set(failures))


def write_new(path: Path, value) -> None:
    """No sobrescribe ni resultados de otra ejecución ni un artefacto actual."""
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def error_record(exc: Exception) -> dict:
    # No serializar argumentos de errores inesperados: podrían contener cuerpos
    # HTTP o parámetros privados. Los adaptadores ofrecen códigos sanitizados.
    code = getattr(exc, "code", "index_unavailable" if isinstance(exc, IndexUnavailable) else "unexpected_error")
    return {"type": type(exc).__name__, "code": code}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3, help="Sesiones independientes por caso (predeterminado: 3)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "essential-verification",
                        help="Directorio base; cada ejecución utiliza un subdirectorio nuevo")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "essential-cases")
    parser.add_argument("--suite", type=Path, default=ROOT / "evaluation" / "essential-cases.json")
    parser.add_argument("--case", action="append", choices=["comprension-y-empates", "pistas-acumuladas"],
                        help="Limita familias; se puede repetir. Por defecto ejecuta ambas.")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats debe ser al menos 1")
    suite_raw = args.suite.read_bytes()
    suite = json.loads(suite_raw)
    cases = [case for case in suite["cases"] if not args.case or case["family"] in args.case]
    if not cases:
        parser.error("No hay casos seleccionados")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    output_dir = args.output_dir.resolve() / run_id
    data_dir = args.data_dir.resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    data_dir.mkdir(parents=True, exist_ok=False)
    # La configuración normal permanece intacta; solo se aísla el estado de esta
    # evaluación. Settings decide modelo, URL y credenciales como en el producto.
    settings = Settings(data_dir=data_dir)
    settings.corpus_path = settings.corpus_path.resolve()
    metadata = {
        "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
        "provider": settings.llm_provider, "model": settings.llm_model,
        "revision": settings.llm_revision, "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens, "retries": settings.llm_retries,
        "response_format": settings.llm_response_format,
        "embedding_model": settings.embedding_model, "embedding_revision": settings.embedding_revision,
        "suite_sha256": hashlib.sha256(suite_raw).hexdigest(),
        "corpus_sha256": hashlib.sha256(settings.corpus_path.read_bytes()).hexdigest(),
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "tutor").glob("*.py"))
        },
        "repeats": args.repeats, "cases": [case["id"] for case in cases],
        "data_dir": str(data_dir), "output_dir": str(output_dir),
        "scope": "Proveedor y embeddings reales; ninguna respuesta de prueba sustituye al servicio.",
        "interpretation": "La aprobación automática cubre los síntomas comprobados. No demuestra ausencia de otros errores, utilidad de las pistas ni validez pedagógica general.",
        "pedagogical_review": suite["pedagogical_review"],
    }
    write_new(output_dir / "run.json", metadata)
    print(f"Resultados nuevos: {output_dir}", flush=True)
    service = None
    results = []
    fatal_errors = []
    started = time.monotonic()
    try:
        if settings.llm_provider == "disabled" or not settings.llm_model:
            raise ProviderError("No hay un proveedor real configurado", "not_configured")
        service = TutorService(settings)
        if settings.llm_model not in service.provider.models():
            raise ProviderError("El modelo seleccionado no figura en el proveedor real", "model_not_available")
        write_new(output_dir / "index.json", service.retriever.ingest())
        catalog_ids = {chunk["id"] for chunk in service.catalog.chunks() if chunk["kind"] != "editorial"}
        for repetition in range(1, args.repeats + 1):
            for case in cases:
                case_dir = output_dir / f"{case['id']}-repeat-{repetition:02d}"
                case_dir.mkdir(exist_ok=False)
                sid = service.store.create_student(f"Regresión {case['id']} {repetition}", BASICS)["id"]
                session_id = service.start_session(sid, case["problem_id"])["id"]
                turns = []
                messages = []
                for number, spec in enumerate(case["turns"], start=1):
                    turn = {"number": number, "input": spec["message"], "expectation": spec["expectation"],
                            "critical": number == case["critical_turn"], "automatic_failures": []}
                    turn_started = time.monotonic()
                    try:
                        response = service.turn(sid, session_id, Attempt(message=spec["message"]))
                        turn["response"] = response.model_dump()
                        session = service.store.session(sid, session_id, internal=True)
                        record = session["interactions"][-1]
                        turn["trace"] = record.get("trace", {})
                        turn["automatic_failures"] = inspect_turn(
                            case, spec, response, turn["trace"], turns, messages, catalog_ids
                        )
                        if len(session["interactions"]) != number or record["attempt"]["message"] != spec["message"]:
                            turn["automatic_failures"].append("history_not_preserved")
                        if record["status"] != "completed" or record["id"] != response.interaction_id:
                            turn["automatic_failures"].append("response_not_persisted_as_completed")
                    except Exception as exc:
                        turn["error"] = error_record(exc)
                        turn["automatic_failures"].append("turn_failed_or_rejected")
                        # Registrar también los candidatos rechazados por los controles
                        # del servicio. Son artefactos de revisión, nunca ayuda al alumno.
                        try:
                            session = service.store.session(sid, session_id, internal=True)
                            if len(session["interactions"]) >= number:
                                turn["trace"] = session["interactions"][number - 1].get("trace", {})
                        except Exception as trace_error:
                            turn["trace_capture_error"] = error_record(trace_error)
                            turn["automatic_failures"].append("failed_trace_unavailable")
                    turn["duration_seconds"] = round(time.monotonic() - turn_started, 3)
                    write_new(case_dir / f"turn-{number:02d}.json", turn)
                    turns.append(turn)
                    messages.append(spec["message"])
                    print(f"{case['id']} {repetition}/{args.repeats}, turno {number}: "
                          f"{'FALLO' if turn['automatic_failures'] else 'controles automáticos superados'}", flush=True)
                result = {
                    "case": case["id"], "family": case["family"], "variant": case["variant"],
                    "repetition": repetition, "student_id": sid, "session_id": session_id,
                    "turns": turns, "profile": service.store.profile(sid),
                    "session": service.store.session(sid, session_id),
                    "automatic_pass": not any(turn["automatic_failures"] for turn in turns),
                    "pedagogical_review": {"status": "pending", "reviewer": None, "findings": None},
                }
                write_new(case_dir / "case.json", result)
                results.append({key: result[key] for key in ("case", "family", "variant", "repetition", "automatic_pass")})
    except Exception as exc:
        fatal_errors.append(error_record(exc))
        print(f"La ejecución no pudo completarse: {fatal_errors[-1]['code']}", flush=True)
    finally:
        if service is not None:
            try:
                service.close()
            except Exception as exc:
                fatal_errors.append(error_record(exc))
        expected_cases = len(cases) * args.repeats
        summary = {
            "run_id": run_id, "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "expected_sessions": expected_cases, "completed_sessions": len(results),
            "passed_automatic_sessions": sum(result["automatic_pass"] for result in results),
            "failed_automatic_sessions": sum(not result["automatic_pass"] for result in results),
            "fatal_errors": fatal_errors, "results": results,
            "automatic_pass": not fatal_errors and len(results) == expected_cases and all(result["automatic_pass"] for result in results),
            "pedagogical_review": "pending: leer las respuestas y sus citas; los controles no prueban calidad pedagógica",
        }
        write_new(output_dir / "summary.json", summary)
    print(f"Resumen: {output_dir / 'summary.json'}", flush=True)
    return 0 if summary["automatic_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
