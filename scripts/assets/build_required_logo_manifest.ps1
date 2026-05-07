param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [switch]$AcquireMissing,

    [switch]$NoDataWrite,

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
    if ([string]$Quality.format -eq 'svg') {
        return $true
    }
    if ($Quality.width -gt 0 -and $Quality.height -gt 0) {
        return ($Quality.width -ge $MinimumPixels -and $Quality.height -ge $MinimumPixels)
    }
    return $true
}

function Test-SquarePreferredQuality {
    param([object]$Quality)

    if (-not $Quality.exists -or -not $Quality.valid_image) { return $false }
    if ($Quality.width -le 0 -or $Quality.height -le 0) { return $false }
    $aspectRatio = [double]$Quality.width / [double]$Quality.height
    return ($aspectRatio -ge 0.75 -and $aspectRatio -le 1.33)
}

function Add-CandidateAudit {
    param(
        [object]$Log,
        [string]$EntityType,
        [string]$EntityName,
        [string]$Candidate,
        [string]$ResolvedPath,
        [string]$ResolutionSource,
        [object]$Quality,
        [bool]$Accepted,
        [string]$Reason
    )

    if ($null -eq $Log) { return }

    if ([string]::IsNullOrWhiteSpace($Reason) -and $null -ne $Quality) {
        $Reason = [string]$Quality.reason
    }
    if ([string]::IsNullOrWhiteSpace($Reason)) {
        $Reason = $(if ($Accepted) { 'accepted' } else { 'quality threshold not met' })
    }

    $Log.Add([pscustomobject]@{
        entity_type = $EntityType
        entity_name = $EntityName
        candidate = $Candidate
        resolved_path = $ResolvedPath
        resolution_source = $ResolutionSource
        accepted = $Accepted
        reason = $Reason
        quality = $Quality
    }) | Out-Null
}

function Find-LogoAsset {
    param(
        [string[]]$Names,
        [string]$BrandFolder,
        [string]$AssetDirectory,
        [int]$MinimumPixels,
        [switch]$RejectGeneratedPptxFallbacks,
        [string[]]$ForbiddenLeafNames = @(),
        [object]$CandidateLog,
        [string]$EntityType = 'unknown',
        [string]$EntityName = '',
        [switch]$PreferSquare
    )

    $firstAccepted = $null
    foreach ($name in $Names) {
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        $leafName = Split-Path -Leaf $name
        if ($RejectGeneratedPptxFallbacks -and $leafName -match '(?i)-pptx-logo\.(png|jpe?g|webp|svg)$') {
            Add-CandidateAudit -Log $CandidateLog -EntityType $EntityType -EntityName $EntityName -Candidate $name -ResolvedPath '' -ResolutionSource 'local' -Quality $null -Accepted $false -Reason 'generated PPTX text-card fallback is not an acquired mandatory logo'
            continue
        }
        if ($leafName -in $ForbiddenLeafNames) {
            Add-CandidateAudit -Log $CandidateLog -EntityType $EntityType -EntityName $EntityName -Candidate $name -ResolvedPath '' -ResolutionSource 'local' -Quality $null -Accepted $false -Reason 'forbidden generic asset'
            continue
        }

        $candidate = Resolve-LocalAssetPath -Value $name -BrandFolder $BrandFolder -AssetDirectory $AssetDirectory
        $quality = Get-ImageQuality -Path $candidate
        $accepted = Test-QualityAccepted -Quality $quality -MinimumPixels $MinimumPixels
        Add-CandidateAudit -Log $CandidateLog -EntityType $EntityType -EntityName $EntityName -Candidate $name -ResolvedPath $candidate -ResolutionSource 'local' -Quality $quality -Accepted $accepted -Reason ''
        if ($accepted) {
            $result = [pscustomobject]@{
                asset = $name
                resolved_path = $candidate
                quality = $quality
                resolution_source = 'local'
            }
            if (-not $PreferSquare) {
                return $result
            }
            if (Test-SquarePreferredQuality -Quality $quality) {
                return $result
            }
            if ($null -eq $firstAccepted) {
                $firstAccepted = $result
            }
        }
    }

    return $firstAccepted
}

function Get-AbsoluteUrl {
    param(
        [string]$BaseUrl,
        [string]$Href
    )

    if ([string]::IsNullOrWhiteSpace($Href)) { return '' }
    try {
        return ([System.Uri]::new([System.Uri]$BaseUrl, $Href)).AbsoluteUri
    }
    catch {
        return ''
    }
}

function Get-UrlExtension {
    param(
        [string]$Url,
        [string]$FallbackPath
    )

    try {
        $path = ([System.Uri]$Url).AbsolutePath
        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        if ($extension -in @('.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.svg')) {
            return $extension
        }
    }
    catch {
    }

    $fallbackExtension = [System.IO.Path]::GetExtension($FallbackPath).ToLowerInvariant()
    if ($fallbackExtension) { return $fallbackExtension }
    return '.png'
}

function Add-UrlCandidate {
    param(
        [object]$List,
        [string]$Url,
        [string]$Source
    )

    if ([string]::IsNullOrWhiteSpace($Url)) { return }
    if (@($List | Where-Object { [string]$_.url -ceq $Url }).Count -gt 0) { return }
    $List.Add([pscustomobject]@{
        url = $Url
        source = $Source
    }) | Out-Null
}

function Get-SiteIconCandidates {
    param([string]$DomainUrl)

    $candidates = New-Object System.Collections.Generic.List[object]
    if ([string]::IsNullOrWhiteSpace($DomainUrl)) { return $candidates.ToArray() }

    try {
        $uri = [System.Uri]$DomainUrl
        $origin = ('{0}://{1}' -f $uri.Scheme, $uri.Host)

        foreach ($path in @('/apple-touch-icon.png', '/apple-touch-icon-precomposed.png', '/favicon-512x512.png', '/favicon-256x256.png', '/favicon-192x192.png', '/favicon-180x180.png', '/favicon-128x128.png', '/favicon.png', '/favicon.ico')) {
            Add-UrlCandidate -List $candidates -Url (Get-AbsoluteUrl -BaseUrl $origin -Href $path) -Source 'site-common-icon'
        }

        $response = Invoke-WebRequest -Uri $origin -UseBasicParsing -TimeoutSec 20
        $html = [string]$response.Content
        $linkMatches = [regex]::Matches($html, '<link\b[^>]*>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        foreach ($match in $linkMatches) {
            $tag = $match.Value
            $relMatch = [regex]::Match($tag, 'rel\s*=\s*["'']([^"'']+)["'']', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            $hrefMatch = [regex]::Match($tag, 'href\s*=\s*["'']([^"'']+)["'']', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if (-not $relMatch.Success -or -not $hrefMatch.Success) { continue }

            $rel = $relMatch.Groups[1].Value.ToLowerInvariant()
            $href = $hrefMatch.Groups[1].Value
            if ($rel -match 'icon|apple-touch-icon|mask-icon') {
                Add-UrlCandidate -List $candidates -Url (Get-AbsoluteUrl -BaseUrl $origin -Href $href) -Source 'site-declared-icon'
            }
            elseif ($rel -match 'manifest') {
                $manifestUrl = Get-AbsoluteUrl -BaseUrl $origin -Href $href
                if (-not [string]::IsNullOrWhiteSpace($manifestUrl)) {
                    try {
                        $manifest = Invoke-WebRequest -Uri $manifestUrl -UseBasicParsing -TimeoutSec 20 | Select-Object -ExpandProperty Content | ConvertFrom-Json
                        foreach ($icon in @($manifest.icons)) {
                            $src = [string]$icon.src
                            if (-not [string]::IsNullOrWhiteSpace($src)) {
                                Add-UrlCandidate -List $candidates -Url (Get-AbsoluteUrl -BaseUrl $manifestUrl -Href $src) -Source 'site-webmanifest-icon'
                            }
                        }
                    }
                    catch {
                    }
                }
            }
        }
    }
    catch {
    }

    return $candidates.ToArray()
}

function Get-WikimediaLogoCandidates {
    param([string]$EntityName)

    $candidates = New-Object System.Collections.Generic.List[object]
    if ([string]::IsNullOrWhiteSpace($EntityName)) { return $candidates.ToArray() }

    $clean = ($EntityName -replace '[^\p{L}\p{Nd}\s&.-]', '').Trim()
    $raw = $EntityName.Trim()
    $variantNames = New-Object System.Collections.Generic.List[string]
    foreach ($name in @($raw, $clean)) {
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        foreach ($variant in @(
            "$name Logo.svg",
            "$name logo.svg",
            "$name-Logo.svg",
            "$name-logo.svg",
            "$name Logo.png",
            "$name logo.png",
            "$name-Logo.png",
            "$name-logo.png"
        )) {
            if (-not [string]::IsNullOrWhiteSpace($variant) -and -not $variantNames.Contains($variant)) {
                $variantNames.Add($variant) | Out-Null
            }
        }
    }

    foreach ($variant in $variantNames.ToArray()) {
        $encoded = [System.Uri]::EscapeDataString($variant)
        Add-UrlCandidate -List $candidates -Url "https://commons.wikimedia.org/wiki/Special:FilePath/$encoded" -Source 'wikimedia-special-filepath'
    }

    return $candidates.ToArray()
}

function Get-WikimediaSearchLogoCandidates {
    param(
        [string]$EntityName,
        [string]$DomainUrl = ''
    )

    $candidates = New-Object System.Collections.Generic.List[object]
    if ([string]::IsNullOrWhiteSpace($EntityName) -and [string]::IsNullOrWhiteSpace($DomainUrl)) {
        return $candidates.ToArray()
    }

    $terms = New-Object System.Collections.Generic.List[string]
    foreach ($term in @(
        [string]$EntityName,
        ([string]$EntityName -replace '[^\p{L}\p{Nd}\s&.-]', '').Trim(),
        (([string]$EntityName -replace "['’]", '') -replace '[^\p{L}\p{Nd}\s&.-]', '').Trim()
    )) {
        if (-not [string]::IsNullOrWhiteSpace($term) -and -not $terms.Contains($term)) {
            $terms.Add($term) | Out-Null
        }
    }

    try {
        $host = ([System.Uri]$DomainUrl).Host -replace '^www\.', ''
        $hostFirstLabel = (($host -split '\.')[0] -replace '[^a-zA-Z0-9]+', ' ').Trim()
        if (-not [string]::IsNullOrWhiteSpace($hostFirstLabel) -and -not $terms.Contains($hostFirstLabel)) {
            $terms.Add($hostFirstLabel) | Out-Null
        }
    }
    catch {
    }

    $words = @((([string]$EntityName -replace "['’]", '') -replace '[^\p{L}\p{Nd}\s]+', ' ').Trim() -split '\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($words.Count -ge 1 -and -not $terms.Contains($words[0])) {
        $terms.Add($words[0]) | Out-Null
    }
    if ($words.Count -ge 2) {
        $shortName = ($words[0..1] -join ' ')
        if (-not $terms.Contains($shortName)) {
            $terms.Add($shortName) | Out-Null
        }
    }

    foreach ($term in $terms.ToArray()) {
        $search = [System.Uri]::EscapeDataString("$term logo")
        $apiUrl = "https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit=8&gsrsearch=$search&prop=imageinfo&iiprop=url|mime|size"
        try {
    $response = Invoke-WebRequest -Uri $apiUrl -UseBasicParsing -TimeoutSec 20 -Headers @{ 'User-Agent' = 'newbizintel-logo-acquisition/1.0' }
            $payload = $response.Content | ConvertFrom-Json
            if ($null -eq $payload.query -or $null -eq $payload.query.pages) { continue }

            $pages = @($payload.query.pages.PSObject.Properties.Value)
            foreach ($page in $pages) {
                $title = [string]$page.title
                if ($title -notmatch '(?i)logo') { continue }
                if ($title -match '(?i)\b(powered by|sponsored by|in partnership with)\b') { continue }
                if ($title -match '(?i)\b(frontage|store|shop|supermarket|building|signage)\b') { continue }

                $imageInfo = @($page.imageinfo)[0]
                $mime = [string]$imageInfo.mime
                if ($mime -notin @('image/svg+xml', 'image/png', 'image/jpeg', 'image/webp')) { continue }

                $url = [string]$imageInfo.url
                if ([string]::IsNullOrWhiteSpace($url)) { continue }

                Add-UrlCandidate -List $candidates -Url $url -Source 'wikimedia-api-search'
            }
        }
        catch {
        }
    }

    return $candidates.ToArray()
}

function Save-RemoteImageCandidate {
    param(
        [string]$Url,
        [string]$DestinationPath,
        [int]$MinimumPixels,
        [object]$CandidateLog,
        [string]$ResolutionSource,
        [string]$EntityType = 'unknown',
        [string]$EntityName = ''
    )

    if ([string]::IsNullOrWhiteSpace($Url)) { return $null }

    $extension = Get-UrlExtension -Url $Url -FallbackPath $DestinationPath
    $finalPath = [System.IO.Path]::ChangeExtension($DestinationPath, $extension)
    $tempPath = "$finalPath.download$extension"

    try {
        Invoke-WebRequest -Uri $Url -OutFile $tempPath -UseBasicParsing -TimeoutSec 20
        $quality = Get-ImageQuality -Path $tempPath
        $accepted = Test-QualityAccepted -Quality $quality -MinimumPixels $MinimumPixels
        Add-CandidateAudit -Log $CandidateLog -EntityType $EntityType -EntityName $EntityName -Candidate $Url -ResolvedPath $tempPath -ResolutionSource $ResolutionSource -Quality $quality -Accepted $accepted -Reason ''
        if ($accepted) {
            Move-Item -LiteralPath $tempPath -Destination $finalPath -Force
            $quality = Get-ImageQuality -Path $finalPath
            return [pscustomobject]@{
                ok = $true
                source_url = $Url
                path = $finalPath
                asset_name = (Split-Path -Leaf $finalPath)
                quality = $quality
                resolution_source = $ResolutionSource
            }
        }
    }
    catch {
        Add-CandidateAudit -Log $CandidateLog -EntityType $EntityType -EntityName $EntityName -Candidate $Url -ResolvedPath $tempPath -ResolutionSource $ResolutionSource -Quality $null -Accepted $false -Reason $_.Exception.Message
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
    }

    return $null
}

function Save-FaviconCandidate {
    param(
        [string]$DomainUrl,
        [string]$DestinationPath,
        [int]$MinimumPixels,
        [object]$CandidateLog,
        [string]$EntityType = 'unknown',
        [string]$EntityName = ''
    )

    if ([string]::IsNullOrWhiteSpace($DomainUrl)) { return $null }

    $encodedDomain = [System.Uri]::EscapeDataString($DomainUrl)
    $attempts = New-Object System.Collections.Generic.List[object]
    foreach ($candidate in Get-SiteIconCandidates -DomainUrl $DomainUrl) {
        Add-UrlCandidate -List $attempts -Url ([string]$candidate.url) -Source ([string]$candidate.source)
    }
    Add-UrlCandidate -List $attempts -Url "https://www.google.com/s2/favicons?sz=256&domain_url=$encodedDomain" -Source 'google-favicon'
    Add-UrlCandidate -List $attempts -Url "https://www.google.com/s2/favicons?sz=128&domain_url=$encodedDomain" -Source 'google-favicon'
    foreach ($candidate in Get-WikimediaLogoCandidates -EntityName $EntityName) {
        Add-UrlCandidate -List $attempts -Url ([string]$candidate.url) -Source ([string]$candidate.source)
    }
    foreach ($candidate in Get-WikimediaSearchLogoCandidates -EntityName $EntityName -DomainUrl $DomainUrl) {
        Add-UrlCandidate -List $attempts -Url ([string]$candidate.url) -Source ([string]$candidate.source)
    }

    foreach ($candidate in $attempts.ToArray()) {
        $download = Save-RemoteImageCandidate -Url ([string]$candidate.url) -DestinationPath $DestinationPath -MinimumPixels $MinimumPixels -CandidateLog $CandidateLog -ResolutionSource ([string]$candidate.source) -EntityType $EntityType -EntityName $EntityName
        if ($download) {
            return $download
        }
    }

    return $null
}

function Get-CompetitorCandidateNames {
    param([string]$Name, [string]$Website)

    $names = New-Object System.Collections.Generic.List[string]
    $hostSlug = Get-HostSlug $Website
    $nameSlug = ConvertTo-Slug $Name
    $depossessiveNameSlug = ConvertTo-Slug (([string]$Name -replace "['’]", ''))
    $domainNameSlug = ''
    try {
        $host = ([System.Uri]$Website).Host -replace '^www\.', ''
        $domainNameSlug = ConvertTo-Slug (($host -split '\.')[0])
    }
    catch {
    }
    foreach ($slug in @($hostSlug, $nameSlug, $depossessiveNameSlug, $domainNameSlug)) {
        if ([string]::IsNullOrWhiteSpace($slug)) { continue }
        foreach ($suffix in @('mark', 'favicon', 'logo')) {
            $names.Add("$slug-$suffix.png")
            $names.Add("$slug-$suffix.jpg")
            $names.Add("$slug-$suffix.jpeg")
            $names.Add("$slug-$suffix.svg")
            $names.Add("slide-assets/$slug-$suffix.png")
            $names.Add("slide-assets/$slug-$suffix.jpg")
            $names.Add("slide-assets/$slug-$suffix.jpeg")
            $names.Add("slide-assets/$slug-$suffix.svg")
        }
        $names.Add("$slug.png")
        $names.Add("$slug.jpg")
        $names.Add("$slug.jpeg")
        $names.Add("$slug.svg")
        $names.Add("slide-assets/$slug.png")
        $names.Add("slide-assets/$slug.jpg")
        $names.Add("slide-assets/$slug.jpeg")
        $names.Add("slide-assets/$slug.svg")
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
$baseHash = (Get-FileHash -LiteralPath $resolvedDataPath -Algorithm SHA256).Hash

$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json -Depth 100
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$candidateAudit = New-Object System.Collections.Generic.List[object]
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

$brandLogo = Find-LogoAsset -Names $brandCandidates -BrandFolder $brandFolder -AssetDirectory $assetDirectory -MinimumPixels $MinimumPixels -CandidateLog $candidateAudit -EntityType 'brand' -EntityName $brandName
if (-not $brandLogo -and $AcquireMissing) {
    $targetName = "$brandSlug-logo.png"
    $targetPath = Join-Path $assetDirectory $targetName
    $download = Save-FaviconCandidate -DomainUrl (Get-DomainUrl ([string]$data.brand.website)) -DestinationPath $targetPath -MinimumPixels $MinimumPixels -CandidateLog $candidateAudit -EntityType 'brand' -EntityName $brandName
    if ($download) {
        $actualName = if ($download.asset_name) { [string]$download.asset_name } else { $targetName }
        Ensure-Property -Object $data.brand -Name 'logo_url' -Value ("slide-assets/$actualName")
        $brandLogo = [pscustomobject]@{
            asset = "slide-assets/$actualName"
            resolved_path = [string]$download.path
            quality = $download.quality
            resolution_source = [string]$download.resolution_source
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
    $logo = Find-LogoAsset -Names $candidates -BrandFolder $brandFolder -AssetDirectory $assetDirectory -MinimumPixels $MinimumPixels -RejectGeneratedPptxFallbacks -CandidateLog $candidateAudit -EntityType 'competitor' -EntityName $name -PreferSquare

    if ($AcquireMissing -and ($null -eq $logo -or -not (Test-SquarePreferredQuality -Quality $logo.quality))) {
        $slug = ConvertTo-Slug $name
        $targetName = "$slug-mark.png"
        $targetPath = Join-Path $assetDirectory $targetName
        $download = Save-FaviconCandidate -DomainUrl (Get-DomainUrl $website) -DestinationPath $targetPath -MinimumPixels $MinimumPixels -CandidateLog $candidateAudit -EntityType 'competitor' -EntityName $name
        if ($download) {
            $actualName = if ($download.asset_name) { [string]$download.asset_name } else { $targetName }
            $actualAsset = "slide-assets/$actualName"
            Ensure-Property -Object $row -Name 'logo_url' -Value $actualAsset
            $logo = [pscustomobject]@{
                asset = $actualAsset
                resolved_path = [string]$download.path
                quality = $download.quality
                resolution_source = [string]$download.resolution_source
            }
        }
        elseif ($logo -and -not (Test-SquarePreferredQuality -Quality $logo.quality)) {
            $warnings.Add(("Competitor logo for {0} is a wide wordmark and no square mark/favicon could be acquired; using wordmark fallback." -f $name))
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
        $logo = Find-LogoAsset -Names $candidates -BrandFolder $brandFolder -AssetDirectory $assetDirectory -MinimumPixels $MinimumPixels -ForbiddenLeafNames @('news.png') -CandidateLog $candidateAudit -EntityType 'news_source' -EntityName $source
    }

    if (-not $logo -and $AcquireMissing) {
        $slug = ConvertTo-Slug $source
        $targetName = "$slug-news.png"
        $targetPath = Join-Path $assetDirectory $targetName
        $domainUrl = if (-not [string]::IsNullOrWhiteSpace($url)) { Get-DomainUrl $url } else { Get-DomainUrl ([string]$data.brand.website) }
        if (-not [string]::IsNullOrWhiteSpace($source) -and -not [string]::IsNullOrWhiteSpace($brandName) -and $source.Trim().ToLowerInvariant() -eq $brandName.Trim().ToLowerInvariant()) {
            $domainUrl = Get-DomainUrl ([string]$data.brand.website)
        }
        $download = Save-FaviconCandidate -DomainUrl $domainUrl -DestinationPath $targetPath -MinimumPixels $MinimumPixels -CandidateLog $candidateAudit -EntityType 'news_source' -EntityName $source
        if ($download) {
            $actualName = if ($download.asset_name) { [string]$download.asset_name } else { $targetName }
            $actualAsset = "slide-assets/$actualName"
            Ensure-Property -Object $item -Name 'publisher_logo_url' -Value $actualAsset
            $logo = [pscustomobject]@{
                asset = $actualAsset
                resolved_path = [string]$download.path
                quality = $download.quality
                resolution_source = [string]$download.resolution_source
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

if ($AcquireMissing -and -not $NoDataWrite) {
    & (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $resolvedDataPath -InputObject $data
}

$manifestPath = Join-Path $brandFolder 'required-logo-manifest.json'
$brandLogoAsset = ''
$brandLogoResolvedPath = ''
$brandLogoResolutionSource = 'missing'
$brandLogoQuality = $null
if ($null -ne $brandLogo) {
    $brandLogoAsset = $brandLogo.asset
    $brandLogoResolvedPath = $brandLogo.resolved_path
    $brandLogoResolutionSource = $brandLogo.resolution_source
    $brandLogoQuality = $brandLogo.quality
}
$candidateAuditArray = @()
foreach ($candidateAuditItem in $candidateAudit) {
    $candidateAuditArray += $candidateAuditItem
}
$rejectionCount = 0
foreach ($candidateAuditItem in $candidateAuditArray) {
    if ($candidateAuditItem.accepted -ne $true) {
        $rejectionCount++
    }
}
$warningsArray = @()
foreach ($warning in $warnings) { $warningsArray += $warning }
$errorsArray = @()
foreach ($errorItem in $errors) { $errorsArray += $errorItem }
$patches = New-Object System.Collections.Generic.List[object]
if ($brandLogo -and -not [string]::IsNullOrWhiteSpace([string]$brandLogo.asset)) {
    $patches.Add([pscustomobject]@{
        path = 'brand.logo_url'
        value = [string]$brandLogo.asset
    }) | Out-Null
}
foreach ($competitor in @($competitorResults)) {
    if ($competitor.ok -eq $true -and -not [string]::IsNullOrWhiteSpace([string]$competitor.asset)) {
        foreach ($fieldName in @('logo_url', 'competitor_logo_url', 'badge_url')) {
            $patches.Add([pscustomobject]@{
                path = ('competitive_landscape.table[{0}].{1}' -f [int]$competitor.index, $fieldName)
                value = [string]$competitor.asset
            }) | Out-Null
        }
    }
}
foreach ($newsSource in @($newsResults)) {
    if ($newsSource.ok -eq $true -and -not [string]::IsNullOrWhiteSpace([string]$newsSource.asset) -and ((Split-Path -Leaf ([string]$newsSource.asset)) -ne 'news.png')) {
        $patches.Add([pscustomobject]@{
            path = ('brand_reputation.influential_news[{0}].publisher_logo_url' -f [int]$newsSource.index)
            value = [string]$newsSource.asset
        }) | Out-Null
    }
}
$patchArray = @()
foreach ($patch in $patches) {
    $patchArray += $patch
}
$patchManifestPath = Join-Path $brandFolder 'assets-report-data-patch.json'
$patchManifest = [pscustomobject]@{
    ok = ($errors.Count -eq 0)
    domain = 'assets'
    data = (Split-Path -Leaf $resolvedDataPath)
    base_sha256 = $baseHash
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    patches = $patchArray
    source_manifest = (Split-Path -Leaf $manifestPath)
}

$manifest = [pscustomobject]@{
    ok = ($errors.Count -eq 0)
    data = $resolvedDataPath
    asset_directory = $assetDirectory
    minimum_pixels = $MinimumPixels
    brand = [pscustomobject]@{
        name = $brandName
        website = [string]$data.brand.website
        asset = $brandLogoAsset
        resolved_path = $brandLogoResolvedPath
        resolution_source = $brandLogoResolutionSource
        quality = $brandLogoQuality
        ok = ($null -ne $brandLogo)
    }
    competitors = $competitorResults
    news_sources = $newsResults
    candidate_audit = $candidateAuditArray
    rejection_count = $rejectionCount
    report_data_patch_manifest = $patchManifestPath
    warnings = $warningsArray
    errors = $errorsArray
}

& (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $manifestPath -InputObject $manifest
& (Join-Path $PSScriptRoot '..\common\write_json_utf8.ps1') -Path $patchManifestPath -InputObject $patchManifest

if ($errors.Count -gt 0) {
    throw ("Required logo manifest failed: {0}" -f (@($errors) -join '; '))
}

[pscustomobject]@{
    ok = $true
    manifest = $manifestPath
    report_data_patch_manifest = $patchManifestPath
    brand_logo = $manifest.brand
    competitor_count = $competitorResults.Count
    news_source_count = $newsResults.Count
    warnings = @($warnings)
} | ConvertTo-Json -Depth 8 -Compress
