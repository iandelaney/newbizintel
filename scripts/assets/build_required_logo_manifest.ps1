param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [switch]$AcquireMissing,

    [int]$MinimumPixels = 64
)

$ErrorActionPreference = 'Stop'

function ConvertTo-Slug {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }

    $slug = $Value.ToLowerInvariant() -replace '^https?://', ''
    $slug = $slug -replace '^www\.', ''
    $slug = $slug -replace '[^a-z0-9]+', '-'
    return $slug.Trim('-')
}

function Ensure-Property {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
    else {
        $Object.$Name = $Value
    }
}

function Resolve-LocalAssetPath {
    param(
        [string]$Value,
        [string]$BrandFolder,
        [string]$AssetDirectory
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }

    $candidate = $Value
    try {
        $uri = [System.Uri]$Value
        if ($uri.IsAbsoluteUri) {
            if ($uri.Scheme -eq 'file') { $candidate = $uri.LocalPath } else { return $null }
        }
    }
    catch {
    }

    if ([System.IO.Path]::IsPathRooted($candidate)) { return $candidate }

    $assetRelativePath = Join-Path $AssetDirectory $candidate
    if (Test-Path -LiteralPath $assetRelativePath) { return $assetRelativePath }

    return (Join-Path $BrandFolder $candidate)
}

function Get-HostSlug {
    param([string]$Url)

    if ([string]::IsNullOrWhiteSpace($Url)) { return '' }

    try {
        $host = ([System.Uri]$Url).Host -replace '^www\.', ''
        return ConvertTo-Slug $host
    }
    catch {
        return ''
    }
}

function Get-DomainUrl {
    param([string]$Url)

    if ([string]::IsNullOrWhiteSpace($Url)) { return '' }

    try {
        $uri = [System.Uri]$Url
        if ($uri.IsAbsoluteUri -and $uri.Scheme -in @('http', 'https')) {
            return ('{0}://{1}/' -f $uri.Scheme, $uri.Host)
        }
    }
    catch {
    }

    return ''
}

function Get-ImageQuality {
    param([string]$Path)

    $result = [ordered]@{
        exists = $false
        valid_image = $false
        width = 0
        height = 0
        bytes = 0
        format = ''
        reason = ''
    }

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        $result.reason = 'missing'
        return [pscustomobject]$result
    }

    $item = Get-Item -LiteralPath $Path
    $result.exists = $true
    $result.bytes = [int64]$item.Length
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    $result.format = $ext.TrimStart('.')

    if ($item.Length -lt 256) {
        $result.reason = 'too few bytes to be a reliable logo'
        return [pscustomobject]$result
    }

    if ($ext -eq '.svg') {
        try {
            [xml]$svg = Get-Content -LiteralPath $Path -Raw
            $viewBox = [string]$svg.DocumentElement.GetAttribute('viewBox')
            if (-not [string]::IsNullOrWhiteSpace($viewBox)) {
                $parts = $viewBox -split '\s+'
                if ($parts.Count -ge 4) {
                    $result.width = [int][double]$parts[2]
                    $result.height = [int][double]$parts[3]
                    $result.valid_image = ($result.width -ge 1 -and $result.height -ge 1)
                    return [pscustomobject]$result
                }
            }
            $result.valid_image = $true
            return [pscustomobject]$result
        }
        catch {
            $result.reason = 'invalid svg'
            return [pscustomobject]$result
        }
    }

    try {
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $image = [System.Drawing.Image]::FromFile($Path)
        try {
            $result.width = [int]$image.Width
            $result.height = [int]$image.Height
            $result.valid_image = ($image.Width -gt 0 -and $image.Height -gt 0)
        }
        finally {
            $image.Dispose()
        }
    }
    catch {
        $result.reason = 'unreadable image'
    }

    return [pscustomobject]$result
}

function Test-QualityAccepted {
    param(
        [object]$Quality,
        [int]$MinimumPixels
    )

    if (-not $Quality.exists -or -not $Quality.valid_image) { return $false }
    if ($Quality.width -gt 0 -and $Quality.height -gt 0) {
        return ($Quality.width -ge $MinimumPixels -and $Quality.height -ge $MinimumPixels)
    }
    return $true
}

function Find-LogoAsset {
    param(
        [string[]]$Names,
        [string]$BrandFolder,
        [string]$AssetDirectory,
        [int]$MinimumPixels,
        [string[]]$ForbiddenLeafNames = @()
    )

    foreach ($name in $Names) {
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        if ((Split-Path -Leaf $name) -in $ForbiddenLeafNames) { continue }

        $candidate = Resolve-LocalAssetPath -Value $name -BrandFolder $BrandFolder -AssetDirectory $AssetDirectory
        $quality = Get-ImageQuality -Path $candidate
        if (Test-QualityAccepted -Quality $quality -MinimumPixels $MinimumPixels) {
            return [pscustomobject]@{
                asset = $name
                resolved_path = $candidate
                quality = $quality
                resolution_source = 'local'
            }
        }
    }

    return $null
}

function Save-FaviconCandidate {
    param(
        [string]$DomainUrl,
        [string]$DestinationPath,
        [int]$MinimumPixels
    )

    if ([string]::IsNullOrWhiteSpace($DomainUrl)) { return $null }

    $encodedDomain = [System.Uri]::EscapeDataString($DomainUrl)
    $attempts = @(
        "https://www.google.com/s2/favicons?sz=256&domain_url=$encodedDomain",
        "https://www.google.com/s2/favicons?sz=128&domain_url=$encodedDomain"
    )

    foreach ($url in $attempts) {
        $tempPath = "$DestinationPath.download"
        try {
            Invoke-WebRequest -Uri $url -OutFile $tempPath -UseBasicParsing -TimeoutSec 20
            $quality = Get-ImageQuality -Path $tempPath
            if (Test-QualityAccepted -Quality $quality -MinimumPixels $MinimumPixels) {
                Move-Item -LiteralPath $tempPath -Destination $DestinationPath -Force
                $quality = Get-ImageQuality -Path $DestinationPath
                return [pscustomobject]@{
                    ok = $true
                    source_url = $url
                    path = $DestinationPath
                    quality = $quality
                }
            }
        }
        catch {
        }
        finally {
            if (Test-Path -LiteralPath $tempPath) {
                Remove-Item -LiteralPath $tempPath -Force
            }
        }
    }

    return $null
}

function Get-CompetitorCandidateNames {
    param([string]$Name, [string]$Website)

    $names = New-Object System.Collections.Generic.List[string]
    $hostSlug = Get-HostSlug $Website
    $nameSlug = ConvertTo-Slug $Name
    foreach ($slug in @($hostSlug, $nameSlug)) {
        if ([string]::IsNullOrWhiteSpace($slug)) { continue }
        foreach ($suffix in @('logo', 'mark', 'favicon')) {
            $names.Add("$slug-$suffix.png")
            $names.Add("$slug-$suffix.jpg")
            $names.Add("$slug-$suffix.jpeg")
            $names.Add("$slug-$suffix.svg")
        }
        $names.Add("$slug.png")
        $names.Add("$slug.jpg")
        $names.Add("$slug.jpeg")
        $names.Add("$slug.svg")
    }
    return @($names | Select-Object -Unique)
}

function Get-NewsCandidateNames {
    param([string]$Source, [string]$Url)

    $names = New-Object System.Collections.Generic.List[string]
    $sourceSlug = ConvertTo-Slug $Source
    $hostSlug = Get-HostSlug $Url
    foreach ($slug in @($sourceSlug, $hostSlug)) {
        if ([string]::IsNullOrWhiteSpace($slug)) { continue }
        foreach ($suffix in @('news', 'logo', 'mark', 'favicon')) {
            $names.Add("$slug-$suffix.png")
            $names.Add("$slug-$suffix.jpg")
            $names.Add("$slug-$suffix.jpeg")
            $names.Add("$slug-$suffix.svg")
        }
        $names.Add("$slug.png")
        $names.Add("$slug.jpg")
        $names.Add("$slug.jpeg")
        $names.Add("$slug.svg")
    }
    return @($names | Select-Object -Unique)
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$brandFolder = Split-Path -Parent $resolvedDataPath
$assetDirectory = Join-Path $brandFolder 'slide-assets'
New-Item -ItemType Directory -Path $assetDirectory -Force | Out-Null

$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$logoHashes = @{}

$brandName = [string]$data.brand.name
$brandSlug = if (-not [string]::IsNullOrWhiteSpace([string]$data.brand.slug)) { [string]$data.brand.slug } else { ConvertTo-Slug $brandName }
$brandCandidates = @(
    [string]$data.brand.logo_url,
    [string]$data.brand.mark_url,
    "slide-assets/$brandSlug-logo.png",
    "slide-assets/$brandSlug-logo.jpg",
    "slide-assets/$brandSlug-logo.svg",
    "slide-assets/$brandSlug-mark.png",
    "slide-assets/$brandSlug-mark.jpg",
    "slide-assets/$brandSlug-mark.svg",
    "slide-assets/logo.png",
    "slide-assets/logo.svg",
    "slide-assets/mark.png",
    "slide-assets/mark.svg"
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

$brandLogo = Find-LogoAsset -Names $brandCandidates -BrandFolder $brandFolder -AssetDirectory $assetDirectory -MinimumPixels $MinimumPixels
if (-not $brandLogo -and $AcquireMissing) {
    $targetName = "$brandSlug-logo.png"
    $targetPath = Join-Path $assetDirectory $targetName
    $download = Save-FaviconCandidate -DomainUrl (Get-DomainUrl ([string]$data.brand.website)) -DestinationPath $targetPath -MinimumPixels $MinimumPixels
    if ($download) {
        Ensure-Property -Object $data.brand -Name 'logo_url' -Value ("slide-assets/$targetName")
        $brandLogo = [pscustomobject]@{
            asset = "slide-assets/$targetName"
            resolved_path = $targetPath
            quality = $download.quality
            resolution_source = 'acquired-favicon'
        }
    }
}

if (-not $brandLogo) {
    $errors.Add('brand.logo_url/brand.mark_url is missing or failed image-quality validation; the report header would fall back to initials.')
}

$competitorResults = @()
$competitors = @($data.competitive_landscape.table)
for ($i = 0; $i -lt $competitors.Count; $i++) {
    $row = $competitors[$i]
    $name = [string]$row.competitor
    $website = [string]$row.website
    $explicit = @([string]$row.logo_url, [string]$row.competitor_logo_url, [string]$row.badge_url, [string]$row.mark_url) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $candidates = @($explicit) + (Get-CompetitorCandidateNames -Name $name -Website $website)
    $logo = Find-LogoAsset -Names $candidates -BrandFolder $brandFolder -AssetDirectory $assetDirectory -MinimumPixels $MinimumPixels

    if (-not $logo -and $AcquireMissing) {
        $slug = ConvertTo-Slug $name
        $targetName = "$slug-favicon.png"
        $targetPath = Join-Path $assetDirectory $targetName
        $download = Save-FaviconCandidate -DomainUrl (Get-DomainUrl $website) -DestinationPath $targetPath -MinimumPixels $MinimumPixels
        if ($download) {
            Ensure-Property -Object $row -Name 'logo_url' -Value $targetName
            $logo = [pscustomobject]@{
                asset = $targetName
                resolved_path = $targetPath
                quality = $download.quality
                resolution_source = 'acquired-favicon'
            }
        }
    }

    if (-not $logo) {
        $errors.Add(("competitive_landscape.table[{0}] {1} has no valid logo asset." -f $i, $name))
    }

    if ($logo -and (Test-Path -LiteralPath $logo.resolved_path)) {
        $hash = (Get-FileHash -LiteralPath $logo.resolved_path -Algorithm SHA256).Hash
        if ($logoHashes.ContainsKey($hash) -and $logoHashes[$hash] -ne $name) {
            $warnings.Add(("Logo asset for {0} has the same hash as {1}; check for generic favicon fallback." -f $name, $logoHashes[$hash]))
        }
        else {
            $logoHashes[$hash] = $name
        }
    }

    $competitorResults += [pscustomobject]@{
        index = $i
        name = $name
        website = $website
        asset = if ($logo) { $logo.asset } else { '' }
        resolved_path = if ($logo) { $logo.resolved_path } else { '' }
        resolution_source = if ($logo) { $logo.resolution_source } else { 'missing' }
        quality = if ($logo) { $logo.quality } else { $null }
        ok = [bool]$logo
    }
}

$newsResults = @()
$newsItems = @($data.brand_reputation.influential_news)
for ($i = 0; $i -lt $newsItems.Count; $i++) {
    $item = $newsItems[$i]
    $source = [string]$item.source
    $url = [string]$item.url
    $explicit = @([string]$item.publisher_logo_url, [string]$item.source_logo_url, [string]$item.logo_url) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Split-Path -Leaf $_) -ne 'news.png' }
    $candidates = @($explicit) + (Get-NewsCandidateNames -Source $source -Url $url)

    $logo = $null
    if (-not [string]::IsNullOrWhiteSpace($source) -and -not [string]::IsNullOrWhiteSpace($brandName) -and $source.Trim().ToLowerInvariant() -eq $brandName.Trim().ToLowerInvariant()) {
        $logo = $brandLogo
    }
    if (-not $logo) {
        $logo = Find-LogoAsset -Names $candidates -BrandFolder $brandFolder -AssetDirectory $assetDirectory -MinimumPixels $MinimumPixels -ForbiddenLeafNames @('news.png')
    }

    if (-not $logo -and $AcquireMissing) {
        $slug = ConvertTo-Slug $source
        $targetName = "$slug-news.png"
        $targetPath = Join-Path $assetDirectory $targetName
        $domainUrl = if (-not [string]::IsNullOrWhiteSpace($url)) { Get-DomainUrl $url } else { Get-DomainUrl ([string]$data.brand.website) }
        if (-not [string]::IsNullOrWhiteSpace($source) -and -not [string]::IsNullOrWhiteSpace($brandName) -and $source.Trim().ToLowerInvariant() -eq $brandName.Trim().ToLowerInvariant()) {
            $domainUrl = Get-DomainUrl ([string]$data.brand.website)
        }
        $download = Save-FaviconCandidate -DomainUrl $domainUrl -DestinationPath $targetPath -MinimumPixels $MinimumPixels
        if ($download) {
            Ensure-Property -Object $item -Name 'publisher_logo_url' -Value $targetName
            $logo = [pscustomobject]@{
                asset = $targetName
                resolved_path = $targetPath
                quality = $download.quality
                resolution_source = 'acquired-favicon'
            }
        }
    }
    elseif ($logo -and $logo.asset -and ((Split-Path -Leaf ([string]$logo.asset)) -ne 'news.png')) {
        Ensure-Property -Object $item -Name 'publisher_logo_url' -Value ([string]$logo.asset)
    }

    if (-not $logo) {
        $errors.Add(("brand_reputation.influential_news[{0}] {1} has no valid source logo asset." -f $i, $source))
    }
    elseif ((Split-Path -Leaf ([string]$logo.asset)) -eq 'news.png') {
        $errors.Add(("brand_reputation.influential_news[{0}] {1} uses the generic news.png badge, which is not allowed for final output." -f $i, $source))
    }

    $newsResults += [pscustomobject]@{
        index = $i
        source = $source
        headline = [string]$item.headline
        url = $url
        asset = if ($logo) { $logo.asset } else { '' }
        resolved_path = if ($logo) { $logo.resolved_path } else { '' }
        resolution_source = if ($logo) { $logo.resolution_source } else { 'missing' }
        quality = if ($logo) { $logo.quality } else { $null }
        ok = [bool]$logo
    }
}

if ($AcquireMissing) {
    & (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $resolvedDataPath -InputObject $data
}

$manifestPath = Join-Path $brandFolder 'required-logo-manifest.json'
$manifest = [pscustomobject]@{
    ok = ($errors.Count -eq 0)
    data = $resolvedDataPath
    asset_directory = $assetDirectory
    minimum_pixels = $MinimumPixels
    brand = [pscustomobject]@{
        name = $brandName
        website = [string]$data.brand.website
        asset = if ($brandLogo) { $brandLogo.asset } else { '' }
        resolved_path = if ($brandLogo) { $brandLogo.resolved_path } else { '' }
        resolution_source = if ($brandLogo) { $brandLogo.resolution_source } else { 'missing' }
        quality = if ($brandLogo) { $brandLogo.quality } else { $null }
        ok = [bool]$brandLogo
    }
    competitors = $competitorResults
    news_sources = $newsResults
    warnings = @($warnings)
    errors = @($errors)
}

& (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $manifestPath -InputObject $manifest

if ($errors.Count -gt 0) {
    throw ("Required logo manifest failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    manifest = $manifestPath
    brand_logo = $manifest.brand
    competitor_count = $competitorResults.Count
    news_source_count = $newsResults.Count
    warnings = @($warnings)
} | ConvertTo-Json -Depth 8 -Compress
