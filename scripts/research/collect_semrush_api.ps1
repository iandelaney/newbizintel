param(
    [string]$DataPath,
    [string]$Domain,
    [ValidateSet('uk', 'us')]
    [string]$Database = 'uk',
    [string]$OutputPath,
    [string]$ApiKeyEnv = 'SEMRUSH_API_KEY',
    [int]$KeywordLimit = 20,
    [int]$CompetitorLimit = 10,
    [int]$PageLimit = 10
)

$ErrorActionPreference = 'Stop'

if (-not $DataPath -and -not $Domain) {
    throw 'Provide either -DataPath or -Domain.'
}

$python = & (Join-Path $PSScriptRoot '..\common\resolve_python.ps1')
$args = @(
    (Join-Path $PSScriptRoot 'collect_semrush_api.py'),
    '--database', $Database,
    '--api-key-env', $ApiKeyEnv,
    '--keyword-limit', ([string]$KeywordLimit),
    '--competitor-limit', ([string]$CompetitorLimit),
    '--page-limit', ([string]$PageLimit)
)

if ($DataPath) {
    $args += @('--data', (Resolve-Path -LiteralPath $DataPath).Path)
}
if ($Domain) {
    $args += @('--domain', $Domain)
}
if ($OutputPath) {
    $args += @('--output', $OutputPath)
}

& $python @args
