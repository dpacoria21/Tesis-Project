import json
import httpx
import pytest
from tutor.config import Settings
from tutor.execution import DockerRunner
from tutor.models import Draft
from tutor.provider import HTTPProvider,ProviderError


@pytest.mark.parametrize("provider",["ollama","openai_compatible"])
def test_real_http_adapters_with_mock_transport(provider):
    seen=[]
    def handle(request):
        body=json.loads(request.content);seen.append(body)
        text=json.dumps(dict(message="Una aclaración",used_chunk_ids=["c-estado"],code_observation=None))
        return httpx.Response(200,json={"message":{"content":text}} if provider=="ollama" else {"choices":[{"message":{"content":text}}]})
    config=Settings(_env_file=None,llm_provider=provider,llm_model="test-transport-only",llm_retries=0)
    result=HTTPProvider(config,httpx.MockTransport(handle)).generate("system",{"test":True},Draft)
    assert result.message=="Una aclaración" and seen[0]["model"]=="test-transport-only"


def test_invalid_structured_output_retries_bounded(monkeypatch):
    monkeypatch.setattr("tutor.provider.time.sleep",lambda _:None)
    requests=[]
    def handle(request):
        requests.append(request)
        return httpx.Response(200,json={"choices":[{"message":{"content":"not json"}}]})
    settings=Settings(_env_file=None,llm_provider="openai_compatible",llm_model="test-only",llm_retries=2)
    with pytest.raises(ProviderError) as err:
        HTTPProvider(settings,httpx.MockTransport(handle)).generate("x",{},Draft)
    assert err.value.code=="invalid_response" and len(requests)==3


def test_credentials_errors_not_leaked_or_retried():
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(401,text="SENSITIVE_ERROR_BODY")
    cfg=Settings(_env_file=None,llm_provider="ollama",llm_model="test-only")
    with pytest.raises(ProviderError) as err:
        HTTPProvider(cfg,httpx.MockTransport(handle)).generate("x",{},Draft)
    assert "SENSITIVE" not in str(err.value) and len(calls)==1


def test_disabled_runner_never_starts_process(monkeypatch):
    def forbidden(*a,**k): pytest.fail("Intento de ejecutar código desactivado")
    monkeypatch.setattr("subprocess.run",forbidden)
    runner=DockerRunner(Settings(_env_file=None))
    assert runner.run("untrusted",[]).status=="no ejecutado"


def test_docker_limits_command_and_digest_gate():
    runner=DockerRunner(Settings(_env_file=None,execution_enabled=True))
    assert not runner.availability()[0]
    command=runner.command("test")
    for flag in ["--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges:true","--memory=512m","--pids-limit=64","--user=65534:65534"]:
        assert flag in command
    assert "--privileged" not in command and "-v" not in command and "--mount" not in command


def test_timeouts_retry_and_stop(monkeypatch):
    monkeypatch.setattr("tutor.provider.time.sleep",lambda _:None)
    calls=[]
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("private details")
    cfg=Settings(_env_file=None,llm_provider="ollama",llm_model="test-only",llm_retries=1)
    with pytest.raises(ProviderError) as err:
        HTTPProvider(cfg,httpx.MockTransport(handle)).generate("x",{},Draft)
    assert len(calls)==2 and err.value.code=="timeout" and "private" not in str(err.value)
