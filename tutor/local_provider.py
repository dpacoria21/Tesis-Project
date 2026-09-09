"""Proveedor LLM REAL opcional en el mismo proceso. Sin credenciales ni servidor externo."""
import json
import time
from pydantic import ValidationError
from tutor.provider import ProviderError


class LocalTransformersProvider:
    def __init__(self, settings):
        self.settings=settings
        self.model=None
        self.tokenizer=None
        self.format_tokens=None

    def _load(self):
        if self.model is not None:
            return
        if not self.settings.llm_model or not self.settings.llm_revision:
            raise ProviderError("El proveedor local requiere modelo y revisión exacta.","not_configured")
        try:
            import torch
            from transformers import AutoModelForCausalLM,AutoTokenizer
            torch.set_num_threads(self.settings.local_threads)
            self.tokenizer=AutoTokenizer.from_pretrained(self.settings.llm_model,revision=self.settings.llm_revision,trust_remote_code=False)
            self.model=AutoModelForCausalLM.from_pretrained(self.settings.llm_model,revision=self.settings.llm_revision,
                trust_remote_code=False,use_safetensors=True,dtype=getattr(torch,self.settings.local_dtype))
            self.model.eval()
        except (OSError,RuntimeError,ValueError):
            raise ProviderError("No se pudo cargar el modelo local. Revisa identificador, revisión, caché y memoria disponible.","local_load") from None

    def models(self):
        self._load()
        return [self.settings.llm_model]

    def generate(self,system,payload,schema):
        self._load()
        import torch
        from transformers import StoppingCriteria,StoppingCriteriaList
        from tutor.structured import tokenizer_data,prefix_constraint
        if self.format_tokens is None:
            self.format_tokens=tokenizer_data(self.tokenizer)
        output_schema=schema.model_json_schema()
        if "message" in output_schema.get("properties",{}):
            level=payload.get("decision",{}).get("level",0) or 0
            output_schema["properties"]["message"]["maxLength"]=[450,600,650,800][min(level,3)]
            if "code_observation" in output_schema["properties"]:
                for choice in output_schema["properties"]["code_observation"].get("anyOf",[]):
                    if choice.get("type")=="string": choice["maxLength"]=200
        # Solo restringe la forma y los IDs elegibles; el modelo sigue decidiendo contenido y evaluación.
        if payload.get("allowed_source_ids") and "used_chunk_ids" in output_schema["properties"]:
            output_schema["properties"]["used_chunk_ids"]["items"]={"type":"string","enum":payload["allowed_source_ids"]}
        messages=[dict(role="system",content=system+"\nDevuelve solamente un objeto JSON válido, sin bloques Markdown, conforme al esquema: "+json.dumps(output_schema,ensure_ascii=False)),
                  dict(role="user",content=json.dumps(payload,ensure_ascii=False))]
        cfg=self.settings
        for attempt in range(cfg.llm_retries+1):
            inputs=self.tokenizer.apply_chat_template(messages,add_generation_prompt=True,return_tensors="pt",return_dict=True)
            length=inputs["input_ids"].shape[-1]
            if length>cfg.local_max_input_tokens:
                raise ProviderError("La conversación excede el contexto permitido del modelo local; no se truncó el historial.","context_limit")
            deadline=time.monotonic()+cfg.llm_timeout
            class Deadline(StoppingCriteria):
                def __call__(self,input_ids,scores,**kwargs):
                    return time.monotonic()>=deadline
            try:
                prefix_function=prefix_constraint(self.format_tokens,output_schema)
                with torch.inference_mode():
                    output=self.model.generate(**inputs,max_new_tokens=cfg.local_max_new_tokens,do_sample=False,
                        prefix_allowed_tokens_fn=prefix_function,
                        stopping_criteria=StoppingCriteriaList([Deadline()]),pad_token_id=self.tokenizer.eos_token_id)
                content=self.tokenizer.decode(output[0,length:],skip_special_tokens=True)
                if time.monotonic()>=deadline:
                    raise ProviderError("El modelo local agotó el tiempo de generación. Ajusta el límite o usa otro proveedor.","timeout")
                return schema.model_validate_json(content)
            except (ValidationError,ValueError):
                if attempt<cfg.llm_retries:
                    messages.append(dict(role="user",content="La salida no cumplió el esquema. Responde un objeto JSON puro con todas las propiedades requeridas, sin comentarios ni Markdown."))
            except RuntimeError:
                raise ProviderError("Falló la inferencia local; revisa memoria y configuración.","local_inference") from None
        raise ProviderError("El modelo local no produjo una respuesta estructurada válida tras los reintentos permitidos.","invalid_response")

    def close(self):
        self.model=None
        self.tokenizer=None
        self.format_tokens=None
