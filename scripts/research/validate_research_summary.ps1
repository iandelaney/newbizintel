param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'

function Test-HasValue {
    param([object]$Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return -not [string]::IsNullOrWhiteSpace($Value) }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        return @($Value).Count -gt 0
    }

    return $true
}

$allowedStatuses = @('pending', 'passed', 'partial', 'quota-limited', 'blocked', 'failed')
$allowedCurrentWebTools = @('tavily', 'jina', 'tavily+jina', 'jina+tavily')
$requiredValidationKeys = @('competitor_discovery', 'recent_news', 'reputation_public_web', 'source_gathering')
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

$resolvedPath = (Resolve-Path -LiteralPath $Path).Path
$summary = Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json

foreach ($field in @('mode', 'data_path', 'brand_name', 'brand_website', 'competitors', 'influential_news', 'reputation', 'seo', 'locked_sets', 'status', 'notes')) {
    if (-not (Test-HasValue $summary.$field)) {
        $errors.Add("Missing required field: $field")
    }
}

foreach ($field in @('competitor_discovery', 'recent_news', 'reputation_public_web', 'source_gathering', 'semrush')) {
    $value = [string]$summary.status.$field
    if (-not ($allowedStatuses -contains $value)) {
        $errors.Add("status.$field must be one of: $($allowedStatuses -join ', '). Current value: '$value'")
    }
}

if ($summary.mode -like 'live*') {
    if (-not (Test-HasValue $summary.tavily_validation)) {
        $errors.Add('Live research summary must include tavily_validation.')
    }
    else {
        foreach ($key in $requiredValidationKeys) {
            $entry = $summary.tavily_validation.$key
            if (-not (Test-HasValue $entry)) {
                $errors.Add("tavily_validation.$key is required for live research.")
                continue
            }

            $validationStatus = [string]$entry.status
            if (-not ($allowedStatuses -contains $validationStatus)) {
                $errors.Add("tavily_validation.$key.status must be one of: $($allowedStatuses -join ', '). Current value: '$validationStatus'")
            }
            if (-not ($allowedCurrentWebTools -contains ([string]$entry.tool))) {
                $errors.Add("tavily_validation.$key.tool must be one of: $($allowedCurrentWebTools -join ', ').")
            }
            if (-not (Test-HasValue $entry.used_in_sections)) {
                $warnings.Add("tavily_validation.$key.used_in_sections is empty.")
            }
        }
    }

    if (-not (Test-HasValue $summary.source_provenance_summary)) {
        $errors.Add('Live research summary must include source_provenance_summary.')
    }
}

[pscustomobject]@{
    ok = $errors.Count -eq 0
    path = $resolvedPath
    mode = [string]$summary.mode
    errors = @($errors)
    warnings = @($warnings)
} | ConvertTo-Json -Depth 8 -Compress
