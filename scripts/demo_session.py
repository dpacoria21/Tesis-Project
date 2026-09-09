"""Demostración real reproducible. No incluye un proveedor simulado."""
import argparse
import json
from pathlib import Path
from tutor.config import Settings
from tutor.models import Attempt
from tutor.provider import ProviderError
from tutor.service import TutorService


MESSAGES = [
    "¿Qué significa que los días sean consecutivos?",
    "Mi idea compara todos los pares de días porque cualquier aumento me parece una subida. ¿Es válido?",
    "Ahora comparo solo vecinos: para [1,3,3,2] cuento una subida porque la igualdad no es un aumento estricto.",
]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--state",type=Path,default=Path("data/demo-session.json"))
    parser.add_argument("--output",type=Path,default=Path("reports/live-demo.json"))
    parser.add_argument("--turns",type=int,default=3,choices=[1,2,3])
    args=parser.parse_args()
    service=TutorService(Settings())
    if service.settings.llm_provider=="disabled" or not service.settings.llm_model:
        raise SystemExit("Prueba real pendiente: configura proveedor, URL y modelo. No se sustituye por una conversación simulada.")
    if service.settings.llm_model not in service.provider.models():
        raise SystemExit("El modelo configurado no aparece en el catálogo real del proveedor.")
    if not service.retriever.ready():
        service.retriever.ingest()
    if args.state.exists():
        state=json.loads(args.state.read_text(encoding="utf-8"))
        session=service.store.session(state["student_id"],state["session_id"])
        index=sum(t["status"]=="completed" for t in session["interactions"])
    else:
        sid=service.store.create_student("Demostración real",["variables","bucles","condicionales","aritmetica"])["id"]
        session_id=service.start_session(sid,"arr-03")["id"]
        state=dict(student_id=sid,session_id=session_id)
        args.state.parent.mkdir(parents=True,exist_ok=True)
        args.state.write_text(json.dumps(state,indent=2),encoding="utf-8")
        index=0
    for message in MESSAGES[index:index+args.turns]:
        response=service.turn(state["student_id"],state["session_id"],Attempt(message=message))
        print("Estudiante:",message)
        print("Tutor:",response.message)
    report=dict(provider=service.settings.llm_provider,model=service.settings.llm_model,revision=service.settings.llm_revision,embeddings=service.retriever.config(),
        session=service.store.session(state["student_id"],state["session_id"]),profile=service.store.profile(state["student_id"]),human_review="pendiente")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Registro real:",args.output)
    service.close()


if __name__=="__main__":
    try:
        main()
    except ProviderError as exc:
        raise SystemExit(str(exc)) from None
