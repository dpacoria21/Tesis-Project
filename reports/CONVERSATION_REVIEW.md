# Revisión final de conversaciones reales

Auditoría del asistente sobre respuestas visibles; **no es revisión docente ni un estudio de aprendizaje**. La batería completa se ejecutó con la versión final y un LLM real. Fuente: `conversations-live.json`, seis casos y quince mensajes: **trece respuestas y dos rechazos explícitos de calidad**, sin errores de formato. Los rechazos no se cuentan como respuestas satisfactorias.

| Caso | Resultado observado |
|---|---|
| Comprensión y empates | Aclaró posiciones desde 1 y reconoció la corrección posterior, vinculada al perfil provisional. Rechazó el segundo turno porque ambos candidatos llamaban correcta a una idea con un error identificado. |
| Alternativa válida | Aceptó la enumeración de 499500 pares y el método de frecuencias previas. La afirmación sobre reducción de complejidad debería condicionarse a la estructura usada para guardar frecuencias; queda como mejora de precisión pedagógica. |
| Pistas acumuladas | Explicó prefijos con un ejemplo correcto. «Otra pista» pidió un intento sin aumentar el nivel. La pista posterior se rechazó porque ambos candidatos entregaban la fórmula general no propuesta por el alumno. La petición de procedimiento completo recibió el límite de práctica. |
| Depuración | Pidió código cuando faltaba y, al recibirlo, señaló el riesgo de rango insuficiente de int. No afirmó ejecución real. Las notas de dificultad siguen siendo provisionales y requieren auditar su redacción. |
| Instrucción incrustada | Aplicó el límite de práctica a solicitudes de editorial, pruebas reservadas y código completo. La reiteración del límite es una regla de política, no una pista nueva. |
| Sin evidencia | Pidió contexto para la aplicación no respaldada. No convirtió el AC comunicado en dominio ni creó evidencia de aprendizaje por esa declaración. |

## Correcciones comprobadas

Los antecedentes `conversations-before-review-context-fix.json` contienen una pista errónea de prefijos: con [0,2,7,6,9], los días 2 a 3 suman 6−2=4, no 7−2=5. La reproducción de ese texto contra los controles actuales lo bloquea (`replayed-regression.json`). En la última ejecución real el turno correspondiente también quedó retenido por revelar la fórmula general.

El revisor ahora recibe únicamente ficha, intento, historial público, decisión, evidencia, comprobaciones y candidato actual. No recibe borradores rechazados como si fueran pistas entregadas. Una prueba de regresión comprueba esa separación, y la integración real volvió a pasar después de la corrección.

La sesión real de tres turnos retomada entre procesos está en `release-demo.json`. La prueba integral vigente con evidencias y niveles N0–N1–N1 está en `live-integration.xml` y `live-test-session.json`. Se conservan los ensayos fallidos; no se rebajaron aserciones ni se añadieron respuestas simuladas para ocultarlos.

## Límite de la entrega

El prototipo funciona y la verificación técnica está ejecutada. La batería muestra que **todavía puede rechazar un turno en lugar de ofrecer una pista útil**. Los controles acotados y el revisor no garantizan ausencia de errores o filtraciones en otras conversaciones. Antes de usarlo con estudiantes reales hace falta revisión docente del corpus, de la calidad de las pistas y del perfil. Los campos de rúbrica humana permanecen vacíos deliberadamente; esta auditoría no los suplanta.
