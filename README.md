# Tutor CP — prototipo local

Tutor para ingresantes con programación básica. Backend Python/FastAPI, consola en español, ejercicios C++17, memoria SQLite y recuperación real BM25 + Chroma. Un único servicio modular, sin frontend, agentes autónomos ni despliegue público.

**Estado:** implementado; verificados embeddings reales, sesiones persistentes, API/consola, referencias C++17 y ejecución restringida en Docker. Se preparó un LLM local real y sustituible, sin claves. Los resultados y límites de las conversaciones reales están en [el informe de verificación](reports/VERIFICATION.md); las pruebas funcionales no certifican calidad pedagógica universal ni sustituyen una revisión docente.

## Instalación en Windows / PowerShell

Requisitos: Python 3.12 y `uv`. Se verificaron Python 3.12.10 y compatibilidad de dependencias mediante resolución e instalación. `uv.lock` fija dependencias transitivas y hashes; no actualizar versiones durante una reproducción.

```powershell
Set-Location 'C:\Users\diego\OneDrive\Desktop\tesis-pc'
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run tutor validate-corpus
uv run tutor ingest
uv run tutor doctor
uv run tutor serve
```

El servicio escucha únicamente en `127.0.0.1:8000`. Documentación interactiva: [API local](http://127.0.0.1:8000/docs). Abre otra consola para `uv run tutor chat`. No necesitas activar manualmente el entorno virtual.

En este equipo ya se preparó la opción local con GPU. Después de reiniciar Windows, inicia primero `& scripts/start_local_gpu.ps1`. Para prepararla en otra instalación o cambiar a CPU/API remota, consulta [proveedores locales](docs/local-llm.md). La configuración del proveedor es independiente del tutor y se puede cambiar en `.env`.

La primera ingesta descarga el modelo público de embeddings; las posteriores reutilizan la caché. El corpus de 12 problemas viene incluido y no requiere extraer sitios externos. La API carga automáticamente el catálogo al comenzar, pero la indexación se hace explícitamente con `ingest` para que el arranque no descargue modelos de forma inesperada.

Si prefieres pip, `requirements.lock.txt` contiene las dependencias con hashes, sin el proyecto editable: crea un entorno Python 3.12, instala con `pip install --require-hashes -r requirements.lock.txt` y luego `pip install --no-deps -e .`. La ruta principal probada es `uv sync --locked`.

## Uso de la consola

```powershell
uv run tutor chat
uv run tutor chat --student ID_ESTUDIANTE --session ID_SESION
```

Selecciona un estudiante existente o escribe un nombre nuevo. Elige una sesión anterior o un problema. Los conocimientos básicos declarados inicialmente son variables, bucles, condicionales y aritmética; no se presentan como dominio confirmado.

Comandos durante la conversación:

| Comando | Función |
|---|---|
| `/codigo C:\ruta\intento.cpp` | Adjunta código al próximo mensaje; no lo ejecuta |
| `/ejecutar` | Solicita comprobar el próximo código dentro del aislamiento |
| `/perfil` | Muestra observaciones y las interacciones que las respaldan |
| `/recomendar [tema]` | Propone ejercicios elegibles y explica el motivo |
| `/problema arr-02` | Crea un estado de resolución independiente conservando el perfil |
| `/salir` | Sale; estudiantes, sesión, intentos y pistas permanecen guardados |

Sin LLM puedes consultar catálogo, perfiles, recomendaciones y sesiones, ingerir y buscar evidencia, y recibir preguntas estructurales por datos indispensables faltantes. Una petición que exige generación devuelve un error explícito de configuración; **no hay un tutor simulado de respaldo**.

## API

| Método y ruta | Uso |
|---|---|
| `GET /health` | Servicio, catálogo, índice y estado de configuración |
| `POST /students` | `{ "name": "Ana", "basics": ["variables", "bucles"] }` |
| `GET /students` | Estudiantes locales |
| `GET /problems` y `/problems/{id}` | Fichas públicas, sin editoriales ni pruebas reservadas |
| `POST /students/{id}/sessions` | `{ "problem_id": "arr-03" }` |
| `GET /students/{id}/sessions` | Sesiones del estudiante |
| `GET /students/{id}/sessions/{session}` | Intentos y respuestas públicas anteriores |
| `POST /students/{id}/sessions/{session}/attempts` | Mensaje, código opcional y petición de comprobación |
| `GET /students/{id}/profile` | Evidencia del perfil |
| `GET /students/{id}/recommendations?goal=prefijos&max_difficulty=3` | Recomendaciones por objetivo |

Ejemplo PowerShell:

```powershell
$base = 'http://127.0.0.1:8000'
$student = Invoke-RestMethod "$base/students" -Method Post -ContentType 'application/json; charset=utf-8' -Body '{"name":"Ana"}'
$session = Invoke-RestMethod "$base/students/$($student.id)/sessions" -Method Post -ContentType 'application/json; charset=utf-8' -Body '{"problem_id":"arr-03"}'
$body = @{message='¿Qué significa días consecutivos?'; need='comprension'} | ConvertTo-Json
Invoke-RestMethod "$base/students/$($student.id)/sessions/$($session.id)/attempts" -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

`need` es opcional: `comprension`, `concepto`, `idea`, `depuracion`, `practica`. `reported_result` conserva lo informado por el estudiante o un juez como **no verificado**. `checks` es la única comprobación del prototipo; `code_observation` es lectura estática. El esquema de turno incluye mensaje, intervención, nivel, citas permitidas y estado real de ejecución. Fallos del proveedor o del índice producen HTTP 503 y conservan el intento; entradas inválidas producen 422; una sesión que no pertenece al estudiante indicado produce 404.

No hay autenticación: el identificador separa datos funcionalmente, pero no impide que alguien con acceso al servicio local y a los IDs consulte otro estudiante. No exponer el servicio a una red. Usa un solo servidor; las llamadas de consola y API comparten un candado local que evita decidir simultáneamente sobre el mismo historial.

## Elegir un proveedor remoto o local

Todos los ajustes se leen de `.env` o variables `TUTOR_*`. El contrato reemplazable es `LLMProvider.generate(system, payload, schema)` en `tutor/provider.py`.

Adaptadores reales incluidos:

| Proveedor | Configuración |
|---|---|
| Ollama nativo | `TUTOR_LLM_PROVIDER=ollama`, `TUTOR_LLM_BASE_URL=http://localhost:11434` |
| API compatible con Chat Completions | `TUTOR_LLM_PROVIDER=openai_compatible`, `TUTOR_LLM_BASE_URL=URL_BASE_DEL_SERVICIO/v1` |
| Transformers en CPU, dentro del proceso | `TUTOR_LLM_PROVIDER=transformers_local`, modelo y revisión exactos de Hugging Face |

Para Ollama o servidores locales compatibles no se exige clave. Las APIs remotas deben usar HTTPS; si requieren credencial, configura `TUTOR_LLM_API_KEY` mediante el mecanismo seguro del proveedor, sin enviarla al chat ni versionarla. No existe un nombre de modelo LLM predeterminado: consulta los identificadores reales con `uv run tutor models`, elige uno y establece `TUTOR_LLM_MODEL`.

Ejemplo para **consultar** un Ollama ya instalado, sin inventar un modelo:

```powershell
$env:TUTOR_LLM_PROVIDER = 'ollama'
$env:TUTOR_LLM_BASE_URL = 'http://localhost:11434'
uv run tutor models
# Asigna TUTOR_LLM_MODEL a un identificador real de esa salida.
uv run tutor doctor
uv run python scripts/demo_session.py
```

La compatibilidad remota requiere `POST /chat/completions`, mensajes system/user, `response_format: json_object`, `max_tokens` y respuesta `choices[0].message.content`. Ollama usa `/api/chat`, `format` con JSON Schema y `stream=false`. El adaptador no significa compatibilidad automática con todas las APIs públicas: para Anthropic, Gemini u otra forma de autenticación/formato, implementa el mismo protocolo o usa una pasarela compatible. No se sustituye silenciosamente un proveedor incompatible.

Cada turno generado hace una generación y una revisión de contenido; los turnos de idea/depuración añaden antes una evaluación separada del intento del estudiante. Puede repetirse una vez la generación rechazada. Cada llamada HTTP tiene reintentos limitados (`TUTOR_LLM_RETRIES`, 0–3) y tiempo de espera (`TUTOR_LLM_TIMEOUT`). `TUTOR_LLM_RESPONSE_FORMAT=json_schema` activa restricciones de formato cuando el servidor las soporta; el valor inicial `json_object` sirve para compatibilidad básica. No se registran encabezados, cuerpos de error del proveedor ni campos de razonamiento privado.

## Demostración de varios turnos y reinicio

Una vez configurado un proveedor real:

```powershell
uv run python scripts/demo_session.py --turns 1
# Cerrar el programa y abrir otra consola en esta carpeta.
uv run python scripts/demo_session.py --turns 2
```

La segunda ejecución retoma los IDs guardados en `data/demo-session.json`; `reports/live-demo.json` contiene las respuestas realmente recibidas y el perfil, con revisión humana pendiente. Si no hay LLM, el script termina indicando exactamente esa falta; nunca fabrica una conversación. Para otra demostración usa `--state data/otra-demo.json --output reports/otra-demo.json`.

El caso parte de una aclaración, revisa una idea que confunde todos los pares con vecinos y recibe una explicación corregida del estudiante. Las palabras del LLM no son reproducibles bit a bit; sí lo son el corpus, el estado, la secuencia de entradas y los registros de comprobación.

## Recuperación e importación

```powershell
uv run tutor search 'sumas de prefijos cancelar parte compartida' --kind concept --level 2
uv run tutor search 'primer máximo' --problem arr-02 --kind hint --level 1 --language es
uv run tutor ingest --file corpus/demo.json
uv run tutor ingest --file C:\ruta\material.jsonl
uv run tutor ingest --rebuild
```

RRF combina **posiciones** de BM25 y distancia coseno vectorial: suma `1/(60+rango)` por lista. No se suman puntuaciones de escalas diferentes. Los IDs y metadatos son comunes. BM25 se reconstruye sobre los fragmentos elegibles de SQLite en cada consulta (80 fragmentos iniciales); Chroma persiste los vectores. Los filtros se aplican a ambos candidatos antes de ordenar. La ficha del problema activo se obtiene siempre por ID, fuera del ranking.

Se conservan unidades semánticas completas: enunciado con restricciones, cada pista, cada editorial y cada concepto. La relación `concept_ids` enlaza problemas y conceptos. El tutor recupera las pistas del problema activo y conceptos enlazados; la búsqueda de consola admite filtros generales. El editorial se indexa para uso interno con nivel 99 y no entra en la tutoría N0–N3. Tampoco se envía código de referencia ni pruebas reservadas al generador.

El manifiesto `data/index.json` guarda modelo, revisión exacta, normalización, versión de fragmentación y hash del catálogo. La ingesta usa upsert sin duplicados. Cambiar el corpus exige reingerir; cambiar modelo/revisión exige `--rebuild`. La caché y colecciones anteriores pueden ocupar espacio; no se borran automáticamente datos del usuario.

Lee [formato de importación](docs/import.md) y [arquitectura y límites](docs/architecture.md).

## Verificación

```powershell
uv run pytest -q
uv run pytest -q -m real_embeddings
uv run python scripts/verify_references.py
uv run pytest -q -m live
uv run pytest -q -m docker
uv run python scripts/evaluate_conversations.py
uv run python scripts/verify_essential_cases.py --repeats 3
uv run python scripts/smoke_api.py
uv run python scripts/smoke_api.py --live
```

Las pruebas deterministas usan dobles **solo en `tests/`**, claramente identificados. Las pruebas `real_embeddings` usan Sentence Transformers y Chroma reales; `live` exige un LLM real; `docker` exige aislamiento verificado. Una prueba omitida no equivale a una prueba superada. El verificador C++ compila únicamente referencias propias incluidas en el repositorio, nunca código de estudiantes ni importaciones externas.

La batería `evaluation/conversations.json` revisa estrategias alternativas, errores, repetición, pistas acumuladas, instrucciones incrustadas y evidencia insuficiente. `scripts/evaluate_conversations.py` guarda respuestas reales con campos para puntuar corrección, utilidad, respaldo y trabajo significativo restante. La evaluación pedagógica requiere revisión humana, no solo coincidencia textual. Véase [resultados verificados](reports/VERIFICATION.md).

La regresión `evaluation/essential-cases.json` conserva los dos historiales originales de empates y prefijos, más una variante de cada uno. El verificador repite sesiones independientes con el proveedor y los embeddings reales, crea directorios únicos bajo `reports/essential-cases/` y `data/essential-verification/`, y devuelve error ante rechazos o incumplimientos observables. Las respuestas y las trazas se conservan completas para revisar su contenido; pasar las comprobaciones automáticas no sustituye esa lectura.

## Diagnóstico

- **Proveedor sin configurar / 401 / 403:** comprueba `doctor`, URL y acceso del proveedor. No imprimas `.env`. La clave es opcional para servicios que no la requieren. Un error de credencial no provoca reintentos repetidos.
- **Modelo inexistente / formato incompatible:** consulta `models`; elige un ID de esa instancia. Un servicio que no acepta JSON estructurado necesita ajustar el adaptador; no se falsea una respuesta válida.
- **Timeout / límite de uso:** revisa el servidor y `TUTOR_LLM_TIMEOUT`; los reintentos son limitados. Los intentos fallidos permanecen en la sesión.
- **Embeddings:** primera descarga pública desde Hugging Face; requiere red y espacio de caché. El aviso de enlaces simbólicos en Windows no impide trabajar. No se exige un token privado para el modelo incluido. Para uso sin red, descarga una vez y conserva la caché; puedes activar `HF_HUB_OFFLINE=1` después.
- **Índice desactualizado:** `uv run tutor ingest`; ante cambio de modelo/revisión, `--rebuild`. Cambia ambas variables si eliges otro modelo. No renombres un índice para saltarte la comprobación.
- **Docker:** `doctor` devuelve «no ejecutado» si está deshabilitado. Para habilitarlo, sigue [aislamiento](docs/sandbox.md). Si el motor no está encendido, no se ejecuta código. El recorrido conceptual no depende de Docker.
- **Caracteres españoles en PowerShell:** configura `$env:PYTHONUTF8='1'` antes de ejecutar. Los archivos y datos se guardan como UTF-8.
- **Respaldo:** detén consola/servicio y copia `data/` junto con tu corpus. SQLite contiene código y mensajes de estudiantes; conserva ese directorio en un entorno privado.

## Documentación oficial consultada

- [FastAPI: pruebas con TestClient](https://fastapi.tiangolo.com/tutorial/testing/).
- [Chroma: cliente persistente](https://docs.trychroma.com/reference/python/client).
- [Sentence Transformers: modelos preentrenados](https://www.sbert.net/docs/sentence_transformer/pretrained_models.html) y [ficha del modelo multilingüe](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
- [Ollama: chat](https://docs.ollama.com/api/chat), [modelos](https://docs.ollama.com/api/tags) y [compatibilidad Chat Completions](https://docs.ollama.com/api/openai-compatibility).
- [Docker: límites y ejecución de contenedores](https://docs.docker.com/engine/containers/run/).

Versiones directas consultadas en metadatos oficiales de PyPI y resueltas antes de instalar. No se incorporó LangChain ni infraestructura distribuida.
