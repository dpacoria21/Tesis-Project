"""Compila SOLO las 12 referencias propias del archivo demo del repositorio.

No acepta rutas de código, importaciones ni intentos de estudiantes. El runner del tutor
es una capacidad diferente que siempre exige Docker.
"""
import argparse
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from tutor.models import Corpus
from tutor.reference import solve


def random_inputs(pid,rng,count):
    for _ in range(count):
        n=rng.randint(1,12)
        a=[rng.randint(-10,10) for _ in range(n)]
        if pid=="sim-01":
            yield f"{n} 1000\n"+" ".join(map(str,a))+"\n"
        elif pid=="sim-02":
            yield f"{rng.randrange(24)} {rng.randint(0,1000000)} {rng.randint(0,1000000000)}\n"
        elif pid=="sim-03":
            yield f"{n}\n"+" ".join(str(rng.randrange(4)) for _ in range(n))+"\n"
        elif pid=="sim-04":
            yield f"{n}\n"+" ".join(str(abs(x)) for x in a)+"\n"
        elif pid=="arr-04":
            ranges=[]
            for _ in range(8):
                l=rng.randint(1,n);r=rng.randint(l,n);ranges.append(f"{l} {r}")
            yield f"{n} 8\n"+" ".join(map(str,a))+"\n"+"\n".join(ranges)+"\n"
        elif pid.startswith("arr-"):
            yield f"{n}\n"+" ".join(map(str,a))+"\n"
        elif pid=="bus-04":
            yield str(rng.randint(1,10**12))+"\n"
        else:
            if pid=="bus-02": a.sort()
            yield f"{n} {rng.randint(-10,10)}\n"+" ".join(map(str,a))+"\n"


def verify(samples=40):
    compiler=shutil.which("g++")
    if not compiler:
        raise RuntimeError("No se encontró g++ para verificar referencias propias; el runner del estudiante permanece separado.")
    corpus=Corpus.model_validate_json(Path("corpus/demo.json").read_text(encoding="utf-8"))
    assert len(corpus.problems)==12 and all(p.provenance.kind=="original_demo" for p in corpus.problems)
    results=[]
    rng=random.Random(20260906)
    with tempfile.TemporaryDirectory(prefix="tutor-own-references-") as folder:
        root=Path(folder)
        for p in corpus.problems:
            source=root/(p.id+".cpp")
            binary=root/(p.id+".exe")
            source.write_text(p.reference_cpp,encoding="utf-8")
            subprocess.run([compiler,"-std=c++17","-O2",str(source),"-o",str(binary)],check=True,capture_output=True,timeout=30)
            cases=[(t.input,t.output) for t in p.tests+p.examples]
            cases += [(raw,solve(p.id,raw)) for raw in random_inputs(p.id,rng,samples)]
            for raw,expected in cases:
                result=subprocess.run([str(binary)],input=raw,text=True,capture_output=True,check=True,timeout=3)
                if result.stdout.split()!=expected.split():
                    raise AssertionError(f"Referencia inconsistente: {p.id}")
            results.append(dict(problem=p.id,passed=len(cases)))
    return dict(scope="Solo referencias C++17 originales, nunca código del estudiante",compiler=compiler,seed=20260906,results=results,total=sum(r["passed"] for r in results))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=Path("reports/references.json"))
    args=parser.parse_args()
    report=verify()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
