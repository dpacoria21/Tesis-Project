"""C++17 solo en Docker verificado. No hay ruta de ejecución local alternativa."""
import json
import re
import subprocess
import threading
import uuid
from tutor.models import CheckResult

# Este supervisor fijo corre DENTRO del contenedor; recibe código y pruebas por stdin.
SUPERVISOR = r'''
import errno, json, os, pathlib, resource, signal, subprocess, sys, tempfile
def probe():
    assert os.getuid()!=0
    status=pathlib.Path('/proc/self/status').read_text()
    assert 'Seccomp:\t2' in status and 'NoNewPrivs:\t1' in status
    assert int(pathlib.Path('/sys/fs/cgroup/memory.max').read_text()) <= 536870912
    assert int(pathlib.Path('/sys/fs/cgroup/pids.max').read_text()) <= 64
    quota,period=map(int,pathlib.Path('/sys/fs/cgroup/cpu.max').read_text().split())
    assert quota <= period
    assert int(pathlib.Path('/sys/fs/cgroup/memory.swap.max').read_text()) == 0
    assert int(next(s.split(':',1)[1].strip() for s in status.splitlines() if s.startswith('CapEff:')),16)==0
    assert set(os.listdir('/sys/class/net')) <= {'lo'}
    try:
        fd=os.open('/tutor-readonly-probe',os.O_CREAT|os.O_WRONLY,0o600)
    except OSError as exc:
        assert exc.errno==errno.EROFS
    else:
        os.close(fd); os.unlink('/tutor-readonly-probe'); raise AssertionError('Root filesystem is writable')
probe()
payload=json.load(sys.stdin)
if payload.get('probe'):
    assert subprocess.run(['g++','--version'],stdout=subprocess.DEVNULL,timeout=3).returncode==0
    print(json.dumps({'ready':True})); sys.exit()
def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_CPU,(3,3))
def execute(args, raw, seconds):
    with tempfile.TemporaryFile() as output:
        p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=output,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
        try: p.communicate(raw,timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL); p.communicate()
            return -1,b'',True
        # Elimina descendientes que sobrevivieran a la salida del proceso principal.
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        output.seek(0); data=output.read(16385)
        return p.returncode,data,len(data)>16384
with tempfile.TemporaryDirectory(dir='/tmp') as folder:
    os.chdir(folder)
    pathlib.Path('main.cpp').write_text(payload['code'])
    result,_,exceeded=execute(['g++','-std=c++17','-O0','-pipe','main.cpp','-o','main'],b'',12)
    if result or exceeded:
        print(json.dumps({'status':'error de compilación','passed':0,'total':len(payload['tests'])})); sys.exit()
    passed=0
    for case in payload['tests']:
        result,out,exceeded=execute(['./main'],case['input'].encode(),2)
        if result==0 and not exceeded and out.decode(errors='replace').split()==case['output'].split(): passed+=1
    print(json.dumps({'status':'supera las pruebas disponibles' if passed==len(payload['tests']) else 'no supera las pruebas disponibles','passed':passed,'total':len(payload['tests'])}))
'''


class DockerRunner:
    def __init__(self, settings):
        self.settings = settings

    def command(self, name):
        return ["docker","run","--rm","--pull=never","--name",name,"--network=none","--read-only",
                "--cap-drop=ALL","--security-opt=no-new-privileges:true","--user=65534:65534",
                "--memory=512m","--memory-swap=512m","--cpus=1","--pids-limit=64",
                "--ulimit","nofile=64:64","--ulimit","fsize=2097152:2097152",
                "--tmpfs","/tmp:rw,nosuid,nodev,exec,size=67108864,mode=1777",
                "--env","HOME=/tmp","--env","PYTHONDONTWRITEBYTECODE=1","--log-driver=none",
                "-i","--entrypoint","python3",self.settings.docker_image,"-c",SUPERVISOR]

    def _run(self, payload, timeout):
        name = "tutor-"+uuid.uuid4().hex
        try:
            proc = subprocess.Popen(self.command(name),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            output = bytearray()
            size = [0]
            lock = threading.Lock()
            exceeded = threading.Event()
            def drain(stream, keep):
                while chunk := stream.read(4096):
                    with lock:
                        size[0] += len(chunk)
                        if size[0] > 16384:
                            exceeded.set()
                            proc.kill()
                            return
                        if keep:
                            output.extend(chunk)
            readers = [threading.Thread(target=drain,args=(proc.stdout,True),daemon=True),threading.Thread(target=drain,args=(proc.stderr,False),daemon=True)]
            for reader in readers:
                reader.start()
            # El envío también se limita en el tiempo si el contenedor deja de leer stdin.
            def feed():
                try:
                    proc.stdin.write(json.dumps(payload).encode())
                    proc.stdin.close()
                except (BrokenPipeError,OSError):
                    pass
            writer = threading.Thread(target=feed,daemon=True)
            writer.start()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                raise
            for reader in readers:
                reader.join(timeout=2)
            if proc.returncode or exceeded.is_set() or any(t.is_alive() for t in readers):
                raise RuntimeError("Fallo del entorno aislado")
            return json.loads(output)
        finally:
            # También limpia el contenedor cuando el cliente Docker agota su tiempo.
            try:
                subprocess.run(["docker","rm","-f",name],capture_output=True,timeout=5)
            except (OSError,subprocess.SubprocessError):
                pass

    def availability(self):
        if not self.settings.execution_enabled:
            return False,"La ejecución aislada está desactivada por configuración."
        if not re.fullmatch(r"(?:[^\s]+@)?sha256:[0-9a-f]{64}",self.settings.docker_image):
            return False,"Se requiere una imagen local de confianza fijada por digest sha256."
        try:
            info = subprocess.run(["docker","info","--format","{{json .}}"],capture_output=True,timeout=5,check=True)
            metadata = json.loads(info.stdout)
            if metadata.get("OSType") != "linux" or not any("seccomp" in s for s in metadata.get("SecurityOptions",[])):
                return False,"Se requiere Docker Linux con seccomp."
            ready = self._run({"probe":True},15).get("ready")
            return bool(ready),"Aislamiento comprobado." if ready else "No se verificaron los límites."
        except (OSError,subprocess.SubprocessError,RuntimeError,ValueError,KeyError):
            return False,"Docker o los límites requeridos no están disponibles; no ejecutado."

    def run(self, code, tests):
        ready, reason = self.availability()
        if not ready:
            return CheckResult(detail=reason)
        try:
            result = self._run({"code":code,"tests":[t.model_dump() for t in tests]},20+len(tests)*3)
            return CheckResult(**result,origin="prototipo",detail="Comprobación local limitada a las pruebas disponibles; no es aceptación oficial.")
        except (OSError,subprocess.SubprocessError,RuntimeError,ValueError,KeyError):
            return CheckResult(detail="El aislamiento falló; no se obtuvo un resultado verificable.")
