$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $workspaceRoot 'data/local-gpu-runtime.json') -Raw | ConvertFrom-Json
$pidFile = Join-Path $workspaceRoot 'data/llama.pid'
if (Test-Path -LiteralPath $pidFile) {
    $recordedPid = [int](Get-Content -LiteralPath $pidFile)
    $running = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
    # Un PID puede haber sido reutilizado después de reiniciar Windows.
    if ($running -and $running.Path -eq $manifest.executable) {
        Stop-Process -InputObject $running
        $running.WaitForExit(10000) | Out-Null
        Write-Output 'Proveedor local detenido.'
    } else {
        Write-Output 'El proceso registrado ya no corresponde al proveedor local; no se detuvo ningún proceso.'
    }
}
