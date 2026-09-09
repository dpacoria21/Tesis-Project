# Verificación del prototipo — 6 de septiembre de 2026

El recorrido funcional se comprobó con **un LLM local real, embeddings reales y almacenamiento persistente**. No se usaron respuestas simuladas en la integración. También se comprobó Docker con restricciones efectivas. La batería final produjo trece respuestas y dos rechazos de calidad; la evaluación docente sigue pendiente; un recorrido funcional exitoso no garantiza que todas las respuestas futuras sean correctas o pedagógicamente adecuadas.

## Resultados automáticos vigentes

| Verificación | Resultado | Registro |
|---|---|---|
| Pruebas deterministas | **45 superadas** | [deterministic.xml](deterministic.xml) |
| Embeddings, Chroma y BM25 reales | **1 superada** | [real-embeddings.xml](real-embeddings.xml) |
| LLM real: tres turnos, memoria y perfil | **1 superada** | [live-integration.xml](live-integration.xml), [conversación](live-test-session.json), [reinicio entre procesos](release-demo.json) |
| Docker real | **4 superadas** | [docker-integration.xml](docker-integration.xml), [entorno y límites](docker-environment.json) |
| Referencias C++17 propias | **529 comprobaciones superadas** | [references.json](references.json) |
| API HTTP real y consola, proveedor desactivado intencionalmente | Superada: error 503 y conservación del intento | [api-smoke.json](api-smoke.json) |
| API HTTP real y consola, LLM real | Superada: respuesta generada con citas y recuperación de sesión en otro proceso | [api-live.json](api-live.json) |

Las cuatro baterías Pytest vigentes suman **51 pruebas superadas y ninguna omitida**. Los casos «deselected» corresponden a otros marcadores, no a omisiones. Los archivos históricos `external-integration.xml` y los ensayos anteriores registran el estado previo a configurar el proveedor; no representan el resultado actual.

`uv sync --locked` volvió a resolver el entorno fijado y `uv pip check` comprobó **105 paquetes instalados compatibles**. Python 3.12.10; dependencias transitivas y hashes en `uv.lock` y `requirements.lock.txt`. La ruta verificada de instalación es uv; no se realizó una instalación independiente con pip en otra máquina.

## Qué cubren las comprobaciones

- Corpus de 12 problemas originales: cuatro de simulación, cuatro de arreglos y cuatro de búsqueda; ocho conceptos y 80 fragmentos. Ejemplos, resultados esperados independientes y referencias propias C++17 concordantes con pruebas fijas y 40 entradas aleatorias por problema, semilla 20260906.
- Reingesta sin duplicados, filtros aplicados a ambos rankings, fusión por posiciones RRF y persistencia de Chroma. Consulta semántica en inglés que recupera un concepto en español. Detección de cambio de modelo/revisión y de índice ausente.
- Ficha activa por ID exacto, separada de la recuperación; editoriales, referencias C++, pruebas reservadas, candidatos rechazados y trazas excluidos de las respuestas públicas.
- Sesiones y perfiles separados entre estudiantes; recuperación en otro proceso; bloqueo de turnos concurrentes entre consola y API; conservación de intentos fallidos.
- Intervenciones diferentes por necesidad; niveles N0–N3 sin incremento automático; continuación de una explicación conceptual ante «otra pista»; controles de repetición, citas y revelación.
- Evidencia del alumno con cita exacta e interacción. En la integración real se registran una dificultad inicial y una demostración posterior, **ambas provisionales**. Dos problemas distintos son necesarios para confirmar un patrón; la explicación del tutor y un AC declarado no bastan.
- Recomendaciones por objetivo, prerrequisitos, historial y escala local; pregunta concreta ante falta de código; errores y tiempos de espera del proveedor con reintentos limitados y sin sustitución simulada.
- Docker Linux con seccomp y cgroups v2: usuario no root, ausencia de privilegios/capacidades, memoria de 512 MiB, swap cero, cuota de una CPU, 64 procesos, solo loopback y rechazo real de escritura en la raíz. Pruebas de solución correcta, incorrecta, compilación inválida, bucle infinito y salida excesiva.

El compilador del host se utilizó únicamente para referencias originales del repositorio. El código enviado al tutor no tiene una ruta de ejecución en Windows. Docker permanece **desactivado por defecto**, aunque su capacidad aislada ya fue probada; se habilita explícitamente siguiendo `docs/sandbox.md`.

## Servicios reales y reproducción

- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revisión `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, CPU, 384 dimensiones.
- LLM: repositorio oficial `Qwen/Qwen3-14B-GGUF`, archivo Q4_K_M, revisión `530227a7d994db8eca5ab5ced2fb692b614357fd`; llama.cpp b10827 y GPU RTX 5070 Ti. La API de modelos confirmó el ID real utilizado. Sin claves, entrenamiento ni servicios de pago.
- Proveedor mediante el adaptador HTTP sustituible `openai_compatible`; salida restringida por JSON Schema. Una estructura JSON válida no certifica la veracidad del contenido.
- FastAPI/Uvicorn, HTTP y consola en procesos reales. Las respuestas del proveedor se conservan en los registros enlazados; no se solicitaron ni almacenaron cadenas privadas de razonamiento.

En PowerShell, desde la carpeta del proyecto:

```powershell
& scripts/start_local_gpu.ps1
uv run tutor doctor
uv run pytest -q
uv run pytest -q -m real_embeddings
uv run pytest -q -m live
uv run python scripts/smoke_api.py --live
uv run python scripts/demo_session.py --state data/nueva-demo.json --output reports/nueva-demo.json --turns 1
# Cerrar y abrir otra consola en la misma carpeta.
uv run python scripts/demo_session.py --state data/nueva-demo.json --output reports/nueva-demo.json --turns 2
```

Ejecutar las pruebas que usan el LLM **una a la vez**: el proveedor local tiene un único puesto de inferencia. Para otra API se cambian proveedor, URL, ID real y formato en `.env`. Las APIs de formato distinto requieren un adaptador, no una clave inventada ni una promesa de compatibilidad universal.

## Conversaciones, correcciones y límites

La batería real de seis casos y quince mensajes está en [conversations-live.json](conversations-live.json), con perfiles y campos de revisión humana sin inventar. El análisis de sus respuestas visibles está en [CONVERSATION_REVIEW.md](CONVERSATION_REVIEW.md); no se considera revisión docente ni una medida validada de aprendizaje.

Los primeros ensayos detectaron errores reales: confusión entre posiciones y valores, omisión de una pareja vecina, repetición de ejemplos, rechazo de una pista parcial, fórmulas demasiado completas y salidas incompatibles con el esquema. `gpu-demo.json`, `gpu-verified-demo.json`, `final-demo.json`, `qwen3-demo.json`, `acceptance-demo.json`, `conversations-baseline.json` y `conversations-before-final-checks.json` y `conversations-before-brief-feedback.json` son **antecedentes de diagnóstico**, no transcripciones de aceptación final.

Esos hallazgos dieron lugar a evaluación separada del estudiante, controles numéricos acotados, clasificación de continuaciones, límites de longitud/esquema, detección de frases repetidas, protección de la fórmula general de prefijos y reglas explícitas para solicitudes de soluciones completas, dominio basado en AC y aplicaciones sin cobertura léxica. La revisión del contenido sigue siendo falible y puede rechazar una respuesta válida. Los rechazos se conservan y se informan; no se ocultan con respuestas de respaldo.

Los fragmentos largos pueden truncarse al producir su vector, aunque la ficha exacta y el texto almacenado permanecen completos. El clasificador y el perfil son reglas iniciales. La comprobación de cobertura puede pedir contexto ante sinónimos. Los controles no ofrecen una garantía absoluta frente a paráfrasis, filtraciones o errores del modelo.

**Pendiente de revisión humana:** precisión y nivel pedagógico del corpus, utilidad de las pistas, rechazo de estrategias válidas, revelación acumulada y validez de las observaciones del perfil. No se ha realizado un estudio con estudiantes ni una evaluación docente. Los avisos de deprecación de TestClient/HTTPX y BlockingPortal no causaron fallos en las verificaciones vigentes.
