param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [object]$State
)

$ErrorActionPreference = 'Stop'

$taskListScript = Join-Path $PSScriptRoot 'task_list.ps1'
if (Test-Path -LiteralPath $taskListScript) {
    . $taskListScript
    Ensure-NewBizTaskList -State $State
    Sync-NewBizTaskStatusFromGates -State $State
}

$hybridScript = Join-Path $PSScriptRoot 'hybrid_execution.ps1'
if (Test-Path -LiteralPath $hybridScript) {
    . $hybridScript
    Ensure-NewBizHybridExecution -State $State
}

$directory = Split-Path -Parent $Path
if ($directory) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$json = $State | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
