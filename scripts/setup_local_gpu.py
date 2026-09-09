"""Prepara un proveedor local opcional y reproducible; no modifica Python ni instala servicios.

Binarios oficiales llama.cpp y modelo oficial Qwen, con versiones verificadas.
Solo descarga/extracción. El arranque separado se limita a localhost.
"""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path
from huggingface_hub import snapshot_download

RELEASE="b10827"
ASSETS=[
    ("llama-b10827-bin-win-cuda-13.3-x64.zip","2cfaafa0eb7a8de46c6f09ac7b8c4a39f4598dfd3ec61c047290afa521d4e69d"),
    ("cudart-llama-bin-win-cuda-13.3-x64.zip","1462a050eb4c684921ba51dcc4cc488a036674c3e73e9945ee705b854808d03e"),
]
MODEL="Qwen/Qwen3-14B-GGUF"
REVISION="530227a7d994db8eca5ab5ced2fb692b614357fd"
MODEL_FILE="Qwen3-14B-Q4_K_M.gguf"
MODEL_SHA256="500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0"


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def main():
    root=Path(".runtime/llama-b10827").resolve()
    root.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,expected in ASSETS:
        archive=root/name
        url=f"https://github.com/ggml-org/llama.cpp/releases/download/{RELEASE}/{name}"
        if not archive.exists():
            print("Descargando runtime oficial:",name,flush=True)
            urllib.request.urlretrieve(url,archive)
        actual=checksum(archive)
        if actual!=expected:
            raise RuntimeError("Hash no coincide; no se extraerá "+name)
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                if not (root/entry.filename).resolve().is_relative_to(root):
                    raise RuntimeError("Ruta fuera del directorio del runtime")
            package.extractall(root)
        records.append(dict(url=url,sha256=actual))
    print("Descargando modelo oficial cuantizado:",MODEL,flush=True)
    model_root=Path(snapshot_download(MODEL,revision=REVISION,allow_patterns=[MODEL_FILE]))
    files=[model_root/MODEL_FILE]
    if checksum(files[0])!=MODEL_SHA256:
        raise RuntimeError("El modelo no coincide con el hash publicado")
    binaries=list(root.rglob("llama-server.exe"))
    if len(binaries)!=1:
        raise RuntimeError("No se identificó un único llama-server.exe")
    manifest=dict(runtime_release=RELEASE,assets=records,executable=str(binaries[0]),model_repository=MODEL,model_revision=REVISION,
                  model_path=str(files[0]),model_parts=[dict(path=str(p),sha256=checksum(p)) for p in files])
    Path("data").mkdir(exist_ok=True)
    manifest_path=Path("data/local-gpu-runtime.json")
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text(encoding="utf-8"))
        if old["model_revision"]!=REVISION:
            Path("data/local-gpu-runtime-previous.json").write_text(json.dumps(old,indent=2),encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print("Runtime preparado. Manifiesto: data/local-gpu-runtime.json",flush=True)


if __name__=="__main__":
    main()
