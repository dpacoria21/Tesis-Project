"""Adaptadores HTTP reales. No incluyen una respuesta simulada ni una clave obligatoria."""
import json
import time
from typing import Protocol, TypeVar
import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    def __init__(self, message, code="provider_error"):
        super().__init__(message)
        self.code = code


class LLMProvider(Protocol):
    def generate(self, system: str, payload: dict, schema: type[T]) -> T: ...


def create_provider(settings):
    if settings.llm_provider=="transformers_local":
        from tutor.local_provider import LocalTransformersProvider
        return LocalTransformersProvider(settings)
    return HTTPProvider(settings)


class HTTPProvider:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def _headers(self):
        key = self.settings.llm_api_key.get_secret_value()
        return {"Authorization":f"Bearer {key}"} if key else {}

    def models(self):
        path = "/api/tags" if self.settings.llm_provider == "ollama" else "/models"
        try:
            with httpx.Client(timeout=self.settings.llm_timeout,transport=self.transport,follow_redirects=False) as client:
                response = client.get(self.settings.llm_base_url.rstrip("/")+path,headers=self._headers())
                response.raise_for_status()
                body = response.json()
            return [m["name"] for m in body["models"]] if path == "/api/tags" else [m["id"] for m in body["data"]]
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            raise ProviderError("No se pudo consultar el catálogo de modelos. Revisa URL, servicio y credenciales.") from None

    def generate(self, system, payload, schema):
        cfg = self.settings
        if cfg.llm_provider == "disabled" or not cfg.llm_model:
            raise ProviderError("Proveedor pendiente de configurar: elige proveedor, URL y un modelo existente.","not_configured")
        wire_schema=schema.model_json_schema()
        if schema.__name__=="Draft":
            level=payload.get("decision",{}).get("level",0)
            wire_schema["properties"]["message"]["maxLength"]=[320,420,600,700][level or 0]
            wire_schema["properties"]["used_chunk_ids"]["items"]={"type":"string","enum":payload["allowed_source_ids"]} if payload.get("allowed_source_ids") else {"type":"string"}
        messages = [dict(role="system",content=system+"\nResponde únicamente JSON válido según este esquema: "+json.dumps(wire_schema,ensure_ascii=False)),
                    dict(role="user",content=json.dumps(payload,ensure_ascii=False))]
        if cfg.llm_provider == "ollama":
            path = "/api/chat"
            body = dict(model=cfg.llm_model,messages=messages,stream=False,format=wire_schema,options={"temperature":cfg.llm_temperature,"num_predict":cfg.llm_max_tokens})
        else:
            path = "/chat/completions"
            body = dict(model=cfg.llm_model,messages=messages,response_format={"type":"json_object"},max_tokens=cfg.llm_max_tokens,temperature=cfg.llm_temperature)
            if cfg.llm_response_format=="json_schema":
                body["response_format"]={"type":"json_schema","json_schema":{"name":schema.__name__,"schema":wire_schema}}
        error_code = "provider_error"
        validation_errors=[]
        for attempt in range(cfg.llm_retries+1):
            try:
                with httpx.Client(timeout=cfg.llm_timeout,transport=self.transport,follow_redirects=False) as client:
                    # Lectura acotada: no guardar cuerpos de errores ni razonamiento privado.
                    with client.stream("POST",cfg.llm_base_url.rstrip("/")+path,headers=self._headers(),json=body) as response:
                        response.raise_for_status()
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 262144:
                                raise ValueError("Respuesta demasiado grande")
                result = json.loads(raw)
                content = result["message"]["content"] if cfg.llm_provider == "ollama" else result["choices"][0]["message"]["content"]
                return schema.model_validate_json(content)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                error_code = "http_"+str(status)
                if status < 500 and status not in {408,429}:
                    break
            except httpx.TimeoutException:
                error_code = "timeout"
            except httpx.HTTPError:
                error_code = "connection"
            except ValidationError as exc:
                error_code = "invalid_response"
                # Solo campos y tipos del esquema, nunca cuerpos de error, secretos ni razonamiento.
                errors=[{"field":".".join(map(str,e["loc"])),"type":e["type"],"message":e["msg"]} for e in exc.errors(include_input=False)]
                validation_errors=errors
                messages.append(dict(role="user",content="La salida no cumple el esquema: "+json.dumps(errors)+". Devuelve el objeto corregido, respetando campos, tipos y límites."))
            except (ValueError,KeyError,TypeError,IndexError):
                error_code = "invalid_response"
            if attempt < cfg.llm_retries:
                time.sleep(min(0.5*2**attempt,2))
        error=ProviderError("El proveedor falló o devolvió una respuesta inválida. El intento fue conservado; revisa la configuración y vuelve a intentar.",error_code)
        error.validation_errors=validation_errors
        error.schema_name=schema.__name__
        raise error
