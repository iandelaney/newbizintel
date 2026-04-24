param(
    [string]$DataPath,
    [string]$Domain,
    [ValidateSet('uk', 'us')]
    [string]$Database = 'uk'
)

$ErrorActionPreference = 'Stop'

function ConvertTo-RootDomain {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    $candidate = $Value.Trim()
    if ($candidate -notmatch '^https?://') {
        $candidate = "https://$candidate"
    }

    try {
        $uri = [System.Uri]$candidate
        return ($uri.Host -replace '^www\.', '').ToLowerInvariant()
    }
    catch {
        return (($Value -replace '^https?://', '') -replace '^www\.', '' -replace '/.*$', '').ToLowerInvariant()
    }
}

if (-not $Domain) {
    if (-not $DataPath) {
        throw 'Provide either -DataPath or -Domain.'
    }

    $resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
    $data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
    $Domain = [string]$data.brand.website
}
else {
    $resolvedDataPath = $null
}

$rootDomain = ConvertTo-RootDomain -Value $Domain
if ([string]::IsNullOrWhiteSpace($rootDomain)) {
    throw 'Could not resolve a root domain for SEMrush planning.'
}

$requests = @(
    [pscustomobject]@{
        priority = 1
        tool = 'SEMRUSH_DOMAIN_ORGANIC_SEARCH_KEYWORDS'
        parameters = [pscustomobject]@{
            domain = $rootDomain
            database = $Database
        }
        why = 'Primary evidence for keyword demand, ranking gaps, and SEO opportunity sizing.'
    },
    [pscustomobject]@{
        priority = 2
        tool = 'SEMRUSH_COMPETITORS_IN_ORGANIC_SEARCH'
        parameters = [pscustomobject]@{
            domain = $rootDomain
            database = $Database
        }
        why = 'Validates the competitor set before structure and recommendations are locked.'
    },
    [pscustomobject]@{
        priority = 3
        tool = 'SEMRUSH_INDEXED_PAGES'
        parameters = [pscustomobject]@{
            target = $rootDomain
            target_type = 'root_domain'
        }
        why = 'Checks index footprint and helps catch missing or underperforming site sections.'
    },
    [pscustomobject]@{
        priority = 4
        tool = 'SEMRUSH_BACKLINKS_OVERVIEW'
        parameters = [pscustomobject]@{
            target = $rootDomain
            target_type = 'root_domain'
        }
        why = 'Adds authority context if keyword or competitor evidence is thin.'
    }
)

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    domain = $rootDomain
    provider = 'Composio MCP'
    backup_provider = 'Jina AI'
    database = $Database
    requests = $requests
    status_guidance = [pscustomobject]@{
        passed = 'Use when at least two compact SEMrush-backed proof points can be included.'
        partial = 'Use when one SEMrush dataset exists but needs public-web supplementation.'
        quota_limited = 'Use when Composio SEMrush quota or entitlement blocks full retrieval.'
        blocked = 'Use when SEMrush cannot be authenticated or reached.'
    }
} | ConvertTo-Json -Depth 8
