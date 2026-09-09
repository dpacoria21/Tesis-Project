# Importador JSON / JSONL

El importador valida con Pydantic, conserva procedencia y hace upsert por identificador estable. No extrae sitios web ni afirma disponer de contenido de plataformas externas. El corpus incluido es material propio; no es de Codeforces ni AtCoder.

## Formatos

JSON: objeto con `schema_version: 1`, `problems: []` y `concepts: []`. `corpus/demo.json` es un ejemplo completo válido. `corpus/schema.json` es el JSON Schema exportado desde los mismos modelos que usa la aplicación.

JSONL: cada línea representa un objeto `{"kind":"problem","data":{...}}` o `{"kind":"concept","data":{...}}`. Los conceptos enlazados deben estar en la misma importación o ya existir en el catálogo. La validación es anterior a la transacción, por lo que una referencia rota no deja una importación parcial.

## Problemas

Campos públicos: `id`, `title`, `statement`, `constraints`, `input_format`, `output_format`, `examples` (objetos input/output), `topics`, `prerequisites`, `difficulty`, `difficulty_scale`, `language`, `programming_language`, `provenance`.

Campos internos obligatorios: `explanation`, `reference_strategy`, `reference_cpp`, `common_errors`, `tests`, `guidance` (cada objeto con level, text y step), `concept_ids`. Las pistas deben cubrir N0, N1, N2 y N3. `step` identifica el foco de orientación; los IDs de fragmento se derivan del problema y nivel. Prepara un foco por nivel en esta versión.

`difficulty` es un entero 1–5 que solo tiene sentido dentro de `difficulty_scale`. Para material importado conserva una escala propia del conjunto, sin etiquetarla `demo_local_1_5` salvo que haya una calibración local documentada. El recomendador inicial usa únicamente la escala de demostración; no compara ratings de plataformas.

## Conceptos

`id`, `title`, `text`, `topics`, `language`, `min_level` y `provenance`. `min_level=2` es el valor inicial para explicaciones conceptuales. Mantén textos breves y unidades completas: no se realiza fragmentación arbitraria del documento. Para un artículo largo, prepara varios conceptos con títulos e IDs claros, preservando condiciones y enlaces.

## Procedencia

`provenance` contiene `kind` (`original_demo` o `external`), `platform`, `external_id`, `url`, `review_status` y `license_note`. El material externo requiere ID real y URL HTTPS. No se descargan ni verifican automáticamente los enlaces: la persona que incorpora el material debe comprobar procedencia, permisos, fidelidad y calidad docente.

Para incorporar Codeforces o AtCoder, conserva el identificador original y la URL exacta del problema que tengas autorizado utilizar. Para conceptos de CP-Algorithms o USACO Guide, conserva la URL exacta del artículo y su identificador o slug real. Asigna un ID local estable con espacio de nombres para evitar colisiones. No hay fixtures que aparenten material extraído de estas plataformas.

El importador exige completar restricciones, ejemplos, pruebas, orientación y referencia antes de añadir un problema. No toma la mera generación automática como revisión docente. `license_note` conserva la situación de derechos declarada; no reemplaza su verificación.

## Ingesta y cambios

```powershell
uv run tutor ingest --file C:\ruta\material.json
uv run tutor ingest --file C:\ruta\material.jsonl
```

Repetir el mismo archivo no duplica registros. Actualizar un ID sustituye ese material; no cambia los IDs de sesiones. Para cambios incompatibles de enunciado crea un ID nuevo, de modo que una sesión no cambie de problema a mitad del recorrido. La ingesta conserva los otros materiales del catálogo; no hace borrado masivo por ausencia en el archivo.

La actualización del catálogo y la del índice son dos fases: si falla la descarga de embeddings, los datos importados permanecen y el manifiesto detecta el desfase. Vuelve a ejecutar la ingesta después de resolver el fallo. Haz mantenimiento de corpus con el servicio detenido.
