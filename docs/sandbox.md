# Ejecución C++17 opcional

El valor inicial es `TUTOR_EXECUTION_ENABLED=false`. La existencia de `docker.exe` no basta. `doctor` y el runner comprueban Docker Linux, seccomp, usuario no root, no-new-privileges y límites de memoria/procesos mediante una prueba en el mismo contenedor restringido. Se exige cgroups v2. Si cualquier comprobación falla, el resultado es **no ejecutado**.

## Preparar una imagen de confianza

Necesitas una imagen Linux local con Python 3, g++ y biblioteca estándar C++17. `sandbox/Dockerfile` permite construirla usando una base Debian con Python elegida y fijada por digest. La construcción es independiente del código del estudiante. No se construye ni descarga una imagen automáticamente durante un intento.

```powershell
docker pull python:3.12-slim-bookworm
$runnerBase = (docker image inspect python:3.12-slim-bookworm | ConvertFrom-Json)[0].RepoDigests[0]
docker build --build-arg "BASE_IMAGE=$runnerBase" -t tutor-cp-runner:verified ./sandbox
$env:TUTOR_DOCKER_IMAGE = (docker image inspect tutor-cp-runner:verified | ConvertFrom-Json)[0].Id
$env:TUTOR_EXECUTION_ENABLED = 'true'
uv run tutor doctor
uv run pytest -q -m docker
```

Se aceptan un ID local `sha256:...` o una referencia `nombre@sha256:...`, siempre reales. La imagen final queda fijada por contenido; el Dockerfile por sí solo no promete reconstruir exactamente los paquetes del sistema disponibles en una fecha distinta.

El 6 de septiembre de 2026 se construyó y probó la base oficial `python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254` con Docker Desktop Linux 29.5.2 y cgroups v2. La etiqueta local preparada es `tutor-cp-runner:verified`; consulta su ID real antes de habilitarla. `reports/docker-integration.xml` registra cuatro pruebas reales, sin omisiones. La configuración inicial permanece desactivada: habilitarla permite ejecutar únicamente cuando el estudiante lo solicita explícitamente.

## Condiciones aplicadas

- Red deshabilitada, raíz de archivos de solo lectura, todas las capacidades eliminadas, sin privilegios adicionales, usuario 65534.
- El sondeo interno comprueba interfaces de red (solo loopback), capacidades efectivas vacías, cuota de CPU, swap deshabilitado y rechazo real de escritura en la raíz, además de seccomp, memoria y procesos. No basta con construir una lista de argumentos Docker.
- 512 MiB de memoria y swap total, una CPU, 64 procesos, 64 descriptores, sin core dumps.
- Solo `/tmp` escribible en tmpfs de 64 MiB; no se monta el proyecto, un directorio del host, credenciales ni el socket Docker.
- Código y casos enviados por stdin a un supervisor fijo dentro del contenedor. Tanto compilación como ejecución están aisladas.
- Tiempo de compilación y ejecución limitado; cada caso tiene 2 segundos de pared, procesos hijos agrupados y eliminados al terminar. Tamaño de archivo limitado a 2 MiB; salida leída por caso a 16 KiB. El cliente host también limita la salida total del supervisor a 16 KiB y destruye el contenedor ante timeout o exceso.
- Solo se devuelve resumen de pruebas, nunca entradas reservadas ni salidas del supervisor. «Supera las pruebas disponibles» no significa aceptación oficial ni corrección demostrada.

El aislamiento mediante contenedores depende de la seguridad del motor y el kernel. Esta capacidad es un prototipo local, no un servicio público para adversarios. No hay alternativa que ejecute código del estudiante en Windows cuando Docker no está disponible.

`scripts/verify_references.py` es una herramienta de desarrollo diferente: verifica exclusivamente las referencias **propias incluidas** con el compilador del desarrollador. No acepta archivos del alumno ni material importado y no habilita la ejecución en el tutor.
