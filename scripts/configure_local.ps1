$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $workspaceRoot '.env'
if (Test-Path -LiteralPath $envPath) {
    throw 'Ya existe .env; se conserva. Edita sus variables TUTOR_LLM_* para cambiar de proveedor.'
}
$manifest = Get-Content -LiteralPath (Join-Path $workspaceRoot 'data/local-gpu-runtime.json') -Raw | ConvertFrom-Json
$models = Invoke-RestMethod -Uri 'http://127.0.0.1:8081/v1/models' -TimeoutSec 10
if ($models.data.id -notcontains $manifest.model_path) { throw 'El modelo del manifiesto no está disponible en la API local.' }
$lines = @(
    'TUTOR_DATA_DIR=data',
    'TUTOR_CORPUS_PATH=corpus/demo.json',
    'TUTOR_LLM_PROVIDER=openai_compatible',
    'TUTOR_LLM_BASE_URL=http://127.0.0.1:8081/v1',
    ('TUTOR_LLM_MODEL=' + $manifest.model_path),
    ('TUTOR_LLM_REVISION=' + $manifest.model_revision),
    'TUTOR_LLM_RESPONSE_FORMAT=json_schema',
    'TUTOR_LLM_TIMEOUT=120',
    'TUTOR_LLM_TEMPERATURE=0.2',
    'TUTOR_EXECUTION_ENABLED=false'
)
[IO.File]::WriteAllText($envPath, ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output 'Configuración local guardada, sin credenciales. Docker sigue siendo activable por separado.'
