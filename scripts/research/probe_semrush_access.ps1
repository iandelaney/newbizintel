param(
    [string]$DataPath,
    [string]$Domain,
    [string]$BrandFolder,
    [string]$OutputPath,
    [ValidateSet('uk', 'us')]
    [string]$Database = 'uk',
    [switch]$ComposioMcpAvailable,
    [switch]$JinaFallbackAvailable
)

$ErrorActionPreference = 'Stop'

if (-not $DataPath -and -not $Domain) {
    throw 'Provide either -DataPath or -Domain.'
}

if (-not $BrandFolder) {
    if ($DataPath) {
        $BrandFolder = Split-Path -Parent (Resolve-Path -LiteralPath $DataPath).Path
    }
    else {
        $BrandFolder = (Get-Location).Path
    }
}

$resolvedBrandFolder = (Resolve-Path -LiteralPath $BrandFolder).Path
if (-not $OutputPath) {
    $OutputPath = Join-Path $resolvedBrandFolder 'semrush-access.json'
}

$planArgs = @{
    Database = $Database
}
if ($DataPath) {
    $planArgs.DataPath = (Resolve-Path -LiteralPath $DataPath).Path
}
if ($Domain) {
    $planArgs.Domain = $Domain
}

$plan = & (Join-Path $PSScriptRoot 'prepare_semrush_requests.ps1') @planArgs | ConvertFrom-Json
$envValue = [Environment]::GetEnvironmentVariable('SEMRUSH_API_KEY', 'Process')
if ([string]::IsNullOrWhiteSpace($envValue)) {
    $envValue = [Environment]::GetEnvironmentVariable('SEMRUSH_API_KEY', 'User')
}
if ([string]::IsNullOrWhiteSpace($envValue)) {
    $envValue = [Environment]::GetEnvironmentVariable('SEMRUSH_API_KEY', 'Machine')
}

$directAvailable = -not [string]::IsNullOrWhiteSpace($envValue)
$provider = if ($directAvailable) {
    'direct-api'
}
elseif ($ComposioMcpAvailable) {
    'composio-mcp'
}
elseif ($JinaFallbackAvailable) {
    'jina-public-web'
}
else {
    'blocked'
}

$status = if ($provider -eq 'blocked') {
    'blocked'
}
elseif ($provider -eq 'jina-public-web') {
    'fallback'
}
else {
    'available'
}

$access = [pscustomobject]@{
    ok = $provider -ne 'blocked'
    status = $status
    selected_provider = $provider
    provider_order = @('direct-api', 'composio-mcp', 'jina-public-web')
    next_backup_provider = $(if ($provider -eq 'direct-api' -and $ComposioMcpAvailable) { 'composio-mcp' } elseif ($provider -in @('direct-api', 'composio-mcp') -and $JinaFallbackAvailable) { 'jina-public-web' } else { $null })
    domain = $plan.domain
    database = $Database
    direct_api = [pscustomobject]@{
        available = $directAvailable
        credential_env = 'SEMRUSH_API_KEY'
        credential_value = $(if ($directAvailable) { 'present-redacted' } else { 'missing' })
    }
    composio_mcp = [pscustomobject]@{
        available = [bool]$ComposioMcpAvailable
        required_tool_slugs = @($plan.requests | ForEach-Object { $_.tool })
        role = 'Backup provider after direct SEMrush API is unavailable, quota-limited, or blocked.'
        note = 'Use direct Composio MCP tools only. Do not route SEMrush work through Rube when the user has requested Composio, not Rube.'
    }
    fallback = [pscustomobject]@{
        jina_public_web_available = [bool]$JinaFallbackAvailable
        role = 'Use only to support SEO/source context when SEMrush direct API and Composio MCP are unavailable or quota-limited.'
    }
    query_plan = $plan
    evidence_status = 'pending'
    fail_condition = 'A report must not claim SEMrush-backed evidence unless direct-api or composio-mcp returns at least two verified SEMrush evidence points. Jina/public web is fallback context, not SEMrush-backed evidence.'
}

& (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $OutputPath -InputObject $access

[pscustomobject]@{
    ok = $access.ok
    path = (Resolve-Path -LiteralPath $OutputPath).Path
    status = $access.status
    selected_provider = $access.selected_provider
    direct_api_available = $directAvailable
    composio_mcp_available = [bool]$ComposioMcpAvailable
    jina_fallback_available = [bool]$JinaFallbackAvailable
} | ConvertTo-Json -Depth 8 -Compress
