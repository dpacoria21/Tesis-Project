"""SIMULACIONES EXCLUSIVAS PARA PRUEBAS; nunca seleccionables desde configuración."""
import hashlib
import math
from tutor.models import Draft, Review, Assessment
from tutor.retrieval import tokens


class TestEmbeddings:
    __test__ = False
    def encode(self, texts):
        rows = []
        for text in texts:
            vector = [0.0]*32
            for token in tokens(text):
                vector[int(hashlib.sha256(token.encode()).hexdigest()[:8],16)%32] += 1
            norm = math.sqrt(sum(x*x for x in vector)) or 1
            rows.append([x/norm for x in vector])
        return rows


class TestProvider:
    __test__ = False
    def __init__(self):
        self.calls = []
        self.observation = None
        self.reject = False

    def generate(self, system, payload, schema):
        self.calls.append((schema.__name__,payload))
        if schema is Assessment:
            if self.observation:
                if self.observation.kind=="estrategia":
                    return Assessment(status="strategy_observed",action="probe",observation=self.observation)
                is_difficulty=self.observation.kind=="dificultad"
                return Assessment(status="misconception" if is_difficulty else "supported",action="correct" if is_difficulty else "acknowledge",observation=self.observation)
            return Assessment(status="uncertain",action="probe")
        if schema is Review:
            return Review(correct=True,relevant=True,supported=True,safe_disclosure=not self.reject,
                non_repetitive=True,used_chunk_ids=payload["draft"]["used_chunk_ids"],issue="Revelación excesiva" if self.reject else "")
        turn_count = len(payload["history"])
        # Distintos textos controlados para probar estado, NO evaluación pedagógica real.
        messages = ["El resultado solicitado es una cantidad final. ¿Qué datos de entrada identificas?",
                    "Usa un caso pequeño para comprobar tu interpretación de los datos antes de avanzar.",
                    "Explica qué representa tu variable tras procesar el primer elemento del caso que elegiste.",
                    "Observa si una entrada con un único elemento permite realizar la comparación que propones.",
                    "Compara las condiciones de tu intento con el requisito de conservar la primera posición."]
        message=messages[turn_count%len(messages)]
        if payload.get("response_contract",{}).get("mode")=="prefix_boundary":
            message="Para el intervalo [2,2], observa el prefijo hasta el día 2 de tu ejemplo. ¿Qué día contiene que queda fuera del intervalo objetivo?"
        return Draft(message=message,used_chunk_ids=[payload["evidence"][0]["id"]],
                     code_observation="Observación estática de prueba; código no ejecutado." if payload["attempt"]["code"] else None)
