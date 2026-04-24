param(
    [ValidateSet('pptx_runtime', 'all')]
    [string[]]$Runtime = @('all')
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSCommandPath
$scriptPath = Join-Path $repoRoot 'scripts\bootstrap_vendor_runtime.py'

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Bootstrap script not found: $scriptPath"
}

$python = & (Join-Path $repoRoot 'scripts\common\resolve_python.ps1')

$runtimeArgs = @()
if (-not ($Runtime.Count -eq 1 -and $Runtime[0] -eq 'all')) {
    foreach ($item in $Runtime) {
        $runtimeArgs += @('--runtime', $item)
    }
}

& $python $scriptPath @runtimeArgs --repo-root $repoRoot
