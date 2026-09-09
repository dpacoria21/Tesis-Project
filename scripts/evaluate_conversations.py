"""Ejecuta la batería con LLM real; preserva fallos y deja la rúbrica humana pendiente."""
import json
import argparse
from pathlib import Path
from tutor.config import Settings
from tutor.models import Attempt
from tutor.provider import ProviderError
from tutor.service import TutorService
from tutor.retrieval import IndexUnavailable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("reports/conversations-live.json"))
    parser.add_argument("--data-dir",type=Path)
    args=parser.parse_args()
    service=TutorService(Settings(**({"data_dir":args.data_dir} if args.data_dir else {})))
    if service.settings.llm_provider=="disabled" or not service.settings.llm_model:
        raise SystemExit("Evaluación real pendiente de configurar proveedor; no hay sustitución simulada.")
    service.retriever.ingest()
    suite=json.loads(Path("evaluation/conversations.json").read_text(encoding="utf-8"))
    results=[]
    for case in suite["cases"]:
        sid=service.store.create_student("Evaluación "+case["id"],["variables","bucles","condicionales","aritmetica","arreglos"])["id"]
        session=service.start_session(sid,case["problem_id"])["id"]
        turns=[]
        for message in case["messages"]:
            attempt=Attempt(**message) if isinstance(message,dict) else Attempt(message=message)
            try:
                response=service.turn(sid,session,attempt)
                turns.append(dict(input=message,response=response.model_dump()))
            except (ProviderError,IndexUnavailable) as exc:
                turns.append(dict(input=message,error=getattr(exc,"code","index_unavailable")))
        results.append(dict(case=case["id"],criteria=case["criteria"],turns=turns,profile=service.store.profile(sid),human_scores=None,human_notes=None))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(provider=service.settings.llm_provider,model=service.settings.llm_model,revision=service.settings.llm_revision,results=results),ensure_ascii=False,indent=2),encoding="utf-8")
        print("Caso registrado:",case["id"],flush=True)
    service.close()
    print(f"Batería ejecutada. Completar la rúbrica humana en {args.output}.")
    return 1 if any("error" in turn for result in results for turn in result["turns"]) else 0


if __name__=="__main__":
    raise SystemExit(main())
