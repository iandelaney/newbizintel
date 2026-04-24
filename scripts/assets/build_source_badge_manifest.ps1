param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath
)

$ErrorActionPreference = 'Stop'

function ConvertTo-Slug {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    $slug = $Value.ToLowerInvariant() -replace '^https?://', ''
    $slug = $slug -replace '^www\.', ''
    $slug = $slug -replace '[^a-z0-9]+', '-'
    return $slug.Trim('-')
}

function Resolve-NewsBadge {
    param(
        [object]$Item,
        [string]$AssetDirectory,
        [string]$BrandName,
        [string]$BrandLogoPath,
        [string]$BrandMarkPath
    )

    $explicitLogo = @(
        [string]$Item.publisher_logo_url,
        [string]$Item.source_logo_url,
        [string]$Item.logo_url
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1

    if ($explicitLogo) {
        if ((Split-Path -Leaf $explicitLogo) -eq 'news.png') {
            return [pscustomobject]@{
                badge = $explicitLogo
                resolved_path = (Join-Path $AssetDirectory $explicitLogo)
                exists = $false
                source = 'generic-not-allowed'
            }
        }

        $candidate = if ([System.IO.Path]::IsPathRooted($explicitLogo)) {
            $explicitLogo
        }
        else {
            $assetRelative = Join-Path $AssetDirectory $explicitLogo
            if (Test-Path -LiteralPath $assetRelative) {
                $assetRelative
            }
            else {
                Join-Path (Split-Path -Parent $AssetDirectory) $explicitLogo
            }
        }

        return [pscustomobject]@{
            badge = $explicitLogo
            resolved_path = $candidate
            exists = (Test-Path -LiteralPath $candidate)
            source = 'explicit'
        }
    }

    $source = [string]$Item.source
    if (
        -not [string]::IsNullOrWhiteSpace($source) -and
        -not [string]::IsNullOrWhiteSpace($BrandName) -and
        $source.Trim().ToLowerInvariant() -eq $BrandName.Trim().ToLowerInvariant()
    ) {
        foreach ($candidate in @($BrandMarkPath, $BrandLogoPath)) {
            if ((-not [string]::IsNullOrWhiteSpace($candidate)) -and (Test-Path -LiteralPath $candidate)) {
                return [pscustomobject]@{
                    badge = (Split-Path -Leaf $candidate)
                    resolved_path = $candidate
                    exists = $true
                    source = 'brand'
                }
            }
        }
    }

    $namesToTry = New-Object System.Collections.Generic.List[string]
    $sourceSlug = ConvertTo-Slug $source
    if ($sourceSlug) {
        foreach ($name in @("$sourceSlug-news.png", "$sourceSlug-favicon.png", "$sourceSlug-logo.png", "$sourceSlug.png")) {
            $namesToTry.Add($name)
        }
    }

    $url = [string]$Item.url
    if (-not [string]::IsNullOrWhiteSpace($url)) {
        try {
            $uri = [System.Uri]$url
            $hostSlug = ConvertTo-Slug $uri.Host
            if ($hostSlug) {
                foreach ($name in @("$hostSlug-news.png", "$hostSlug-favicon.png", "$hostSlug-logo.png", "$hostSlug.png")) {
                    $namesToTry.Add($name)
                }
            }
        }
        catch {
        }
    }

    foreach ($name in $namesToTry) {
        $candidate = Join-Path $AssetDirectory $name
        if (Test-Path -LiteralPath $candidate) {
            return [pscustomobject]@{
                badge = $name
                resolved_path = $candidate
                exists = $true
                source = $(if ($name -eq 'news.png') { 'generic' } else { 'inferred' })
            }
        }
    }

    return [pscustomobject]@{
        badge = ''
        resolved_path = ''
        exists = $false
        source = 'missing'
    }
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$brandFolder = Split-Path -Parent $resolvedDataPath
$assetDirectory = Join-Path $brandFolder 'slide-assets'
New-Item -ItemType Directory -Path $assetDirectory -Force | Out-Null

$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
$brandName = [string]$data.brand.name
$brandLogoPath = $null
$brandMarkPath = $null

foreach ($pair in @(
    @{ key = 'logo_url'; out = 'brandLogoPath' },
    @{ key = 'mark_url'; out = 'brandMarkPath' }
)) {
    $property = $data.brand.PSObject.Properties[$pair.key]
    $value = if ($property) { [string]$property.Value } else { '' }
    if ([string]::IsNullOrWhiteSpace($value)) {
        continue
    }

    $resolved = if ([System.IO.Path]::IsPathRooted($value)) {
        $value
    }
    else {
        Join-Path $brandFolder $value
    }

    if ($pair.out -eq 'brandLogoPath') {
        $brandLogoPath = $resolved
    }
    else {
        $brandMarkPath = $resolved
    }
}

$errors = New-Object System.Collections.Generic.List[string]
$items = @()
$newsItems = @($data.brand_reputation.influential_news)

for ($i = 0; $i -lt $newsItems.Count; $i++) {
    $item = $newsItems[$i]
    $badge = Resolve-NewsBadge -Item $item -AssetDirectory $assetDirectory -BrandName $brandName -BrandLogoPath $brandLogoPath -BrandMarkPath $brandMarkPath

    if (-not $badge.exists) {
        $errors.Add(("brand_reputation.influential_news[{0}] could not resolve a specific non-generic badge asset for {1}" -f $i, ([string]$item.source)))
    }

    $items += [pscustomobject]@{
        index = $i
        source = [string]$item.source
        headline = [string]$item.headline
        url = [string]$item.url
        badge = $badge.badge
        resolved_path = $badge.resolved_path
        resolution_source = $badge.source
        exists = [bool]$badge.exists
    }
}

$manifestPath = Join-Path $brandFolder 'source-badge-manifest.json'
$manifest = [pscustomobject]@{
    ok = ($errors.Count -eq 0)
    data = $resolvedDataPath
    asset_directory = $assetDirectory
    items = $items
    errors = @($errors)
}

& (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $manifestPath -InputObject $manifest

if ($errors.Count -gt 0) {
    throw ("Source badge manifest failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    manifest = $manifestPath
    badge_count = $items.Count
} | ConvertTo-Json -Depth 6 -Compress
