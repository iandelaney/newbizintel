param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,

    [Parameter(Mandatory = $true)]
    [ValidateSet('assets','campaign-art')]
    [string]$Domain
)

$ErrorActionPreference = 'Stop'

function Ensure-Property {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][object]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
    else {
        $Object.$Name = $Value
    }
}

function Assert-AllowedPatchPath {
    param(
        [Parameter(Mandatory = $true)][string]$PatchPath,
        [Parameter(Mandatory = $true)][string]$Domain
    )

    $allowed = switch ($Domain) {
        'assets' {
            @(
                '^brand\.(logo_url|mark_url)$',
                '^competitive_landscape\.table\[\d+\]\.(logo_url|competitor_logo_url|badge_url|mark_url)$',
                '^brand_reputation\.influential_news\[\d+\]\.(publisher_logo_url|source_logo_url|logo_url)$'
            )
        }
        'campaign-art' {
            @(
                '^(creative_campaign_ideas|creative_campaigns)\.illustration_prompt_(manifest|brief)$',
                '^(creative_campaign_ideas|creative_campaigns)\.ideas\[\d+\]\.illustration_(url|medium|prompt|style_name|style_family|delivery_target|generation_backend|asset_role|import_source|imported_at|dimensions)$'
            )
        }
    }

    foreach ($pattern in $allowed) {
        if ($PatchPath -match $pattern) {
            return
        }
    }

    throw "Patch path '$PatchPath' is not allowed for reducer domain '$Domain'."
}

function Set-PathValue {
    param(
        [Parameter(Mandatory = $true)][object]$Root,
        [Parameter(Mandatory = $true)][string]$PatchPath,
        [AllowNull()][object]$Value
    )

    $parts = $PatchPath -split '\.'
    $cursor = $Root

    for ($i = 0; $i -lt $parts.Count; $i++) {
        $part = $parts[$i]
        if ($part -notmatch '^([A-Za-z0-9_]+)(?:\[(\d+)\])?$') {
            throw "Unsupported patch path segment '$part' in '$PatchPath'."
        }

        $name = $Matches[1]
        $indexText = $Matches[2]
        $isLast = ($i -eq ($parts.Count - 1))

        if ($isLast) {
            if (-not [string]::IsNullOrWhiteSpace($indexText)) {
                throw "Final patch segment cannot be an array index in '$PatchPath'."
            }
            Ensure-Property -Object $cursor -Name $name -Value $Value
            return
        }

        if ($null -eq $cursor.PSObject.Properties[$name]) {
            throw "Patch path '$PatchPath' cannot be applied because '$name' is missing."
        }

        $cursor = $cursor.$name
        if (-not [string]::IsNullOrWhiteSpace($indexText)) {
            $index = [int]$indexText
            $items = @($cursor)
            if ($index -lt 0 -or $index -ge $items.Count) {
                throw "Patch path '$PatchPath' index $index is outside the available range."
            }
            $cursor = $items[$index]
        }
    }
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$resolvedManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
$manifest = Get-Content -LiteralPath $resolvedManifestPath -Raw | ConvertFrom-Json

if ([string]$manifest.domain -ne $Domain) {
    throw "Manifest domain '$($manifest.domain)' does not match reducer domain '$Domain'."
}

$currentHash = (Get-FileHash -LiteralPath $resolvedDataPath -Algorithm SHA256).Hash
if (-not [string]::IsNullOrWhiteSpace([string]$manifest.base_sha256) -and [string]$manifest.base_sha256 -ne $currentHash) {
    throw "Refusing to reduce stale '$Domain' manifest. report-data.json hash is $currentHash but manifest was prepared against $($manifest.base_sha256)."
}

$patches = @($manifest.patches)
if ($patches.Count -eq 0) {
    throw "Manifest '$resolvedManifestPath' contains no patches."
}

$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
$applied = New-Object System.Collections.Generic.List[string]

foreach ($patch in $patches) {
    $path = [string]$patch.path
    if ([string]::IsNullOrWhiteSpace($path)) {
        throw "Manifest '$resolvedManifestPath' contains a patch with no path."
    }
    Assert-AllowedPatchPath -PatchPath $path -Domain $Domain
    Set-PathValue -Root $data -PatchPath $path -Value $patch.value
    $applied.Add($path) | Out-Null
}

& (Join-Path $PSScriptRoot 'write_json_utf8.ps1') -Path $resolvedDataPath -InputObject $data
$newHash = (Get-FileHash -LiteralPath $resolvedDataPath -Algorithm SHA256).Hash

[pscustomobject]@{
    ok = $true
    data = $resolvedDataPath
    manifest = $resolvedManifestPath
    domain = $Domain
    base_sha256 = [string]$manifest.base_sha256
    new_sha256 = $newHash
    applied_count = $applied.Count
    applied_paths = @($applied)
} | ConvertTo-Json -Depth 6 -Compress
