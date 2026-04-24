param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

function Test-HasValue {
    param([object]$Value)

    if ($null -eq $Value) {
        return $false
    }
    if ($Value -is [string]) {
        return -not [string]::IsNullOrWhiteSpace($Value)
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($item in $Value) {
            return $true
        }
        return $false
    }
    return $true
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$resolvePython = Join-Path $PSScriptRoot '..\common\resolve_python.ps1'
$python = & $resolvePython
$assetAuditJson = & $python (Join-Path $PSScriptRoot 'audit_campaign_art_assets.py') --data $resolvedDataPath
$assetAudit = $assetAuditJson | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $assetAudit.ok -ne $true) {
    foreach ($assetError in @($assetAudit.errors)) {
        $errors.Add([string]$assetError)
    }
}
foreach ($assetWarning in @($assetAudit.warnings)) {
    $warnings.Add([string]$assetWarning)
}

$ideas = @($data.creative_campaign_ideas.ideas)
$families = New-Object System.Collections.Generic.List[string]
$styleNames = New-Object System.Collections.Generic.List[string]

for ($i = 0; $i -lt $ideas.Count; $i++) {
    $idea = $ideas[$i]
    $pathPrefix = "creative_campaign_ideas.ideas[$i]"
    $prompt = [string]$idea.illustration_prompt
    $family = [string]$idea.illustration_style_family
    $styleName = [string]$idea.illustration_style_name

    if (-not (Test-HasValue $prompt)) {
        $errors.Add("$pathPrefix.illustration_prompt is required.")
        continue
    }

    foreach ($required in @('no words', 'no letters', 'no numbers', 'no typography', 'no readable text', 'no logos', 'no target brand')) {
        if ($prompt.ToLowerInvariant() -notlike "*$required*") {
            $errors.Add("$pathPrefix.illustration_prompt must include the hard negative constraint '$required'.")
        }
    }

    if ($prompt -match '(?i)\bshow\s+(the\s+)?(brand|logo|wordmark)|use\s+(the\s+)?brand\s+(assets|logo|identity)|include\s+(the\s+)?logo') {
        $errors.Add("$pathPrefix.illustration_prompt appears to invite brand asset or logo use.")
    }

    if (Test-HasValue $family) {
        $families.Add($family)
    }
    else {
        $warnings.Add("$pathPrefix.illustration_style_family is missing; run the campaign-art module to refresh prompt contracts.")
    }

    if (Test-HasValue $styleName) {
        $styleNames.Add($styleName)
    }
}

if ($ideas.Count -gt 1) {
    $duplicateFamilies = @($families | Group-Object | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name })
    if ($duplicateFamilies.Count -gt 0) {
        $errors.Add("Campaign artwork repeats media families: $($duplicateFamilies -join ', '). Use contrasting art/media treatments across the set.")
    }

    $duplicateStyles = @($styleNames | Group-Object | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name })
    if ($duplicateStyles.Count -gt 0) {
        $errors.Add("Campaign artwork repeats style names: $($duplicateStyles -join ', ').")
    }
}

if ($errors.Count -gt 0) {
    throw ("Campaign art contract audit failed: {0}" -f ($errors.ToArray() -join '; '))
}

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    idea_count = $ideas.Count
    style_families = $families.ToArray()
    style_names = $styleNames.ToArray()
    asset_quality = $assetAudit
    warnings = $warnings.ToArray()
} | ConvertTo-Json -Depth 5 -Compress
