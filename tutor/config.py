from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TUTOR_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    corpus_path: Path = Path("corpus/demo.json")
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_revision: str = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    llm_provider: Literal["disabled", "openai_compatible", "ollama", "transformers_local"] = "disabled"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = ""
    llm_revision: str = ""
    local_dtype: Literal["float32","bfloat16"] = "float32"
    local_threads: int = Field(8,ge=1,le=32)
    local_max_input_tokens: int = Field(12000,ge=1024,le=32000)
    local_max_new_tokens: int = Field(800,ge=128,le=2048)
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout: float = Field(60, ge=1, le=300)
    llm_retries: int = Field(2, ge=0, le=3)
    llm_temperature: float = Field(0.2,ge=0,le=2)
    llm_max_tokens: int = Field(1000,ge=128,le=4096)
    llm_response_format: Literal["json_object","json_schema"] = "json_object"
    max_hint_level: int = Field(3, ge=0, le=3)
    retrieval_k: int = Field(6, ge=1, le=20)
    rrf_constant: int = Field(60, ge=1)
    execution_enabled: bool = False
    docker_image: str = ""

    @model_validator(mode="after")
    def safe_url(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.llm_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise ValueError("La URL del proveedor debe ser HTTP(S), sin credenciales ni parámetros.")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Usa HTTPS para un proveedor remoto.")
        return self
