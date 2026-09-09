$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspaceRoot
$manifest = Get-Content -LiteralPath 'data/local-gpu-runtime.json' -Raw | ConvertFrom-Json
$serverPath = [System.IO.Path]::GetFullPath($manifest.executable)
$runtimeRoot = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot '.runtime'))
if (-not $serverPath.StartsWith($runtimeRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'El ejecutable está fuera del runtime local preparado.'
}
$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8081)
if (Test-Path -LiteralPath 'data/llama.pid') {
    $recordedPid = [int](Get-Content -LiteralPath 'data/llama.pid')
    $running = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
    if ($running -and $running.Path -eq $serverPath) {
        Write-Output 'El proveedor local preparado ya está en ejecución.'
        return
    }
}
try { $portProbe.Start() } finally { $portProbe.Stop() }
# No expone el chat web del runtime; se usa exclusivamente su API en localhost.
$serverArgs = @('-m', ('"' + $manifest.model_path + '"'), '--host', '127.0.0.1', '--port', '8081', '-c', '16384', '-np', '1', '-ngl', '99', '-t', '8', '-ctk', 'q8_0', '-ctv', 'q8_0', '-fa', 'on', '--reasoning', 'off', '--no-webui', '--no-context-shift')
$runtimeProcess = Start-Process -FilePath $serverPath -ArgumentList $serverArgs -WorkingDirectory (Split-Path -Parent $serverPath) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workspaceRoot 'data/llama.stdout.log') -RedirectStandardError (Join-Path $workspaceRoot 'data/llama.stderr.log')
$runtimeProcess.Id | Set-Content -LiteralPath 'data/llama.pid'
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ($runtimeProcess.HasExited) { throw 'El proveedor terminó durante la carga. Consulta data/llama.stderr.log.' }
    try {
        $models = Invoke-RestMethod -Uri 'http://127.0.0.1:8081/v1/models' -TimeoutSec 2
        if ($models.data.id -contains $manifest.model_path) {
            Write-Output ('Proveedor local listo. API: http://127.0.0.1:8081/v1')
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'El proveedor aún no responde; consulta data/llama.stderr.log.'
