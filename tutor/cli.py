import argparse
import json
import sys
from pathlib import Path
from tutor.config import Settings
from tutor.models import Attempt
from tutor.provider import create_provider, ProviderError
from tutor.retrieval import IndexUnavailable
from tutor.service import TutorService


def show(value):
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str))


def conversation(service, student_id=None, session_id=None):
    print("Tutor CP — español, C++17. /salir conserva la sesión.")
    students = service.store.students()
    if not student_id:
        for s in students:
            print(f"{s['id']}  {s['name']}")
        selected = input("ID del estudiante o nombre para crear uno: ").strip()
        student_id = next((s["id"] for s in students if s["id"] == selected),None)
        if student_id is None:
            if not selected:
                raise ValueError("Se requiere un nombre")
            student_id = service.store.create_student(selected,["variables","bucles","condicionales","aritmetica"])["id"]
    service.store.student(student_id)
    if not session_id:
        for s in service.store.sessions(student_id):
            print(f"Sesión {s['id']} — {s['problem_id']}")
        selected = input("ID de sesión para retomar o Enter para elegir problema: ").strip()
        if selected:
            session_id = selected
        else:
            for p in service.catalog.problems():
                print(f"{p.id}: {p.title} (dificultad local {p.difficulty})")
            session_id = service.start_session(student_id,input("Problema: ").strip())["id"]
    session = service.store.session(student_id,session_id)
    problem = service.catalog.problem(session["problem_id"]).public()
    print(f"Estudiante: {student_id}\nSesión: {session_id}\n{problem.title}\n{problem.statement}\n{problem.constraints}")
    print(f"Entrada: {problem.input_format}\nSalida: {problem.output_format}")
    for ex in problem.examples:
        print(f"Ejemplo de entrada:\n{ex.input}Salida:\n{ex.output}")
    for turn in session["interactions"]:
        print("Tú:",turn["attempt"]["message"])
        print("Tutor:",turn["response"]["message"] if turn["response"] else "Intento guardado; no hubo respuesta aprobada.")
    print("Comandos: /codigo ruta.cpp, /ejecutar, /perfil, /recomendar [tema], /problema ID, /salir")
    pending_code = None
    execute = False
    while True:
        try:
            message = input("Tú> ").strip()
        except (EOFError,KeyboardInterrupt):
            print("\nSesión conservada.")
            return
        if not message:
            continue
        if message == "/salir":
            return
        try:
            if message.startswith("/codigo "):
                path = Path(message[len("/codigo "):].strip().strip('"'))
                if path.stat().st_size > 40000:
                    raise ValueError("El código debe ocupar como máximo 40 KB")
                pending_code = path.read_text(encoding="utf-8-sig")
                print("Código cargado. Escribe qué necesitas revisar; no se ha ejecutado.")
                continue
            if message == "/ejecutar":
                execute = True
                print("Se solicitará ejecución aislada en el próximo intento.")
                continue
            if message == "/perfil":
                show(service.store.profile(student_id)); continue
            if message.startswith("/recomendar"):
                topic = message.partition(" ")[2].strip() or None
                show(service.recommendations(student_id,topic)); continue
            if message.startswith("/problema "):
                new_problem = message.partition(" ")[2].strip()
                session_id = service.start_session(student_id,new_problem)["id"]
                print("Nueva sesión:",session_id)
                show(service.catalog.problem(new_problem).public().model_dump())
                pending_code,execute = None,False
                continue
            response = service.turn(student_id,session_id,Attempt(message=message,code=pending_code,request_execution=execute))
            print(f"Tutor [{response.intervention}, N{response.help_level}]: {response.message}")
            print("Comprobación:",response.checks.status,"—",response.checks.detail)
            if response.code_observation:
                print("Lectura estática:",response.code_observation)
            for source in response.sources:
                print(f"Fuente usada: {source.chunk_id} — {source.title}")
            pending_code,execute = None,False
        except (KeyError,ValueError,OSError,ProviderError,IndexUnavailable) as exc:
            print("No se completó:",str(exc))


def main():
    parser = argparse.ArgumentParser(description="Tutor CP: servicio modular con recuperación híbrida")
    sub = parser.add_subparsers(dest="command",required=True)
    ingest = sub.add_parser("ingest",help="Importar corpus e indexar embeddings reales")
    ingest.add_argument("--file",type=Path)
    ingest.add_argument("--rebuild",action="store_true")
    sub.add_parser("validate-corpus")
    sub.add_parser("doctor")
    sub.add_parser("models")
    serve = sub.add_parser("serve")
    serve.add_argument("--port",type=int,default=8000)
    chat = sub.add_parser("chat")
    chat.add_argument("--student")
    chat.add_argument("--session")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--problem")
    search.add_argument("--kind",action="append",choices=["statement","hint","concept"])
    search.add_argument("--topic")
    search.add_argument("--language")
    search.add_argument("--level",type=int,choices=range(4),default=2)
    args = parser.parse_args()
    settings = Settings()
    service = None
    try:
        if args.command == "models":
            show(create_provider(settings).models()); return
        service = TutorService(settings)
        if args.command == "ingest":
            show(service.catalog.ingest(args.file or settings.corpus_path))
            show(service.retriever.ingest(args.rebuild))
        elif args.command == "validate-corpus":
            from tutor.reference import solve
            count = 0
            for p in service.catalog.problems():
                if p.provenance.kind != "original_demo":
                    continue
                for case in p.tests+p.examples:
                    if solve(p.id,case.input).split() != case.output.split():
                        raise ValueError("Resultado inconsistente en "+p.id)
                    count += 1
            show(dict(status="ok",cases=count,scope="Oráculos Python del corpus propio; no compila C++ ni sustituye revisión docente."))
        elif args.command == "doctor":
            ready,reason = service.runner.availability()
            show(dict(catalog=len(service.catalog.problems()),index_ready=service.retriever.ready(),
                      embeddings=dict(model=settings.embedding_model,revision=settings.embedding_revision),
                      llm=dict(provider=settings.llm_provider,model=settings.llm_model or "sin configurar",key_present=bool(settings.llm_api_key.get_secret_value())),
                      execution=dict(ready=ready,detail=reason)))
        elif args.command == "search":
            show(service.retriever.search(args.query,problem_id=args.problem,kinds=args.kind,topic=args.topic,language=args.language,max_level=args.level))
        elif args.command == "serve":
            import uvicorn
            from tutor.api import create_app
            uvicorn.run(create_app(service),host="127.0.0.1",port=args.port,log_level="warning")
        else:
            conversation(service,args.student,args.session)
    except (KeyError,ValueError,OSError,ProviderError,IndexUnavailable) as exc:
        print("Error:",str(exc),file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if service is not None:
            service.close()


if __name__ == "__main__":
    main()
