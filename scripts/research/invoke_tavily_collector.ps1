param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('search','research')]
    [string]$Kind,

    [string]$Query,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$Country,

    [ValidateSet('general','news','finance')]
    [string]$Topic = 'general',

    [ValidateSet('ultra-fast','fast','basic','advanced')]
    [string]$Depth = 'basic',

    [int]$MaxResults = 10,

    [ValidateSet('mini','pro','auto')]
    [string]$Model = 'mini',

    [int]$TimeoutSeconds = 600,

    [int]$PollIntervalSeconds = 10,

    [string]$RequestId,

    [switch]$AllowExpensiveResearch,

    [switch]$ReuseExisting
)

$ErrorActionPreference = 'Stop'

if (-not $Query -and -not $RequestId) {
    throw 'Provide either -Query or -RequestId.'
}

if ($Kind -eq 'research' -and -not $AllowExpensiveResearch -and -not $RequestId) {
    throw 'Tavily Research is an expensive escalation. Pass -AllowExpensiveResearch, reuse an existing completed workpack, or poll an existing -RequestId.'
}

if ($MaxResults -lt 0 -or $MaxResults -gt 20) {
    throw '-MaxResults must be between 0 and 20.'
}

$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory) {
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}
$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$validate = Join-Path $PSScriptRoot 'validate_tavily_workpack.ps1'

function Invoke-TavilyCommand {
    param([string[]]$Arguments)

    $command = Get-Command tvly -ErrorAction SilentlyContinue
    if (-not $command) {
        throw 'Tavily CLI `tvly` was not found on PATH.'
    }

    & $command.Source @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Tavily CLI failed with exit code $LASTEXITCODE. Arguments: $($Arguments -join ' ')"
    }
}

function Invoke-TavilyPoll {
    param([Parameter(Mandatory = $true)][string]$Id)

    Invoke-TavilyCommand -Arguments @(
        'research', 'poll', $Id,
        '--poll-interval', [string]$PollIntervalSeconds,
        '--timeout', [string]$TimeoutSeconds,
        '--json',
        '-o', $resolvedOutputPath
    )
}

if ($ReuseExisting -and (Test-Path -LiteralPath $resolvedOutputPath)) {
    $existingValidation = & $validate -Path $resolvedOutputPath -Kind $Kind | ConvertFrom-Json
    if ($existingValidation.ok -eq $true) {
        [pscustomobject]@{
            ok = $true
            reused_existing = $true
            output = $resolvedOutputPath
            validation = $existingValidation
        } | ConvertTo-Json -Depth 8 -Compress
        exit 0
    }
    if ($Kind -eq 'research' -and $existingValidation.recoverable -eq $true -and $existingValidation.request_id) {
        $RequestId = [string]$existingValidation.request_id
    }
}

if ($Kind -eq 'research' -and $RequestId) {
    Invoke-TavilyPoll -Id $RequestId
}
elseif ($Kind -eq 'research') {
    Invoke-TavilyCommand -Arguments @(
        'research', 'run', $Query,
        '--model', $Model,
        '--poll-interval', [string]$PollIntervalSeconds,
        '--timeout', [string]$TimeoutSeconds,
        '--json',
        '-o', $resolvedOutputPath
    )
}
else {
    $args = @(
        'search', $Query,
        '--depth', $Depth,
        '--max-results', [string]$MaxResults,
        '--topic', $Topic,
        '--json',
        '-o', $resolvedOutputPath
    )
    if (-not [string]::IsNullOrWhiteSpace($Country)) {
        $args += @('--country', $Country)
    }
    Invoke-TavilyCommand -Arguments $args
}

$validation = & $validate -Path $resolvedOutputPath -Kind $Kind | ConvertFrom-Json
if ($Kind -eq 'research' -and $validation.recoverable -eq $true -and $validation.request_id) {
    Invoke-TavilyPoll -Id ([string]$validation.request_id)
    $validation = & $validate -Path $resolvedOutputPath -Kind $Kind | ConvertFrom-Json
}

if ($validation.ok -ne $true) {
    throw ("Tavily workpack did not validate: {0}" -f (@($validation.errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    reused_existing = $false
    output = $resolvedOutputPath
    validation = $validation
} | ConvertTo-Json -Depth 8 -Compress
