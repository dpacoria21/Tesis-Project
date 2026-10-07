# Problemas de Codeforces para las sesiones

`corpus/codeforces.json` incorpora dos problemas reales, completos para el contexto del tutor:

| ID local | Problema original | Fuente |
| --- | --- | --- |
| `cf-4A` | 4A — Watermelon | [Enunciado de Codeforces](https://codeforces.com/problemset/problem/4/A) |
| `cf-71A` | 71A — Way Too Long Words | [Enunciado de Codeforces](https://codeforces.com/problemset/problem/71/A) |

Los enunciados se contrastaron el 7 de octubre de 2026 mediante las páginas oficiales. Codeforces puede responder con restricciones de acceso automatizado en algunas solicitudes; la consulta del original sigue siendo un enlace externo. No se utiliza un scraper ni un proxy de la página.

El archivo contiene paráfrasis breves en español, restricciones, formatos y ejemplos del problema, junto con orientación N0–N3, conceptos y referencias C++17 redactados para este prototipo. Los conceptos permiten importar el archivo sin depender del corpus de demostración. Las explicaciones y referencias completas son internas. El campo `review_status` deja explícita la revisión docente pendiente; una comprobación automática no la reemplaza. No se han copiado editoriales ni se atribuye una licencia abierta al texto original.

La dificultad 1 en `codeforces_intro_local_1_5` es una clasificación provisional propia de este pequeño conjunto, no el rating de Codeforces ni una equivalencia con la escala de demostración. El recomendador actual no compara esas escalas.

## Incorporación al catálogo

Con el servicio detenido, desde la raíz del repositorio:

```powershell
uv run tutor ingest --file corpus/codeforces.json
```

La ingesta conserva los materiales existentes, actualiza por ID y reconstruye el índice con la configuración de embeddings vigente. Si falla la fase de embeddings, el catálogo importado permanece y el índice queda pendiente: repite la ingesta cuando se resuelva la causa. El archivo por sí solo no modifica la base de datos ni la configuración de una instalación en marcha.

## Comprobación

```powershell
uv run pytest tests/test_codeforces_corpus.py
```

Se comprueban esquema, procedencia, importación incremental e idempotencia, separación de los campos internos y resultados de ejemplos y fronteras. Si existe `g++`, se compilan únicamente las dos referencias propias: Watermelon se contrasta con enumeración de repartos para todos los pesos permitidos y Way Too Long Words con todas las longitudes permitidas en un lote de 100 palabras. No se compilan intentos de estudiantes ni código importado por terceros. Sin `g++`, se omite esa comprobación de compilación; no se instala un compilador. `tutor validate-corpus` sigue limitado a los oráculos del corpus original de demostración.
