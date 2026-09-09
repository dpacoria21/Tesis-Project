"""Comprueba HTTP real, consola y reinicio sin sustituir el proveedor de generación."""
import json
import argparse
import os
import socket
import site
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true",help="Exige generación mediante el proveedor real configurado")
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="tutor-http-smoke-") as folder:
        env=dict(os.environ,TUTOR_DATA_DIR=folder,PYTHONUTF8="1")
        if not args.live:
            env["TUTOR_LLM_PROVIDER"]="disabled"
        kwargs={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
        # Chroma mantiene archivos abiertos: ingerir en otro proceso permite limpiar en Windows.
        subprocess.run([sys.executable,"-m","tutor.cli","ingest"],env=env,capture_output=True,check=True,timeout=180,**kwargs)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        # El ejecutable base evita el lanzador de venv que crea otro proceso en Windows.
        # Las bibliotecas siguen siendo exactamente las del entorno fijado del proyecto.
        env["PYTHONPATH"]=os.pathsep.join(site.getsitepackages()+[env.get("PYTHONPATH","")])
        proc=subprocess.Popen([sys._base_executable,"-m","tutor.cli","serve","--port",str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}",timeout=30) as client:
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError("El servidor terminó antes de estar disponible")
                    try:
                        health=client.get("/health")
                        if health.status_code==200: break
                    except httpx.ConnectError:
                        pass
                    time.sleep(.1)
                else: raise RuntimeError("Servidor no disponible")
                assert health.json()["index_ready"]
                sid=client.post("/students",json={"name":"Prueba HTTP real"}).json()["id"]
                session=client.post(f"/students/{sid}/sessions",json={"problem_id":"arr-01"}).json()["id"]
                base=f"/students/{sid}/sessions/{session}"
                question=client.post(base+"/attempts",json={"message":"Mi código falla","need":"depuracion"})
                assert question.status_code==200 and "Comparte el código" in question.json()["message"]
                recommendations=client.post(base+"/attempts",json={"message":"Recomienda ejercicios","need":"practica"})
                assert recommendations.status_code==200
                unavailable=client.post(base+"/attempts",json={"message":"¿Qué pide el problema?"})
                if args.live:
                    assert unavailable.status_code==200, unavailable.text
                    assert unavailable.json()["message"] and unavailable.json()["sources"]
                else:
                    assert unavailable.status_code==503 and unavailable.json()["code"]=="not_configured"
                history=client.get(base).json()
                assert len(history["interactions"])==3
                assert history["interactions"][-1]["status"]==("completed" if args.live else "failed")
                assert "trace" not in json.dumps(history)
                catalog=client.get("/problems").json()
                assert len(catalog)==12 and "reference_cpp" not in json.dumps(catalog)
            # Consola real en otro proceso retoma exactamente esa sesión y sale.
            console=subprocess.run([sys.executable,"-m","tutor.cli","chat","--student",sid,"--session",session],input="/salir\n",capture_output=True,text=True,encoding="utf-8",env=env,timeout=20,**kwargs)
            assert console.returncode==0 and session in console.stdout and "Comparte el código" in console.stdout
            result=dict(http_server="uvicorn real en localhost",catalog_count=12,persisted_interactions=3,
                public_projection="verified",missing_code_question="verified",recommendation="verified",
                llm_failure="no inducido" if args.live else "503 not_configured; intento conservado",console_resume="verified in another process",
                embeddings="Sentence Transformers reales",llm_real="respuesta real incluida" if args.live else "desactivado intencionalmente en esta prueba de manejo de fallos; no se simuló")
            if args.live:
                result["generated_response"]=unavailable.json()
        finally:
            if os.name=="nt" and proc.poll() is None:
                # El lanzador de venv Windows puede crear un hijo: detener todo SU árbol.
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True,timeout=10)
            elif proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/api-live.json" if args.live else "reports/api-smoke.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
