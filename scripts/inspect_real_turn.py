"""Auditoría interna de una llamada real. No modifica ni simula respuestas del proveedor."""
import json
from pathlib import Path
from tutor.config import Settings
from tutor.models import Attempt
from tutor.provider import ProviderError
from tutor.service import TutorService


def main():
    service=TutorService(Settings())
    real=service.provider
    captures=[]
    class ObservedProvider:
        def generate(self,system,payload,schema):
            result=real.generate(system,payload,schema)
            captures.append(dict(schema=schema.__name__,output=result.model_dump()))
            return result
    service.provider=ObservedProvider()
    sid=service.store.create_student("Auditoría del proveedor real",["variables","bucles"])["id"]
    session=service.start_session(sid,"arr-03")["id"]
    try:
        response=service.turn(sid,session,Attempt(message="¿Qué significa que los días sean consecutivos?"))
        status="completed"
    except ProviderError as exc:
        status=exc.code
    finally:
        service.close()
    result=dict(status=status,provider=service.settings.llm_provider,model=service.settings.llm_model,captures=captures)
    Path("reports/provider-inspection.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
