param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvePython = Join-Path $repoRoot 'scripts\common\resolve_python.ps1'
$python = & $resolvePython
$runner = Join-Path $repoRoot 'scripts\newbizintel.py'

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Unable to find runner at $runner"
}

& $python $runner @Args
exit $LASTEXITCODE
