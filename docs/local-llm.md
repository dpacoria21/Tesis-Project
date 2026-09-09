# Proveedores locales sin credenciales

## Opción preparada en este equipo: GPU y API compatible

El tutor puede usar una API pública o local. Para comprobarlo sin claves se preparó **Qwen3-14B-GGUF Q4_K_M**, desde el repositorio oficial `Qwen/Qwen3-14B-GGUF`, revisión `530227a7d994db8eca5ab5ced2fb692b614357fd`. El archivo publicado tiene 9.001.752.960 bytes y SHA-256 `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0`. Se usa llama.cpp `b10827` con binarios oficiales CUDA 13.3, cuyos hashes comprueba el preparador.

```powershell
# Preparación inicial; descarga unos 9 GB de modelo y 541 MB de runtime.
uv run python scripts/setup_local_gpu.py
& scripts/start_local_gpu.ps1
& scripts/configure_local.ps1   # Solo si no existe .env; conserva cualquier configuración previa.
uv run tutor models
uv run tutor ingest
uv run tutor chat
```

Después de reiniciar Windows basta iniciar el proveedor y después la consola o API del tutor. El modelo se identifica consultando `/v1/models`; no se inventa un alias. El manifiesto `data/local-gpu-runtime.json` registra rutas, revisión y hashes. El proveedor escucha solo en `127.0.0.1:8081`, sin interfaz web, con contexto de 16.384 tokens, un turno simultáneo, caché KV q8_0 y razonamiento explícito desactivado. No se permite desplazar el contexto descartando pistas antiguas. El servicio del tutor sigue siendo único; llama.cpp es el proveedor de inferencia sustituible.

Se comprobó en una RTX 5070 Ti de 16 GB y 64 GB de RAM. No se promete que esta configuración quepa en cualquier GPU. La cuantización de caché reduce la memoria utilizada; otras aplicaciones también consumen VRAM. Ejecuta las baterías reales una a la vez para no competir por el único puesto de inferencia. `TUTOR_LLM_RESPONSE_FORMAT=json_schema` limita la estructura y longitud de la salida, sin fijar su contenido o sus evaluaciones.

Para detenerlo: `& scripts/stop_local_gpu.ps1`. Ese script comprueba la ruta del ejecutable antes de detener el PID guardado, porque Windows puede reutilizar identificadores tras un reinicio. Los registros técnicos de carga están en `data/llama.stderr.log`. No se inicia automáticamente con Windows ni se instala como servicio.

Los ensayos anteriores con Qwen2.5-1.5B y Qwen2.5-7B detectaron problemas reales de formato y corrección. Sus registros se conservan como antecedentes; no son evidencia de aceptación final. Ver [resultados](../reports/VERIFICATION.md).

Fuentes oficiales: [modelo Qwen3 cuantizado](https://huggingface.co/Qwen/Qwen3-14B-GGUF), [release del runtime](https://github.com/ggml-org/llama.cpp/releases/tag/b10827) y [API del servidor](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Alternativa en CPU dentro del mismo proceso

Además de Ollama y HTTP compatible, `transformers_local` permite usar un LLM real con las bibliotecas Python ya instaladas. No requiere clave, puerto adicional ni entrenamiento. El proveedor implementa el mismo contrato que las APIs remotas.

Modelo de prueba descargado desde su repositorio oficial: [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct), revisión `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`. Su ficha declara soporte de español y JSON. Que esas capacidades estén declaradas no demuestra que todas las respuestas pedagógicas sean correctas.

```powershell
$env:TUTOR_LLM_PROVIDER = 'transformers_local'
$env:TUTOR_LLM_MODEL = 'Qwen/Qwen2.5-1.5B-Instruct'
$env:TUTOR_LLM_REVISION = '989aa7980e4cf806f80c7fef2b1adb7bc71aa306'
$env:TUTOR_LOCAL_DTYPE = 'bfloat16' # Solo en CPU con soporte; usar float32 en otras
$env:TUTOR_LOCAL_THREADS = '8'
$env:TUTOR_LLM_TIMEOUT = '180'
uv run python scripts/demo_session.py --state data/local-demo.json --output reports/local-demo.json --turns 1
```

La carga inicial descarga aproximadamente 3 GB de pesos; la caché permite reutilizarlos. `float32` consume más memoria durante inferencia. El backend actual usa CPU; no supone que disponer de una GPU implique una instalación CUDA de PyTorch funcional.

La generación local emplea `lm-format-enforcer` para restringir los tokens a la estructura JSON requerida y a los IDs de evidencia elegibles. **No fija las respuestas, las evaluaciones ni las observaciones del perfil.** El modelo sigue generando el contenido; la revisión estructural y de contenido sigue siendo obligatoria. Si falla, el intento se conserva y el tutor no emite una respuesta simulada.

La integración upstream de LM Format Enforcer 0.11.3 importa una clase desde una ruta retirada en Transformers 5. `tutor/structured.py` usa directamente la API de su núcleo para evitar esa incompatibilidad sin modificar paquetes instalados. Se prueba que el formato exige citas no vacías y no admite IDs fuera del conjunto permitido.

El límite de tiempo se comprueba durante la generación de tokens; no es un aislamiento de procesos ni interrumpe de forma instantánea la carga inicial o una operación de inferencia del sistema. No hay truncamiento silencioso del historial: superar `TUTOR_LOCAL_MAX_INPUT_TOKENS` devuelve una limitación explícita. `TUTOR_LOCAL_MAX_NEW_TOKENS` limita la longitud generada.

Consulta `reports/VERIFICATION.md` y los registros reales antes de afirmar una prueba integral superada. Los errores de los primeros ensayos permanecen en la sesión; no se borran para aparentar éxito.

Fuentes de implementación: [Transformers: generación](https://huggingface.co/docs/transformers/main/en/main_classes/text_generation) y [LM Format Enforcer](https://github.com/noamgat/lm-format-enforcer).
