# Arquitectura y decisiones

`TutorService` es el punto único del recorrido usado por FastAPI y la consola. Los adaptadores de transporte, almacenamiento, recuperación y ejecución no son agentes autónomos.

1. Carga la sesión del estudiante y el perfil acumulado desde SQLite.
2. Obtiene la ficha del problema por ID y decide la necesidad pedagógica mediante reglas transparentes.
3. Comprueba C++17 solamente si se solicitó y el aislamiento está disponible.
4. Recupera pistas del problema y conceptos enlazados con BM25 y embeddings. Filtra el contenido por nivel antes de entregarlo al generador.
5. Evalúa el intento actual del estudiante en ideas/depuración y genera una respuesta JSON mediante el proveedor configurable. Son operaciones separadas: la revisión de la respuesta del tutor no decide el perfil.
6. Aplica controles estructurales y una segunda llamada de revisión de contenido, incluyendo todas las respuestas anteriores. Puede pedir una corrección, como máximo una vez.
7. Valida citas y evidencia textual del estudiante; registra intento, respuesta, trazas y observación en una transacción.
8. En el siguiente turno repite la evaluación con el historial persistido. La observación nueva solo se atribuye a la respuesta del estudiante, nunca a lo que acaba de explicar el tutor.

## Persistencia

SQLite separa `students`, `sessions`, `interactions`, `observations` y `materials`. El estado de sesión contiene problema, mensajes, código, resultados declarados, comprobaciones y ayuda entregada. La traza interna guarda decisión breve, recuperación (IDs, contenido y procedencia), configuración del modelo y embeddings, nivel, duración, revisión y progreso observado. No se pide ni almacena razonamiento privado del modelo.

Una transacción registra la interacción y su evidencia. Un candado del sistema operativo serializa turnos entre consola y API y se libera al terminar el proceso. Las sesiones se consultan por combinación de estudiante e ID; cambiar de problema crea otra sesión, con el mismo perfil.

## Política N0–N3

La necesidad (`comprension`, `concepto`, `idea`, `depuracion`, `practica`) es diferente de la estrategia de recuperación (exacta + híbrida). La necesidad puede indicarse explícitamente o inferirse por reglas de palabras y presencia de código. Es una política inicial evaluable, no una clasificación lingüística exhaustiva.

La ayuda inicia en N0 para comprensión, N1 para ideas/depuración y N2 para conceptos. La falta de código o de una idea suficiente produce una pregunta concreta sin consumir una llamada LLM. El historial evita subir automáticamente: para escalar exige bloqueo explícito más intento sustantivo. Una dificultad confirmada relevante y una declaración de incomprensión permiten una explicación N2. `TUTOR_MAX_HINT_LEVEL` limita la política.

Las solicitudes explícitas de código completo, editorial o procedimiento entero reciben un límite de práctica mediante una regla identificada en la traza. Pedir que un AC confirme dominio produce una solicitud de evidencia. Son decisiones pedagógicas del servicio, no respuestas simuladas para ocultar fallos de un proveedor. La generación sigue fallando de forma explícita cuando el LLM no responde correctamente.

Cada turno recibe únicamente la pista de su nivel que todavía no se haya utilizado. Si se agotó, el generador debe invitar a aplicar una anterior, sin volver a revelarla. Los conceptos necesarios pueden reutilizarse para sostener una explicación, pero la respuesta completa se revisa por repetición. No hay obligación de terminar cada respuesta en pregunta socrática. Una respuesta correcta con justificación puede recibir solo una devolución breve, sin otra pista automática. Una petición vaga de «otra pista» sin intento nuevo pide describir qué se probó, conservando el nivel.

Antes de la primera generación, `response_contract.py` fija un objetivo mediante instrucciones constantes del servicio: contrastar un intento equivocado, reconocer una propiedad justificada, definir el concepto o orientar un único paso. Para prefijos en N3, exige declarar el intervalo objetivo y una frontera concreta sin resolver las dos fronteras ni entregar la resta general. El generador recibe como foco una pista ya autorizada, sin respuestas prefabricadas ni referencias privadas. Una mención aislada a los símbolos de una fórmula no cuenta como haberla propuesto.

Al contrastar una actualización de máximo con igualdad, el generador también recibe un único ejemplo público calculado: posición requerida del primer máximo y posición conservada si se actualiza al empatar. Se prefieren los valores del estudiante y después los de la pista permitida. Esto sustenta un contraejemplo pequeño; no es ejecución del código ni entrega del algoritmo general. Una comprobación acotada detecta ciertas afirmaciones positivas que atribuyen a esa regla una posición numérica equivocada; las preguntas y negaciones quedan fuera de esa comprobación.

Si un candidato falla, se genera otro desde el mismo intento, nivel e historial entregado. El texto rechazado no se reinyecta para evitar su repetición. Se mantienen los controles estructurales, numéricos y la revisión de contenido; una revisión con cinco aprobaciones y un defecto escrito es inválida y debe corregirse mediante los reintentos limitados del proveedor. La evaluación del estudiante y la del tutor siguen siendo falibles.

## Perfil: evidencia, no elogios

Una observación requiere concepto perteneciente a los temas, cita textual exacta del mensaje o código actual, tipo (`demostracion`, `dificultad`, `estrategia`), nota breve, fecha, interacción y nivel. La evaluación del intento debe comprobar que la conducta está sustentada. Se descartan citas inexistentes, evaluaciones inciertas con observaciones y supuestas demostraciones demasiado breves o formuladas como preguntas.

Toda observación comienza **provisional**. Dos observaciones del mismo concepto y tipo, en **dos problemas distintos**, confirman el patrón observado. Repetir mensajes dentro de un mismo problema no confirma el patrón. `confirmado` significa evidencia repetida bajo esta regla del prototipo, no certificación de dominio. El modelo puede equivocarse al evaluar la evidencia: se requiere auditoría humana.

La evaluación puede registrar una estrategia declarada sin certificar su corrección; esa categoría se mantiene separada de las demostraciones. Pedir ayuda, recibir una explicación o comunicar un AC no basta para crear una demostración. El recomendador utiliza conocimientos básicos declarados (etiquetados como tales), demostraciones confirmadas, dificultades, dificultad local, prerrequisitos e historial. Excluye ejercicios ya iniciados y escalas no comparables. Puede recomendar preparar un prerrequisito; si no hay opción elegible lo dice.

## Límites relevantes

- El RAG aporta evidencia; no demuestra corrección. La revisión de contenido por el mismo modelo en otra llamada puede compartir sus errores.
- La evaluación del estudiante y la revisión del tutor pueden consultar estrategia interna, errores frecuentes y conceptos de referencia; el generador recibe solo materiales públicos permitidos y la acción pedagógica, nunca esa referencia privada. Los borradores rechazados y sus defectos quedan únicamente en la traza interna para auditoría.
- Se calculan sumas, primer máximo y vecinos de ejemplos textuales pequeños de arreglos para ayudar al revisor. Hay un control acotado de enumeraciones de vecinos. Esto no ejecuta código ni demuestra corrección de lenguaje natural en general; no cubre ejemplos arbitrarios ni todos los problemas.
- El control estructural detecta también frases largas repetidas dentro de respuestas distintas y ciertas descripciones explícitas de bucles en N0/N1. Para el ejercicio de prefijos, retiene la fórmula general de intervalo si el estudiante todavía no la propuso. Son controles acotados al prototipo; paráfrasis equivalentes pueden escapar a ellos.
- Ante preguntas de la forma «cómo aplico/uso X», una regla de cobertura pide contexto si no encuentra términos de X en el material público del problema y sus conceptos. La ausencia léxica no demuestra irrelevancia semántica: puede pedir aclaraciones ante sinónimos o términos de otro idioma. No inventa fuentes para completar esa conexión.
- Los controles de longitud, código, citas, similitud y revisión acumulada reducen revelaciones, pero no garantizan impedirlas. El riesgo es especialmente alto en problemas cuya solución es una sola operación. La batería humana debe revisar el conjunto de pistas.
- Los embeddings incluidos usan el límite de secuencia del modelo preentrenado. Un fragmento largo puede truncarse al vectorizar, aunque el texto completo permanece almacenado y la ficha exacta siempre llega íntegra al tutor. Los importadores deben preparar conceptos breves. No se usa el vector como sustituto de restricciones.
- La recuperación relaciona conceptos explícitamente enlazados; no descubre automáticamente todos los prerrequisitos de materiales nuevos.
- El perfil y la clasificación son reglas iniciales, no modelos psicométricos. No hay entrenamiento ni medición validada de aprendizaje.
- La sesión admite contexto completo hasta un límite de 60.000 caracteres; después pide comenzar otra sesión y conserva los datos anteriores. Nunca omite silenciosamente pistas antiguas para hacer caber la respuesta.
- El servicio es local y sin autenticación. No incluye juez oficial, frontend, uso concurrente distribuido ni despliegue.
- APIs públicas con formatos distintos necesitan un adaptador. No existe una interfaz HTTP universal que funcione con cualquier proveedor sin adaptación.

## Archivos principales

`models.py` valida esquemas; `storage.py` guarda estado/evidencia; `corpus.py` importa y separa visibilidad; `retrieval.py` implementa Chroma/BM25/RRF; `pedagogy.py` decide y revisa; `provider.py` integra HTTP real; `execution.py` exige aislamiento; `recommend.py` recomienda; `service.py` compone el recorrido; `api.py` y `cli.py` son dos accesos a los mismos servicios.
