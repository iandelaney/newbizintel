param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$TemplatePath,

    [string]$OutputPath,

    [switch]$SkipValidation
)

$ErrorActionPreference = 'Stop'

function Resolve-RequiredPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    return (Resolve-Path -LiteralPath $LiteralPath).Path
}

if (-not $TemplatePath) {
    $TemplatePath = Join-Path $PSScriptRoot '..\..\templates\report-template.html'
}

$resolvedDataPath = Resolve-RequiredPath -LiteralPath $DataPath
$resolvedTemplatePath = Resolve-RequiredPath -LiteralPath $TemplatePath

if (-not $SkipValidation) {
    $null = & (Join-Path $PSScriptRoot '..\structure\validate_report_data.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json
}

if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $resolvedDataPath) 'newbizintel-report.html'
}

$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $resolvedOutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    $null = New-Item -ItemType Directory -Path $outputDirectory -Force
}

$pythonCandidates = @(
    'C:\Users\iande\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
    (Join-Path $PSScriptRoot '..\..\vendor\python\python.exe')
)

$pythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonPath) {
    throw 'Unable to locate a Python runtime for render_report.py.'
}

$rendererPath = Resolve-RequiredPath -LiteralPath (Join-Path $PSScriptRoot 'render_report.py')
$arguments = @(
    $rendererPath
    '--data'
    $resolvedDataPath
    '--template'
    $resolvedTemplatePath
    '--output'
    $resolvedOutputPath
)

if ($SkipValidation) {
    $arguments += '--skip-validation'
}

$output = & $pythonPath @arguments 2>&1
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    $message = ($output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($message)) {
        $message = "render_report.py exited with code $exitCode."
    }
    throw $message
}

$jsonText = ($output | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($jsonText)) {
    throw 'render_report.py returned no output.'
}

try {
    $result = $jsonText | ConvertFrom-Json
}
catch {
    throw "render_report.py returned invalid JSON: $jsonText"
}

$result | ConvertTo-Json -Depth 8
