param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [ValidateSet('search','research')]
    [string]$Kind = 'search'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
    throw "Tavily workpack not found: $Path"
}

$resolvedPath = (Resolve-Path -LiteralPath $Path).Path
$json = Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$status = [string]$json.status
$requestId = [string]$json.request_id

if ([string]::IsNullOrWhiteSpace($status)) {
    $status = 'completed'
}

$recoverableStatuses = @('timeout', 'pending', 'queued', 'running', 'processing', 'in_progress')
$failedStatuses = @('failed', 'error')
$recoverable = $recoverableStatuses -contains $status

if ($failedStatuses -contains $status) {
    $errors.Add("Tavily workpack reports failed status: $status")
}
elseif ($recoverable) {
    if ([string]::IsNullOrWhiteSpace($requestId)) {
        $errors.Add("Tavily workpack reports recoverable status '$status' but has no request_id to poll.")
    }
}
elseif ($Kind -eq 'search') {
    if (@($json.results).Count -eq 0) {
        $errors.Add('Tavily search workpack has no results.')
    }
}
elseif ($Kind -eq 'research') {
    $hasContent = -not [string]::IsNullOrWhiteSpace([string]$json.content)
    $hasAnswer = -not [string]::IsNullOrWhiteSpace([string]$json.answer)
    $hasSources = @($json.sources).Count -gt 0
    if (-not ($hasContent -or $hasAnswer -or $hasSources)) {
        $errors.Add('Tavily research workpack has no content, answer, or sources.')
    }
}

[pscustomobject]@{
    ok = ($errors.Count -eq 0 -and -not $recoverable)
    recoverable = $recoverable
    status = $status
    request_id = $(if ([string]::IsNullOrWhiteSpace($requestId)) { $null } else { $requestId })
    kind = $Kind
    path = $resolvedPath
    result_count = @($json.results).Count
    source_count = @($json.sources).Count
    errors = @($errors)
    warnings = @($warnings)
} | ConvertTo-Json -Depth 8 -Compress
