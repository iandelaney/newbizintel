param(
    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [string]$TemplatePath,

    [string]$OutputPath,

    [switch]$SkipValidation
)

$ErrorActionPreference = 'Stop'

if (-not $TemplatePath) {
    $TemplatePath = Join-Path $PSScriptRoot '..\..\templates\report-template.html'
}

$resolvedDataPath = (Resolve-Path -LiteralPath $DataPath).Path
$resolvedTemplatePath = (Resolve-Path -LiteralPath $TemplatePath).Path
$script:DataDirectory = Split-Path -Parent $resolvedDataPath

if (-not $SkipValidation) {
    $null = & (Join-Path $PSScriptRoot '..\structure\validate_report_data.ps1') -DataPath $resolvedDataPath | ConvertFrom-Json
}

if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $resolvedDataPath) 'newbizintel-report.html'
}

function ConvertTo-HtmlEncoded {
    param([string]$Text)

    if ($null -eq $Text) {
        return ''
    }

    $normalized = [System.Net.WebUtility]::HtmlDecode([string]$Text)
    $encoded = [System.Net.WebUtility]::HtmlEncode($normalized)
    $encoded = $encoded.Replace('&#39;', "'").Replace('&apos;', "'")
    return $encoded
}

function Get-SafeHref {
    param(
        [string]$Value,
        [switch]$AllowFile,
        [switch]$AllowFragment
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    $trimmed = $Value.Trim()
    if ($AllowFragment -and $trimmed.StartsWith('#')) {
        return $trimmed
    }

    try {
        $uri = [System.Uri]$trimmed
        if ($uri.IsAbsoluteUri) {
            if ($uri.Scheme -in @('http', 'https')) {
                return $uri.AbsoluteUri
            }
            if ($AllowFile -and $uri.Scheme -eq 'file') {
                return $uri.AbsoluteUri
            }
        }
    }
    catch {
        return ''
    }

    return ''
}

function Resolve-AssetUrl {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    $safeRemote = Get-SafeHref -Value $Value
    if (-not [string]::IsNullOrWhiteSpace($safeRemote)) {
        return $safeRemote
    }

    $candidate = $Value
    try {
        $uri = [System.Uri]$Value
        if ($uri.IsAbsoluteUri -and $uri.Scheme -eq 'file') {
            $candidate = $uri.LocalPath
        }
    }
    catch {
    }

    $candidatePaths = New-Object System.Collections.Generic.List[string]
    if ([System.IO.Path]::IsPathRooted($candidate)) {
        $candidatePaths.Add($candidate)
    }
    else {
        $candidatePaths.Add((Join-Path $script:DataDirectory $candidate))
        $normalisedCandidate = $candidate -replace '\\','/'
        if ($normalisedCandidate -notmatch '/') {
            $candidatePaths.Add((Join-Path (Join-Path $script:DataDirectory 'slide-assets') $candidate))
        }
    }

    foreach ($candidatePath in $candidatePaths) {
        try {
            $resolved = (Resolve-Path -LiteralPath $candidatePath -ErrorAction Stop).Path
        $dataRoot = [System.IO.Path]::GetFullPath($script:DataDirectory)
        $resolvedFull = [System.IO.Path]::GetFullPath($resolved)

        if ($resolvedFull.StartsWith($dataRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $relative = [System.IO.Path]::GetRelativePath($dataRoot, $resolvedFull)
            return ($relative -replace '\\','/')
        }

        return ([System.Uri]$resolvedFull).AbsoluteUri
        }
        catch {
        }
    }

    return ''
}


function Resolve-BrandBadgeAssetUrl {
    param([object]$Brand)

    $markUrl = Resolve-AssetUrl ([string]$Brand.mark_url)
    if (-not [string]::IsNullOrWhiteSpace($markUrl)) {
        return $markUrl
    }

    $brandSlug = [string]$Brand.slug
    $candidateNames = @()
    if (-not [string]::IsNullOrWhiteSpace($brandSlug)) {
        $candidateNames += @(
            "slide-assets/$brandSlug-mark.png",
            "slide-assets/$brandSlug-mark.svg",
            "slide-assets/$brandSlug-mark.webp",
            "slide-assets/$brandSlug-mark.jpg",
            "slide-assets/$brandSlug-mark.jpeg",
            "$brandSlug-mark.png",
            "$brandSlug-mark.svg",
            "$brandSlug-mark.webp",
            "$brandSlug-mark.jpg",
            "$brandSlug-mark.jpeg"
        )
    }
    $candidateNames += @(
        "slide-assets/mark.png",
        "slide-assets/mark.svg",
        "slide-assets/mark.webp",
        "slide-assets/mark.jpg",
        "slide-assets/mark.jpeg",
        "mark.png",
        "mark.svg",
        "mark.webp",
        "mark.jpg",
        "mark.jpeg"
    )

    foreach ($candidate in $candidateNames) {
        $resolved = Resolve-AssetUrl $candidate
        if (-not [string]::IsNullOrWhiteSpace($resolved)) {
            return $resolved
        }
    }

    $logoUrl = [string]$Brand.logo_url
    if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
        $logoFileName = [System.IO.Path]::GetFileName($logoUrl)
        if ($logoFileName -match '(?i)logo') {
            $markFileName = [regex]::Replace($logoFileName, '(?i)logo', 'mark')
            $markCandidate = $logoUrl -replace [regex]::Escape($logoFileName), $markFileName
            $resolvedMarkCandidate = Resolve-AssetUrl $markCandidate
            if (-not [string]::IsNullOrWhiteSpace($resolvedMarkCandidate)) {
                return $resolvedMarkCandidate
            }
        }
    }

    return Resolve-AssetUrl ([string]$Brand.logo_url)
}

function Resolve-BrandHeroAssetUrl {
    param([object]$Brand)

    $logoUrl = Resolve-AssetUrl ([string]$Brand.logo_url)
    if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
        return $logoUrl
    }

    return Resolve-BrandBadgeAssetUrl $Brand
}

function ConvertTo-AssetSlug {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }

    return (([regex]::Replace($Value.ToLowerInvariant(), '[^a-z0-9]+', '-')).Trim('-'))
}

function Resolve-LocalSlideAssetUrl {
    param(
        [string[]]$CandidateNames
    )

    foreach ($candidate in $CandidateNames) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }

        $resolved = Resolve-AssetUrl ("slide-assets/{0}" -f $candidate)
        if (-not [string]::IsNullOrWhiteSpace($resolved)) {
            return $resolved
        }
    }

    return ''
}

function Assert-NoLocalFileUrisInHtml {
    param([string]$Html)

    if ([string]::IsNullOrWhiteSpace($Html)) {
        return
    }

    $matches = [regex]::Matches($Html, '(?i)file:///[^"''<\s)]+')
    if ($matches.Count -eq 0) {
        return
    }

    $examples = $matches | Select-Object -First 5 | ForEach-Object { $_.Value } | Select-Object -Unique
    $message = "Rendered HTML contains local file URIs, which will break hosted reports. Examples: {0}" -f ($examples -join ', ')
    throw $message
}

function Resolve-CompetitorBadgeAssetUrl {
    param(
        [string]$Name,
        [string]$Website
    )

    $candidateNames = @()
    $hostSlug = ''
    try {
        if (-not [string]::IsNullOrWhiteSpace($Website)) {
            $hostSlug = ConvertTo-AssetSlug (([System.Uri]$Website).Host -replace '^www\.','')
        }
    }
    catch {
        $hostSlug = ''
    }

    $nameSlug = ConvertTo-AssetSlug $Name
    $depossessiveNameSlug = ConvertTo-AssetSlug (([string]$Name -replace "['’]", ''))
    $domainNameSlug = ''
    try {
        if (-not [string]::IsNullOrWhiteSpace($Website)) {
            $domainNameSlug = ConvertTo-AssetSlug ((([System.Uri]$Website).Host -replace '^www\.','' -split '\.')[0])
        }
    }
    catch {
        $domainNameSlug = ''
    }

    foreach ($slug in @($hostSlug, $nameSlug, $depossessiveNameSlug, $domainNameSlug)) {
        if ([string]::IsNullOrWhiteSpace($slug)) {
            continue
        }
        foreach ($suffix in @('news', 'favicon', 'logo', 'pptx-logo', 'mark')) {
            foreach ($extension in @('png', 'jpg', 'jpeg', 'svg', 'webp')) {
                $candidateNames += "$slug-$suffix.$extension"
            }
        }
        foreach ($extension in @('png', 'jpg', 'jpeg', 'svg', 'webp')) {
            $candidateNames += "$slug.$extension"
        }
    }

    return Resolve-LocalSlideAssetUrl $candidateNames
}

function Resolve-PublisherBadgeAssetUrl {
    param([object]$Item)

    $brandName = ''
    $brandWebsite = ''
    try {
        $reportData = Get-Variable -Name reportData -Scope Script -ErrorAction Stop
        $brandName = [string]$reportData.Value.brand.name
        $brandWebsite = [string]$reportData.Value.brand.website
    }
    catch {
        $brandName = ''
        $brandWebsite = ''
    }

    $explicitLogo = @(
        [string]$Item.publisher_logo_url,
        [string]$Item.source_logo_url,
        [string]$Item.logo_url
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
    if (-not [string]::IsNullOrWhiteSpace($explicitLogo)) {
        if ([System.IO.Path]::IsPathRooted($explicitLogo)) {
            if (Test-Path -LiteralPath $explicitLogo) {
                return (Resolve-AssetUrl $explicitLogo)
            }
        }
        else {
            $resolvedExplicitLogo = Resolve-AssetUrl $explicitLogo
            if (-not [string]::IsNullOrWhiteSpace($resolvedExplicitLogo)) {
                return $resolvedExplicitLogo
            }
        }
    }

    $sourceName = [string]$Item.source
    $sourceUrl = Get-SafeHref ([string]$Item.url)
    if (
        -not [string]::IsNullOrWhiteSpace($sourceName) -and
        -not [string]::IsNullOrWhiteSpace($brandName) -and
        $sourceName.Trim().ToLowerInvariant() -eq $brandName.Trim().ToLowerInvariant()
    ) {
        return Resolve-BrandBadgeAssetUrl ([pscustomobject]@{
            name = $brandName
            website = $brandWebsite
            logo_url = $reportData.Value.brand.logo_url
            mark_url = $reportData.Value.brand.mark_url
            slug = $reportData.Value.brand.slug
        })
    }

    return Resolve-CompetitorBadgeAssetUrl -Name $sourceName -Website $sourceUrl
}

function ConvertTo-SafeHtmlFragment {
    param([string]$Text)

    $safe = ConvertTo-HtmlEncoded $Text
    $safe = [regex]::Replace($safe, '&lt;(\/)?(p|strong|em|b|i|ul|ol|li)&gt;', '<$1$2>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $safe = [regex]::Replace($safe, '&lt;br\s*\/??&gt;', '<br>', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    return $safe
}

function ConvertTo-RichText {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ''
    }

    $trimmed = $Text.Trim()

    if ($trimmed -match '<\/?[a-zA-Z]') {
        return ConvertTo-SafeHtmlFragment $trimmed
    }

    $paragraphs = $trimmed -split '(\r?\n){2,}' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if (-not $paragraphs) {
        $paragraphs = @($trimmed)
    }

    return (($paragraphs | ForEach-Object {
        '<p>{0}</p>' -f (ConvertTo-HtmlEncoded $_.Trim())
    }) -join "`n")
}
function ConvertTo-ListHtml {
    param([object[]]$Items)

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $listItems = $Items | ForEach-Object {
        '<li>{0}</li>' -f (ConvertTo-RichText ([string]$_))
    }

    return "<ul>`n{0}`n</ul>" -f ($listItems -join "`n")
}

function ConvertTo-PublishedMessagingAssessmentHtml {
    param([object]$Assessment)

    if (-not $Assessment) {
        return ''
    }

    $statementRows = @($Assessment.published_statements)
    $statementHtml = ''
    if ($statementRows.Count -gt 0) {
        $decoratedRows = foreach ($row in $statementRows) {
            $sourceLabel = ConvertTo-HtmlEncoded ([string]$row.source)
            $sourceUrl = Get-SafeHref ([string]$row.source_url)
            $sourceHtml = $sourceLabel
            if (-not [string]::IsNullOrWhiteSpace($sourceUrl)) {
                $sourceHtml = '<a href="{0}" target="_blank" rel="noopener noreferrer">{1}</a>' -f (ConvertTo-HtmlEncoded $sourceUrl), $sourceLabel
            }

            [pscustomobject]@{
                label = $row.label
                statement = $row.statement
                source_html = $sourceHtml
            }
        }

        $statementHtml = ConvertTo-TableHtml -Rows $decoratedRows -Columns @(
            @{ header = 'Published statement'; key = 'label' },
            @{ header = 'What it says'; key = 'statement' },
            @{ header = 'Source'; key = 'source_html'; raw_html = $true }
        )
    }

    return @"
    <div class="score published-messaging-assessment">
      <span class="eyebrow">Published Messaging Assessment</span>
      $(ConvertTo-RichText ([string]$Assessment.summary))
      $statementHtml
      <p><span class="eyebrow">Reputation read-across</span> $(ConvertTo-HtmlEncoded ([string]$Assessment.reputation_read_across))</p>
      <p><span class="eyebrow">Messaging implication</span> $(ConvertTo-HtmlEncoded ([string]$Assessment.implication))</p>
    </div>
"@
}

function ConvertTo-RecommendationCardsHtml {
    param(
        [object[]]$Items,
        [string]$Tone = 'blue'
    )

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $index = 0
    $cardHtml = foreach ($item in $Items) {
        $index += 1
        $text = [string]$item
        $action = $text
        $why = ''
        $match = [regex]::Match($text, '(?is)^(?<action>.*?)(?:\s+Why:\s+)(?<why>.+)$')
        if ($match.Success) {
            $action = $match.Groups['action'].Value.Trim()
            $why = $match.Groups['why'].Value.Trim()
        }
        $whyHtml = ''
        if (-not [string]::IsNullOrWhiteSpace($why)) {
            $whyHtml = '<div class="recommendation-card__why"><span>Why this matters</span>{0}</div>' -f (ConvertTo-RichText $why)
        }

        @"
      <article class="recommendation-card recommendation-card--$Tone">
        <div class="recommendation-card__number">$(ConvertTo-HtmlEncoded ([string]$index))</div>
        <div class="recommendation-card__body">
          <div class="recommendation-card__action">$(ConvertTo-RichText $action)</div>
          $whyHtml
        </div>
      </article>
"@
    }

    return @"
    <div class="recommendation-grid recommendation-grid--$Tone">
$($cardHtml -join "`n")
    </div>
"@
}

function ConvertTo-SourceListHtml {
    param([object[]]$Items)

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $listItems = foreach ($item in $Items) {
        if ($item -is [string]) {
            '<li>{0}</li>' -f (ConvertTo-HtmlEncoded $item)
            continue
        }

        $label = ConvertTo-HtmlEncoded ([string]$item.label)
        $url = Get-SafeHref ([string]$item.url)
        if ([string]::IsNullOrWhiteSpace($url)) {
            '<li>{0}</li>' -f $label
            continue
        }
        '<li><a href="{0}">{1}</a></li>' -f (ConvertTo-HtmlEncoded $url), $label
    }

    return "<ul>`n{0}`n</ul>" -f ($listItems -join "`n")
}

function ConvertTo-TableHtml {
    param(
        [object[]]$Rows,
        [object[]]$Columns,
        [string]$TableClass = ''
    )

    $tableClassAttribute = ''
    if (-not [string]::IsNullOrWhiteSpace($TableClass)) {
        $tableClassAttribute = ' class="{0}"' -f (ConvertTo-HtmlEncoded $TableClass)
    }

    $headerHtml = $Columns | ForEach-Object {
        '<th>{0}</th>' -f (ConvertTo-HtmlEncoded ([string]$_.header))
    }

    $rowHtml = $Rows | ForEach-Object {
        $cells = foreach ($column in $Columns) {
            $renderRawHtml = $false
            if ($column -is [System.Collections.IDictionary] -and $column.Contains('raw_html')) {
                $renderRawHtml = [bool]$column['raw_html']
            }

            $value = $_.($column.key)
            if ($renderRawHtml) {
                '<td>{0}</td>' -f [string]$value
                continue
            }

            '<td>{0}</td>' -f (ConvertTo-RichText ([string]$value))
        }

        "<tr>`n{0}`n</tr>" -f ($cells -join "`n")
    }

    return @"
    <table$tableClassAttribute>
      <thead>
        <tr>
$($headerHtml -join "`n")
        </tr>
      </thead>
      <tbody>
$($rowHtml -join "`n")
      </tbody>
    </table>
"@
}

function ConvertTo-ClaimSignalHtml {
    param(
        [string]$Text,
        [string]$IconKey = 'summary'
    )

    return '<span style="display:inline-flex;align-items:center;gap:0.45rem;font-weight:700;color:#10263b"><span class="heading-icon" style="width:1rem;height:1rem">{0}</span><span>{1}</span></span>' -f (Get-IconSvg $IconKey), (ConvertTo-HtmlEncoded $Text)
}

function ConvertTo-CrossSectionReadoutHtml {
    param([object[]]$Items)

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $rows = foreach ($item in $Items) {
        $informs = [string]$item.informs_section
        $sharpens = [string]$item.sharpens_usp_ksp
        if ([string]::IsNullOrWhiteSpace($informs) -and [string]::IsNullOrWhiteSpace($sharpens)) {
            $informs = [string]$item.summary
        }

        [pscustomobject]@{
            area = [string]$item.area
            informs_section = $informs
            sharpens_usp_ksp = $sharpens
        }
    }

    return ConvertTo-TableHtml $rows @(
        @{ header = 'Connected section'; key = 'area' },
        @{ header = 'How USP and KSP findings should inform it'; key = 'informs_section' },
        @{ header = 'How that section should sharpen the USP and KSP verdict'; key = 'sharpens_usp_ksp' }
    )
}

function ConvertTo-DepartmentOpportunityTableHtml {
    param(
        [object[]]$Items,
        [string]$LeadDepartment
    )

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $rows = foreach ($item in $Items) {
        $tone = [string]$item.tone
        if ([string]::IsNullOrWhiteSpace($tone)) { $tone = 'warn' }
        $label = [string]$item.opportunity
        if ([string]::IsNullOrWhiteSpace($label)) { $label = 'Amber' }
        $department = [string]$item.department
        $toneClass = Get-OpportunityToneClass $tone
        $valueNote = [string]$item.value_note
        $leadHtml = ''
        if (-not [string]::IsNullOrWhiteSpace($LeadDepartment) -and $department -eq $LeadDepartment) {
            $leadHtml = ' <span class="opportunity-chip opportunity-chip--lead opportunity-chip--{0}">Lead</span>' -f $toneClass
        }
        $fitParts = @()
        if (-not [string]::IsNullOrWhiteSpace($valueNote)) {
            $fitParts += $valueNote
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$item.rationale)) {
            $fitParts += [string]$item.rationale
        }
        [pscustomobject]@{
            department = $department
            department_html = ConvertTo-DepartmentLabelHtml -Department $department -ToneClass $toneClass
            opportunity_html = '<span class="pill {0}">{1}</span>{2}' -f (ConvertTo-HtmlEncoded $tone), (ConvertTo-HtmlEncoded $label), $leadHtml
            fit = ($fitParts -join ' ')
        }
    }

    return ConvertTo-TableHtml $rows @(
        @{ header = 'Department'; key = 'department_html'; raw_html = $true },
        @{ header = 'Opportunity'; key = 'opportunity_html'; raw_html = $true },
        @{ header = 'Value and fit'; key = 'fit' }
    ) -TableClass 'opportunity-table'
}

function Get-OpportunityToneClass {
    param([string]$Tone)

    $normalized = ([string]$Tone).Trim().ToLowerInvariant()
    if ($normalized -eq 'good') { return 'good' }
    if ($normalized -eq 'bad') { return 'bad' }
    return 'warn'
}


function Get-DepartmentIconKey {
    param([string]$Department)

    $normalized = ([string]$Department).Trim().ToLowerInvariant()
    switch -Regex ($normalized) {
        '^pr\s*&\s*comms$' { return 'messaging' }
        '^content$' { return 'content' }
        '^digital marketing$' { return 'seo' }
        '^brands$' { return 'reputation' }
        '^creative services$' { return 'fixes' }
        '^insights\s*&\s*intelligence$' { return 'snapshot' }
        default { return 'opportunities' }
    }
}

function ConvertTo-DepartmentLabelHtml {
    param(
        [string]$Department,
        [string]$ToneClass = 'warn'
    )

    if ([string]::IsNullOrWhiteSpace($Department)) {
        return ''
    }

    $iconKey = Get-DepartmentIconKey $Department
    return '<span class="department-label"><span class="department-label__icon department-label__icon--{0}">{1}</span><span class="department-label__text">{2}</span></span>' -f $ToneClass, (Get-IconSvg $iconKey), (ConvertTo-HtmlEncoded $Department)
}

function Get-OpportunityToneClassForDepartment {
    param(
        [object[]]$Items,
        [string]$Department
    )

    foreach ($item in @($Items)) {
        if ([string]::IsNullOrWhiteSpace([string]$item.department)) {
            continue
        }

        if ([string]$item.department -eq $Department) {
            return Get-OpportunityToneClass ([string]$item.tone)
        }
    }

    return 'warn'
}

function ConvertTo-DepartmentSignalGridHtml {
    param(
        [object[]]$Items,
        [string]$LeadDepartment
    )

    $rows = [System.Collections.Generic.List[string]]::new()
    foreach ($item in @($Items)) {
        $department = [string]$item.department
        if ([string]::IsNullOrWhiteSpace($department)) {
            continue
        }

        $toneClass = Get-OpportunityToneClass ([string]$item.tone)
        $signal = [string]$item.opportunity_signal
        if ([string]::IsNullOrWhiteSpace($signal)) {
            $signal = [string]$item.rationale
        }

        $departmentHtml = ConvertTo-DepartmentLabelHtml -Department $department -ToneClass $toneClass
        $rows.Add(@"
      <div class="opportunity-signal opportunity-signal--$toneClass">
        $departmentHtml
        <p>$(ConvertTo-HtmlEncoded $signal)</p>
      </div>
"@) | Out-Null
    }

    if ($rows.Count -eq 0) {
        return ''
    }

    return @"
    <div class="opportunity-signal-grid">
$($rows -join "`n")
    </div>
"@
}

function ConvertTo-LeadOfferingHtml {
    param(
        [object]$LeadOffering,
        [object[]]$DepartmentItems
    )

    if ($null -eq $LeadOffering) {
        return ''
    }

    $name = [string]$LeadOffering.name
    $verdict = [string]$LeadOffering.verdict
    $leadDepartment = [string]$LeadOffering.lead_department
    $bestBuyer = [string]$LeadOffering.best_buyer
    $supporting = @($LeadOffering.supporting_departments | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    $whyThisLeads = @($LeadOffering.why_this_leads)
    $whyNotFirst = @($LeadOffering.why_not_first)
    $expectedOutcomes = @($LeadOffering.expected_outcomes)
    $leadToneClass = Get-OpportunityToneClassForDepartment -Items $DepartmentItems -Department $leadDepartment

    if ([string]::IsNullOrWhiteSpace($name) -and [string]::IsNullOrWhiteSpace($verdict)) {
        return ''
    }

    $supportHtml = ''
    if ($supporting.Count -gt 0) {
        $supportPills = $supporting | ForEach-Object {
            '<span class="opportunity-chip opportunity-chip--support">{0}</span>' -f (ConvertTo-HtmlEncoded ([string]$_))
        }
        $supportHtml = @"
      <div class="opportunity-support">
        <span class="eyebrow">Supporting teams</span>
        <div class="opportunity-support__pills">$($supportPills -join '')</div>
      </div>
"@
    }

    $bestBuyerHtml = ''
    if (-not [string]::IsNullOrWhiteSpace($bestBuyer)) {
        $bestBuyerHtml = '<p><strong>Best internal buyer:</strong> {0}</p>' -f (ConvertTo-HtmlEncoded $bestBuyer)
    }

    $leadDepartmentHtml = ''
    if (-not [string]::IsNullOrWhiteSpace($leadDepartment)) {
        $leadDepartmentLabel = ConvertTo-DepartmentLabelHtml -Department $leadDepartment -ToneClass $leadToneClass
        $leadDepartmentHtml = '<div class="opportunity-lead__department"><strong>Lead department:</strong> {0}</div>' -f $leadDepartmentLabel
    }

    return @"
    <div class="opportunity-lead">
      <div class="opportunity-lead__hero">
        <div class="opportunity-lead__head">
          <span class="eyebrow">Recommended lead offering</span>
          <h3>$(ConvertTo-HtmlEncoded $name)</h3>
        </div>
        <div class="opportunity-lead__meta">
          <span class="opportunity-chip opportunity-chip--lead opportunity-chip--$leadToneClass">Lead: $(ConvertTo-HtmlEncoded $leadDepartment)</span>
        </div>
      </div>
      <p class="opportunity-lead__verdict">$(ConvertTo-HtmlEncoded $verdict)</p>
      $leadDepartmentHtml
      $bestBuyerHtml
      $supportHtml
      <div class="opportunity-lead__grid">
        <div class="opportunity-lead__panel">
          <span class="eyebrow">Why this should lead</span>
$(ConvertTo-ListHtml $whyThisLeads)
        </div>
        <div class="opportunity-lead__panel">
          <span class="eyebrow">Why other departments should not lead first</span>
$(ConvertTo-ListHtml $whyNotFirst)
        </div>
        <div class="opportunity-lead__panel">
          <span class="eyebrow">Expected outcomes</span>
$(ConvertTo-ListHtml $expectedOutcomes)
        </div>
      </div>
    </div>
"@
}

function ConvertTo-ClaimedPositioningTableHtml {
    param([object]$ClaimedPositioning)

    if ($null -eq $ClaimedPositioning) {
        return ''
    }

    $rows = @($ClaimedPositioning.rows)
    if (-not $rows -or $rows.Count -eq 0) {
        return ''
    }

    $introParts = @()
    if (-not [string]::IsNullOrWhiteSpace([string]$ClaimedPositioning.summary)) {
        $introParts += '<p><strong>Summary:</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$ClaimedPositioning.summary))
    }

    $verdict = $ClaimedPositioning.overall_verdict
    if ($null -ne $verdict) {
        if (-not [string]::IsNullOrWhiteSpace([string]$verdict.headline)) {
            $introParts += '<p><strong>Overall verdict:</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$verdict.headline))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$verdict.uniqueness_verdict)) {
            $introParts += '<p><strong>Unique enough?</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$verdict.uniqueness_verdict))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$verdict.who_for)) {
            $introParts += '<p><strong>Best fit:</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$verdict.who_for))
        }
    }

    $decoratedRows = foreach ($row in $rows) {
        [pscustomobject]@{
            claim_type_html = ConvertTo-ClaimSignalHtml -Text ([string]$row.claim_type) -IconKey ([string]$row.icon_key)
            claim_summary = [string]$row.claim_summary
            proof_points = [string]$row.proof_points
            proof_feedback = [string]$row.proof_feedback
        }
    }

    $tableHtml = ConvertTo-TableHtml $decoratedRows @(
        @{ header = 'Claim'; key = 'claim_type_html'; raw_html = $true },
        @{ header = 'Claim summary'; key = 'claim_summary' },
        @{ header = 'Proof points'; key = 'proof_points' },
        @{ header = 'Feedback on proof'; key = 'proof_feedback' }
    )

    if ([string]::IsNullOrWhiteSpace($tableHtml)) {
        return ($introParts -join "`n")
    }

    return "{0}`n{1}" -f (($introParts -join "`n")), $tableHtml
}

function ConvertTo-CardGridHtml {
    param([object[]]$Cards)

    $cardHtml = $Cards | ForEach-Object {
        @"
      <div class="card">
        <strong>$(ConvertTo-HtmlEncoded ([string]$_.title))</strong>
        $(ConvertTo-RichText ([string]$_.body))
      </div>
"@
    }

    return @"
    <div class="card-grid">
$($cardHtml -join "`n")
    </div>
"@
}

function ConvertTo-ChartNumber {
    param([object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [decimal] -or $Value -is [float]) {
        return [double]$Value
    }

    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }

    $normalized = $text.Trim() -replace '[^0-9\.\-]', ''
    $parsed = 0.0
    if ([double]::TryParse($normalized, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
        return $parsed
    }

    return $null
}

function Get-ChartToneClass {
    param([string]$Tone)

    $normalized = ([string]$Tone).Trim().ToLowerInvariant()
    if ($normalized -eq 'teal') { return 'teal' }
    if ($normalized -eq 'amber' -or $normalized -eq 'warn') { return 'amber' }
    return 'blue'
}

function ConvertTo-SimpleBarChartsHtml {
    param(
        [object[]]$Charts,
        [string]$SectionClass = ''
    )

    if (-not $Charts -or $Charts.Count -eq 0) {
        return ''
    }

    $chartHtml = @()
    $newline = [Environment]::NewLine
    foreach ($chart in $Charts) {
        $series = @($chart.series | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.label) })
        if ($series.Count -eq 0) {
            continue
        }

        $numericValues = @()
        foreach ($item in $series) {
            $value = ConvertTo-ChartNumber $item.value
            if ($null -ne $value) {
                $numericValues += $value
            }
        }

        if ($numericValues.Count -eq 0) {
            continue
        }

        $maxValue = ($numericValues | Measure-Object -Maximum).Maximum
        if ($maxValue -le 0) {
            $maxValue = 1
        }

        $rows = @()
        foreach ($item in $series) {
            $value = ConvertTo-ChartNumber $item.value
            if ($null -eq $value) {
                continue
            }

            $displayValue = [string]$item.display_value
            if ([string]::IsNullOrWhiteSpace($displayValue)) {
                $suffix = [string]$chart.value_suffix
                if ($value -eq [math]::Floor($value)) {
                    $displayValue = '{0}{1}' -f ([int]$value), $suffix
                }
                else {
                    $displayValue = '{0:0.#}{1}' -f $value, $suffix
                }
            }

            $widthPct = [math]::Round(([math]::Max($value, 0) / $maxValue) * 100, 1)
            $toneClass = Get-ChartToneClass ([string]$item.tone)
            $noteHtml = ''
            if (-not [string]::IsNullOrWhiteSpace([string]$item.note)) {
                $noteHtml = '<div class="chart-note">{0}</div>' -f (ConvertTo-HtmlEncoded ([string]$item.note))
            }

            $rowParts = @(
                '      <div class="chart-row">'
                '        <div class="chart-label">{0}</div>' -f (ConvertTo-HtmlEncoded ([string]$item.label))
                '        <div class="chart-bar-track">'
                '          <div class="chart-bar-fill chart-bar-fill--{0}" style="width: {1}%"></div>' -f $toneClass, $widthPct
                '        </div>'
                '        <div class="chart-value">{0}</div>' -f (ConvertTo-HtmlEncoded $displayValue)
                '      </div>'
            )

            if ($noteHtml) {
                $rowParts += "      $noteHtml"
            }

            $rows += ($rowParts -join $newline)
        }

        if ($rows.Count -eq 0) {
            continue
        }

        $subtitleHtml = ''
        if (-not [string]::IsNullOrWhiteSpace([string]$chart.subtitle)) {
            $subtitleHtml = '<p class="chart-subtitle">{0}</p>' -f (ConvertTo-HtmlEncoded ([string]$chart.subtitle))
        }

        $cardParts = @(
            '    <div class="chart-card {0}">' -f (ConvertTo-HtmlEncoded $SectionClass)
            '      <div class="chart-card__header">'
            '        <h4>{0}</h4>' -f (ConvertTo-HtmlEncoded ([string]$chart.title))
        )

        if ($subtitleHtml) {
            $cardParts += "        $subtitleHtml"
        }

        $cardParts += @(
            '      </div>'
            '      <div class="chart-card__rows">'
            ($rows -join $newline)
            '      </div>'
            '    </div>'
        )

        $chartHtml += ($cardParts -join $newline)
    }

    if ($chartHtml.Count -eq 0) {
        return ''
    }

    $gridHtml = @(
        '  <div class="chart-grid {0}">' -f (ConvertTo-HtmlEncoded $SectionClass)
        ($chartHtml -join $newline)
        '  </div>'
    ) -join $newline

    return $gridHtml
}

function Get-Initials {
    param(
        [string]$Text,
        [int]$Limit = 2
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return '?'
    }

    $tokens = @([regex]::Matches($Text.ToUpperInvariant(), '[A-Z0-9]+') | ForEach-Object { $_.Value })
    if (-not $tokens -or $tokens.Count -eq 0) {
        return ($Text.Trim().Substring(0, [Math]::Min($Text.Trim().Length, $Limit))).ToUpperInvariant()
    }

    if ($tokens.Count -eq 1) {
        return $tokens[0].Substring(0, [Math]::Min($tokens[0].Length, $Limit))
    }

    return (($tokens | Select-Object -First $Limit | ForEach-Object { $_.Substring(0, 1) }) -join '')
}

function Get-IconSvg {
    param([string]$Key)

    switch ($Key) {
        'snapshot' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19V7m7 12V5m7 14v-8" /></svg>' }
        'summary' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h10M4 17h7" /></svg>' }
        'messaging' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8.5a3.5 3.5 0 0 1 3.5-3.5h7A3.5 3.5 0 0 1 19 8.5v4A3.5 3.5 0 0 1 15.5 16H11l-4 3v-3.2A3.5 3.5 0 0 1 5 12.5z" /></svg>' }
        'competitive' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 4 7l5 3 3-5 3 5 5-3-3 10z" /></svg>' }
        'seo' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="5.5" /><path d="m16 16 4 4" /></svg>' }
        'reputation' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.5-4.8-2.5-4.8 2.5.9-5.5-3.9-3.8 5.4-.8z" /></svg>' }
        'content' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5.5h8.5L18 8v10.5H7z" /><path d="M15.5 5.5V8H18M9.5 12h6M9.5 15h5" /></svg>' }
        'opportunities' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12" /><path d="m8.5 8.5 3.5-5.5 3.5 5.5" /><path d="M5 19h14" /></svg>' }
        'appendix' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5.5h8.5L18 8v10.5H7z" /><path d="M9.5 12h5M9.5 15h5M9.5 9h3" /></svg>' }
        'one-liner' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h14M5 12h9M5 16h6" /></svg>' }
        'fixes' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14.5 6.5 3 3M7 17l2.5-.5 8-8a1.4 1.4 0 0 0-2-2l-8 8z" /></svg>' }
        'patterns' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h5v5H5zM14 7h5v5h-5zM5 16h5v3H5zM14 16h5v3h-5z" /></svg>' }
        'issues' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 9v4M12 17h.01" /><path d="M10.3 4.8 4.9 14.2A2 2 0 0 0 6.6 17h10.8a2 2 0 0 0 1.7-2.8l-5.4-9.4a2 2 0 0 0-3.4 0Z" /></svg>' }
        'news' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 7h9v10H6z" /><path d="M15 9h3v8a2 2 0 0 1-2 2H8" /><path d="M8 10h5M8 13h5M8 16h3" /></svg>' }
        'actions' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4 10-10" /></svg>' }
        'ideas' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18h6M10 21h4M8.5 14.5A5.5 5.5 0 1 1 15.5 14.5c-.8.7-1.3 1.4-1.5 2.5h-4c-.2-1.1-.7-1.8-1.5-2.5Z" /></svg>' }
        'sources' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 6h10M7 12h10M7 18h6" /></svg>' }
        'missing' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path d="M12 8v5M12 16h.01" /></svg>' }
        'notes' { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5.5h8.5L18 8v10.5H7z" /><path d="M9.5 12h5M9.5 15h5" /></svg>' }
        default { return '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7" /></svg>' }
    }
}

function ConvertTo-HeadingHtml {
    param(
        [string]$Level,
        [string]$Text,
        [string]$IconKey,
        [string]$Class = 'section-heading',
        [string]$Id
    )

    $idAttribute = ''
    if (-not [string]::IsNullOrWhiteSpace($Id)) {
        $idAttribute = ' id="{0}"' -f (ConvertTo-HtmlEncoded $Id)
    }

    return '<{0} class="{1}"{4}><span class="heading-icon">{2}</span><span>{3}</span></{0}>' -f (ConvertTo-HtmlEncoded $Level), (ConvertTo-HtmlEncoded $Class), (Get-IconSvg $IconKey), (ConvertTo-HtmlEncoded $Text), $idAttribute
}

function ConvertTo-PillHtml {
    param([object[]]$Pills)

    $items = $Pills | ForEach-Object {
        '<span class="pill {0}">{1}</span>' -f (ConvertTo-HtmlEncoded ([string]$_.tone)), (ConvertTo-HtmlEncoded ([string]$_.label))
    }

    return ($items -join '')
}

function ConvertTo-TimelineHtml {
    param([object[]]$Timelines)

    $steps = $Timelines | ForEach-Object {
        @(
            '      <div class="timeline-step">'
            '        <h3>{0}</h3>' -f (ConvertTo-HtmlEncoded ([string]$_.title))
            (ConvertTo-ListHtml @($_.items))
            '      </div>'
        ) -join [Environment]::NewLine
    }

    $timelineHtml = @(
        '    <div class="timeline">'
        ($steps -join [Environment]::NewLine)
        '    </div>'
    ) -join [Environment]::NewLine

    return $timelineHtml
}

function ConvertTo-BrandLogoHtml {
    param([object]$Brand)

    $name = [string]$Brand.name
    $logoUrl = Resolve-BrandBadgeAssetUrl $Brand

    if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
        return '<div class="brand-logo-slot"><img src="{0}" alt="{1} logo" loading="eager"></div>' -f (ConvertTo-HtmlEncoded $logoUrl), (ConvertTo-HtmlEncoded $name)
    }

    return '<div class="brand-logo-slot brand-logo-slot--fallback" aria-hidden="true"><span>{0}</span></div>' -f (ConvertTo-HtmlEncoded (Get-Initials -Text $name))
}

function ConvertTo-PublisherLogoHtml {
    param([object]$Item)

    $sourceName = [string]$Item.source
    $url = Get-SafeHref ([string]$Item.url)
    $logoUrl = Resolve-PublisherBadgeAssetUrl $Item
    if ([string]::IsNullOrWhiteSpace($url)) {
        if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
            return '<div class="publisher-badge"><img src="{0}" alt="{1}" loading="lazy"></div>' -f (ConvertTo-HtmlEncoded $logoUrl), (ConvertTo-HtmlEncoded $sourceName)
        }
        return '<div class="publisher-badge"><span>{0}</span></div>' -f (ConvertTo-HtmlEncoded $sourceName)
    }

    if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
        return '<a class="publisher-link" href="{0}" title="{1}"><div class="publisher-badge"><img src="{2}" alt="{1}" loading="lazy"></div></a>' -f (ConvertTo-HtmlEncoded $url), (ConvertTo-HtmlEncoded $sourceName), (ConvertTo-HtmlEncoded $logoUrl)
    }

    return '<a class="publisher-link" href="{0}" title="{1}"><div class="publisher-badge"><span>{1}</span></div></a>' -f (ConvertTo-HtmlEncoded $url), (ConvertTo-HtmlEncoded $sourceName)
}
function ConvertTo-CompetitorBadgeHtml {
    param(
        [string]$Name,
        [string]$Website
    )

    $Website = Get-SafeHref $Website
    $logoUrl = Resolve-CompetitorBadgeAssetUrl -Name $Name -Website $Website
    if ([string]::IsNullOrWhiteSpace($Website)) {
        if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
            return '<div class="competitor-badge"><img src="{0}" alt="{1} logo" loading="lazy"></div>' -f (ConvertTo-HtmlEncoded $logoUrl), (ConvertTo-HtmlEncoded $Name)
        }
        return '<div class="competitor-badge competitor-badge--fallback" aria-hidden="true"><span>{0}</span></div>' -f (ConvertTo-HtmlEncoded (Get-Initials -Text $Name))
    }

    if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
        return '<a class="competitor-badge competitor-badge--link" href="{0}" title="{1}"><img src="{2}" alt="{1} logo" loading="lazy"></a>' -f (ConvertTo-HtmlEncoded $Website), (ConvertTo-HtmlEncoded $Name), (ConvertTo-HtmlEncoded $logoUrl)
    }

    return '<a class="competitor-badge competitor-badge--link competitor-badge--fallback" href="{0}" title="{1}"><span>{2}</span></a>' -f (ConvertTo-HtmlEncoded $Website), (ConvertTo-HtmlEncoded $Name), (ConvertTo-HtmlEncoded (Get-Initials -Text $Name))
}


function ConvertTo-TocHtml {
    param([object[]]$Items)

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $listItems = $Items | ForEach-Object {
        '<li><a href="#{0}">{1}</a></li>' -f (ConvertTo-HtmlEncoded ([string]$_.id)), (ConvertTo-HtmlEncoded ([string]$_.label))
    }

    return @"
    <nav class="toc" id="contents" aria-label="Table of contents">
      <div class="toc-eyebrow">Contents</div>
      <ul>
$($listItems -join "`n")
      </ul>
    </nav>
"@
}

function ConvertTo-BackToContentsHtml {
    return '<div class="section-return"><a href="#contents">Back to contents</a></div>'
}

function ConvertTo-CompetitorCellHtml {
    param([object]$Item)

    $name = [string]$Item.competitor
    $website = Get-SafeHref ([string]$Item.website)
    $logoUrl = @(
        (Resolve-AssetUrl ([string]$Item.logo_url)),
        (Resolve-AssetUrl ([string]$Item.competitor_logo_url)),
        (Resolve-AssetUrl ([string]$Item.badge_url)),
        (Resolve-AssetUrl ([string]$Item.mark_url))
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($logoUrl)) {
        $logoUrl = Resolve-CompetitorBadgeAssetUrl -Name $name -Website $website
    }
    $badgeHtml = ''
    $siteHtml = ''

    if ([string]::IsNullOrWhiteSpace($website)) {
        if (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
            $badgeHtml = '<div class="competitor-badge"><img src="{0}" alt="{1} logo" loading="lazy"></div>' -f (ConvertTo-HtmlEncoded $logoUrl), (ConvertTo-HtmlEncoded $name)
        }
        else {
            $badgeHtml = '<div class="competitor-badge competitor-badge--fallback" aria-hidden="true"><span>{0}</span></div>' -f (ConvertTo-HtmlEncoded (Get-Initials -Text $name))
        }
    }
    elseif (-not [string]::IsNullOrWhiteSpace($logoUrl)) {
        $badgeHtml = '<a class="competitor-badge competitor-badge--link" href="{0}" title="{1}"><img src="{2}" alt="{1} logo" loading="lazy"></a>' -f (ConvertTo-HtmlEncoded $website), (ConvertTo-HtmlEncoded $name), (ConvertTo-HtmlEncoded $logoUrl)
    }
    else {
        $badgeHtml = '<a class="competitor-badge competitor-badge--link competitor-badge--fallback" href="{0}" title="{1}"><span>{2}</span></a>' -f (ConvertTo-HtmlEncoded $website), (ConvertTo-HtmlEncoded $name), (ConvertTo-HtmlEncoded (Get-Initials -Text $name))
    }

    if (-not [string]::IsNullOrWhiteSpace($website)) {
        $siteHtml = '<a class="competitor-site" href="{0}">{1}</a>' -f (ConvertTo-HtmlEncoded $website), (ConvertTo-HtmlEncoded ($website -replace '^https?://', '' -replace '/$',''))
    }

    return @"
<div class="competitor-cell">
  $badgeHtml
  <div class="competitor-copy">
    <span class="competitor-name">$(ConvertTo-HtmlEncoded $name)</span>
    $siteHtml
  </div>
</div>
"@
}

function ConvertTo-NewsTableHtml {
    param([object[]]$Items)

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $rows = foreach ($item in $Items) {
        $subscores = @()
        if ($item.influence_subscores) {
            foreach ($entry in @(
                @{ key = 'source_authority'; label = 'authority' },
                @{ key = 'buyer_relevance'; label = 'buyer' },
                @{ key = 'reputation_risk_or_opportunity'; label = 'impact' },
                @{ key = 'evidence_quality'; label = 'evidence' },
                @{ key = 'novelty'; label = 'novelty' },
                @{ key = 'recency'; label = 'recency' }
            )) {
                $value = $item.influence_subscores.($entry.key)
                if ($null -ne $value -and "$value".Trim()) {
                    $subscores += "$($entry.label) $value"
                }
            }
        }
        [pscustomobject]@{
            date = [string]$item.date
            influence = [string]$item.influence_score
            headline = [string]$item.headline
            source = (ConvertTo-PublisherLogoHtml $item)
            rank_reason = if ($item.rank_reason) { [string]$item.rank_reason } else { [string]$item.why_it_matters }
            score_basis = ($subscores -join ', ')
            why_it_matters = [string]$item.why_it_matters
        }
    }

    return ConvertTo-TableHtml -Rows $rows -Columns @(
        @{ header = 'Date'; key = 'date' },
        @{ header = 'Influence'; key = 'influence' },
        @{ header = 'Headline'; key = 'headline' },
        @{ header = 'Source'; key = 'source'; raw_html = $true },
        @{ header = 'Why it ranked'; key = 'rank_reason' },
        @{ header = 'Score basis'; key = 'score_basis' },
        @{ header = 'Why it mattered'; key = 'why_it_matters' }
    )
}

function ConvertTo-CreativeCampaignIdeasHtml {
    param([object[]]$Ideas)

    if (-not $Ideas -or $Ideas.Count -eq 0) {
        return ''
    }

    function ConvertTo-ActivationPlanHtml {
        param([object]$ActivationPlan)

        if ($null -eq $ActivationPlan) {
            return ''
        }

        $items = @($ActivationPlan.order_of_precedence | Where-Object { $_ })
        if ($items.Count -eq 0) {
            return ''
        }

        $itemHtml = foreach ($item in $items) {
            $name = [string]$item.name
            if ([string]::IsNullOrWhiteSpace($name)) {
                continue
            }

            $parts = @()
            if (-not [string]::IsNullOrWhiteSpace([string]$item.primary_goal)) {
                $parts += '<p><strong>Why first</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$item.primary_goal))
            }

            $contains = @($item.contains | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
            if ($contains.Count -gt 0) {
                $containsHtml = foreach ($entry in $contains) {
                    '<li>{0}</li>' -f (ConvertTo-HtmlEncoded ([string]$entry))
                }
                $parts += '<p><strong>Should contain</strong></p><ul>{0}</ul>' -f ($containsHtml -join '')
            }

            $inputsNeeded = @($item.inputs_needed | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
            if ($inputsNeeded.Count -gt 0) {
                $inputHtml = foreach ($entry in $inputsNeeded) {
                    '<li>{0}</li>' -f (ConvertTo-HtmlEncoded ([string]$entry))
                }
                $parts += '<p><strong>Needs as input</strong></p><ul>{0}</ul>' -f ($inputHtml -join '')
            }

            if ($parts.Count -eq 0) {
                continue
            }

            @"
<li class="idea-activation-plan__item">
  <div class="idea-activation-plan__title">$(ConvertTo-HtmlEncoded $name)</div>
  $(($parts -join "`n"))
</li>
"@
        }

        if (-not $itemHtml -or $itemHtml.Count -eq 0) {
            return ''
        }

        return @"
<div class="idea-activation-plan">
  <p><strong>Activation sequence</strong></p>
  <ol class="idea-activation-plan__list">
    $(($itemHtml -join "`n"))
  </ol>
</div>
"@
    }

    $cards = foreach ($idea in $Ideas) {
        $title = [string]$idea.title
        if ([string]::IsNullOrWhiteSpace($title)) {
            continue
        }

        $channels = @($idea.channels | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        $visualUrl = Resolve-AssetUrl ([string]$idea.illustration_url)
        $visualHtml = ''
        if (-not [string]::IsNullOrWhiteSpace($visualUrl)) {
            $visualHtml = '<div class="idea-card__visual"><img src="{0}" alt="{1} illustration"></div>' -f $visualUrl, (ConvertTo-HtmlEncoded $title)
        }
        else {
            $fallbackMonogram = ((($title -replace '[^A-Za-z0-9 ]', '').Trim() -split '\s+' | Where-Object { $_ }) | Select-Object -First 2 | ForEach-Object { $_.Substring(0, 1).ToUpperInvariant() }) -join ''
            if ([string]::IsNullOrWhiteSpace($fallbackMonogram)) {
                $fallbackMonogram = 'CI'
            }
            $visualHtml = '<div class="idea-card__visual idea-card__visual--fallback"><span>{0}</span></div>' -f (ConvertTo-HtmlEncoded $fallbackMonogram)
        }

        $channelHtml = ''
        if ($channels.Count -gt 0) {
            $channelBadges = foreach ($channel in $channels) {
                '<span class="idea-card__channel">{0}</span>' -f (ConvertTo-HtmlEncoded ([string]$channel))
            }
            $channelHtml = '<div class="idea-card__channels">{0}</div>' -f ($channelBadges -join '')
        }

        $bodyParts = @()
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.concept)) {
            $bodyParts += '<p><strong>Concept</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.concept))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.activation)) {
            $bodyParts += '<p><strong>Activation</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.activation))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.addresses)) {
            $bodyParts += '<p><strong>Addresses</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.addresses))
        }
        $activationPlanHtml = ConvertTo-ActivationPlanHtml $idea.activation_plan
        if (-not [string]::IsNullOrWhiteSpace($activationPlanHtml)) {
            $bodyParts += $activationPlanHtml
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.why_it_fits)) {
            $bodyParts += '<p><strong>Why it fits</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.why_it_fits))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.press_angle)) {
            $bodyParts += '<p><strong>Press angle</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.press_angle))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.why_it_will_work)) {
            $bodyParts += '<p><strong>Why it will work</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.why_it_will_work))
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$idea.intended_effect)) {
            $bodyParts += '<p class="idea-card__effect"><strong>Intended effect</strong> {0}</p>' -f (ConvertTo-HtmlEncoded ([string]$idea.intended_effect))
        }

        @"
<article class="idea-card">
  $visualHtml
  <div class="idea-card__body">
    <div class="idea-card__header">
      <div class="idea-card__eyebrow">Creative campaign idea</div>
      <h3>$(ConvertTo-HtmlEncoded $title)</h3>
    </div>
    <div class="idea-card__copy">
      $(($bodyParts -join "`n"))
    </div>
    $channelHtml
  </div>
</article>
"@
    }

    if (-not $cards -or $cards.Count -eq 0) {
        return ''
    }

    return "<div class=""idea-grid"">$($cards -join "`n")</div>"
}

function Get-LinkedInIconSvg {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.8 8.5v8.7M6.8 5.8h.01M10.5 17.2V8.5h4.1c2.1 0 3.4 1.4 3.4 3.8v4.9M10.5 12.2c0-2.3 1.4-3.7 3.3-3.7" /></svg>'
}

function Get-XIconSvg {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>'
}

function Get-BlueskyIconSvg {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7.5c1.8 1.4 3.1 3 5 5.5 1.9-2.5 3.2-4.1 5-5.5.7-.6 2-.9 2 1 0 1.1-.6 2.4-1.5 3.6-.8 1.1-1.9 2.2-3 2.9 1.2-.2 2.5 0 3.4.6 1 .6 1.4 1.6.7 2.5-.6.8-1.8 1.1-3 .9-1.4-.2-2.7-1-3.6-2.2-.9 1.2-2.2 2-3.6 2.2-1.2.2-2.4-.1-3-.9-.7-.9-.3-1.9.7-2.5.9-.6 2.2-.8 3.4-.6-1.1-.7-2.2-1.8-3-2.9C5.6 11 5 9.7 5 8.6c0-1.9 1.3-1.6 2-1.1Z" /></svg>'
}

function Get-ProfilePlatformMeta {
    param([string]$Platform, [string]$Url)

    $normalizedPlatform = ([string]$Platform).Trim().ToLowerInvariant()
    $normalizedUrl = ([string]$Url).Trim().ToLowerInvariant()

    if ($normalizedPlatform -eq 'linkedin' -or $normalizedUrl -match 'linkedin\.com') {
        return [pscustomobject]@{
            key = 'linkedin'
            label = 'LinkedIn'
            icon = Get-LinkedInIconSvg
        }
    }

    if ($normalizedPlatform -eq 'x' -or $normalizedPlatform -eq 'twitter' -or $normalizedUrl -match '(^https?://)?(www\.)?(x\.com|twitter\.com)/') {
        return [pscustomobject]@{
            key = 'x'
            label = 'X'
            icon = Get-XIconSvg
        }
    }

    if ($normalizedPlatform -eq 'bluesky' -or $normalizedPlatform -eq 'bsky' -or $normalizedUrl -match 'bsky\.app') {
        return [pscustomobject]@{
            key = 'bluesky'
            label = 'Bluesky'
            icon = Get-BlueskyIconSvg
        }
    }

    return [pscustomobject]@{
        key = 'profile'
        label = 'Profile'
        icon = Get-LinkedInIconSvg
    }
}

function ConvertTo-ProfileLinksHtml {
    param([object[]]$Profiles)

    if (-not $Profiles -or $Profiles.Count -eq 0) {
        return ''
    }

    $links = foreach ($profile in $Profiles) {
        $name = [string]$profile.name
        $url = Get-SafeHref ([string]$profile.url)

        if ([string]::IsNullOrWhiteSpace($name) -or [string]::IsNullOrWhiteSpace($url)) {
            continue
        }

        $meta = Get-ProfilePlatformMeta -Platform ([string]$profile.platform) -Url $url

        @"
        <a class="profile-link $($meta.key)-link" href="$(ConvertTo-HtmlEncoded $url)" target="_blank" rel="noreferrer noopener">
          <span class="profile-link-icon">$($meta.icon)</span>
          <span>$(ConvertTo-HtmlEncoded $name)</span>
          <span class="profile-link-platform">$(ConvertTo-HtmlEncoded $meta.label)</span>
        </a>
"@
    }

    if (-not $links) {
        return ''
    }

    return @"
        <div class="profile-links">
$($links -join "`n")
        </div>
"@
}
function ConvertTo-LabelValueGridHtml {
    param(
        [object[]]$Items,
        [switch]$Compact,
        [string]$GridClass = ''
    )

    if (-not $Items -or $Items.Count -eq 0) {
        return ''
    }

    $cardClass = if ($Compact) { 'card snapshot-card' } else { 'card' }
    $rows = $Items | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.value) } | ForEach-Object {
        $profiles = @($_.profiles) + @($_.linkedin_profiles)
        $profilesHtml = ConvertTo-ProfileLinksHtml $profiles
        @"
      <div class="$cardClass">
        <strong>$(ConvertTo-HtmlEncoded ([string]$_.label))</strong>
        $(ConvertTo-RichText ([string]$_.value))
$profilesHtml
      </div>
"@
    }

    if (-not $rows) {
        return ''
    }

    $classAttribute = 'card-grid'
    if (-not [string]::IsNullOrWhiteSpace($GridClass)) {
        $classAttribute = "$classAttribute $GridClass"
    }

    return @"
    <div class="$classAttribute">
$($rows -join "`n")
    </div>
"@
}
$data = Get-Content -LiteralPath $resolvedDataPath -Raw | ConvertFrom-Json
$template = Get-Content -LiteralPath $resolvedTemplatePath -Raw
$pageTitle = '{0} New Business Intelligence Report' -f $data.brand.name
$competitorList = ($data.cover.competitors | ForEach-Object { [string]$_ }) -join ', '
$assumptionsHtml = ($data.cover.assumptions | ForEach-Object { [string]$_ }) -join ' '
$safeBrandWebsite = Get-SafeHref ([string]$data.brand.website)
$brandWebsiteLabel = ConvertTo-HtmlEncoded (([string]$data.brand.website) -replace '^https?://', '' -replace '/$', '')
$brandWebsiteHtml = $brandWebsiteLabel
if (-not [string]::IsNullOrWhiteSpace($safeBrandWebsite)) {
    $brandWebsiteHtml = '<a href="{0}">{1}</a>' -f (ConvertTo-HtmlEncoded $safeBrandWebsite), $brandWebsiteLabel
}
$competitiveTableRows = @($data.competitive_landscape.table | ForEach-Object {
    [pscustomobject]@{
        competitor = (ConvertTo-CompetitorCellHtml $_)
        why_it_matters = [string]$_.why_it_matters
        positioning_pattern = [string]$_.positioning_pattern
        implication = [string]$_.implication
    }
})
$tocItems = @(
    [pscustomobject]@{ id = 'company-snapshot'; label = 'Company Snapshot' }
    [pscustomobject]@{ id = 'executive-summary'; label = 'Executive Summary' }
    [pscustomobject]@{ id = 'agency-opportunity'; label = 'Archetype Opportunity Assessment' }
    [pscustomobject]@{ id = 'storybrand-messaging'; label = 'Messaging Assessment' }
    [pscustomobject]@{ id = 'usp-ksp-review'; label = 'USP and KSP Review' }
    [pscustomobject]@{ id = 'competitive-landscape'; label = 'Competitive Landscape' }
    [pscustomobject]@{ id = 'seo-audit'; label = 'SEO Audit' }
    [pscustomobject]@{ id = 'brand-reputation'; label = 'Brand Reputation Snapshot' }
    [pscustomobject]@{ id = 'content-strategy'; label = 'Content Strategy Recommendations' }
    [pscustomobject]@{ id = 'creative-campaign-ideas'; label = 'Creative Campaign Ideas' }
    [pscustomobject]@{ id = 'opportunities'; label = 'Opportunities' }
    [pscustomobject]@{ id = 'appendix'; label = 'Appendix' }
)

function Get-ReportBodyHtml {
    param(
        [object]$data,
        [object[]]$tocItems,
        [object[]]$competitiveTableRows,
        [string]$competitorList,
        [string]$assumptionsHtml,
        [string]$brandWebsiteHtml
    )

    return @"
    <section class="hero">
      <div class="hero-head">
        $(ConvertTo-BrandLogoHtml $data.brand)
        <div class="hero-copy">
          <div class="eyebrow">NewBizIntel</div>
          <h1>$(ConvertTo-HtmlEncoded ([string]$data.brand.name))</h1>
          $(ConvertTo-RichText ([string]$data.cover.summary))
        </div>
      </div>
      <div class="meta">
        <div><strong>Website</strong><br>$brandWebsiteHtml</div>
        <div><strong>Date</strong><br>$(ConvertTo-HtmlEncoded ([string]$data.brand.date))</div>
        <div><strong>Scope</strong><br>$(ConvertTo-HtmlEncoded ([string]$data.cover.scope))</div>
        <div><strong>Competitors analysed</strong><br>$(ConvertTo-HtmlEncoded $competitorList)</div>
      </div>
      <p class="note">$(ConvertTo-HtmlEncoded $assumptionsHtml)</p>
      <p>
        <span class="pill warn">$(ConvertTo-HtmlEncoded ([string]$data.report_meta.distribution))</span>
        <span class="pill good">$(ConvertTo-HtmlEncoded ([string]$data.report_meta.audience))</span>
      </p>
      <p class="note">$(ConvertTo-HtmlEncoded ([string]$data.report_meta.note))</p>

$(ConvertTo-TocHtml $tocItems)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Company Snapshot' -IconKey 'snapshot' -Id 'company-snapshot')
    $(ConvertTo-RichText ([string]$data.company_snapshot.summary))
$(ConvertTo-LabelValueGridHtml -Items @($data.company_snapshot.items) -Compact -GridClass 'snapshot-grid')
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Executive Summary' -IconKey 'summary' -Id 'executive-summary')
$(ConvertTo-CardGridHtml @($data.executive_summary.cards))
    <p><strong>Overall recommendation:</strong> $(ConvertTo-HtmlEncoded ([string]$data.executive_summary.overall_recommendation))</p>
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Archetype Opportunity Assessment' -IconKey 'opportunities' -Id 'agency-opportunity')
    <div class="score">
      <span class="eyebrow">Archetype fit score</span>
      <strong>$(ConvertTo-HtmlEncoded ([string]$data.agency_opportunity.score))</strong>
      $(ConvertTo-RichText ([string]$data.agency_opportunity.score_summary))
    </div>
    $(ConvertTo-RichText ([string]$data.agency_opportunity.summary))
$(ConvertTo-LeadOfferingHtml $data.agency_opportunity.lead_offering @($data.agency_opportunity.department_opportunity_map))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Department Opportunity Signals' -IconKey 'opportunities' -Class 'category-heading')
$(ConvertTo-DepartmentSignalGridHtml -Items @($data.agency_opportunity.department_opportunity_map) -LeadDepartment ([string]$data.agency_opportunity.lead_offering.lead_department))
$(ConvertTo-CardGridHtml @($data.agency_opportunity.cards))
  $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Most Likely Workstreams' -IconKey 'content' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.agency_opportunity.priority_workstreams))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Why Archetype Is Well Matched' -IconKey 'summary' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.agency_opportunity.archetype_advantages))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Messaging Assessment' -IconKey 'messaging' -Id 'storybrand-messaging')
$(ConvertTo-PublishedMessagingAssessmentHtml $data.storybrand.existing_messaging_assessment)
    <div class="score">
      <span class="eyebrow">Messaging Score</span>
      <strong>$(ConvertTo-HtmlEncoded ([string]$data.storybrand.score))</strong>
      $(ConvertTo-RichText ([string]$data.storybrand.score_summary))
    </div>
$(ConvertTo-CardGridHtml @($data.storybrand.cards))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Recommended One-Liner' -IconKey 'one-liner' -Class 'category-heading')
    <p><strong>$(ConvertTo-HtmlEncoded ([string]$data.storybrand.one_liner))</strong></p>
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Biggest Messaging Fixes' -IconKey 'fixes' -Class 'category-heading')
$(ConvertTo-RecommendationCardsHtml -Items @($data.storybrand.messaging_fixes) -Tone 'teal')
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Content Implications of the Messaging Findings' -IconKey 'content' -Class 'category-heading')
$(ConvertTo-RecommendationCardsHtml -Items @($data.storybrand.content_implications) -Tone 'gold')
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'USP and KSP Review' -IconKey 'competitive' -Id 'usp-ksp-review')
    <div class="score">
      <span class="eyebrow">USP and KSP score</span>
      <strong>$(ConvertTo-HtmlEncoded ([string]$data.usp_ksp_review.score))</strong>
      $(ConvertTo-RichText ([string]$data.usp_ksp_review.score_summary))
    </div>
    <p>This chapter tests whether the company has a genuinely differentiated offer, how well that position is proved, and which buyer context makes the offer feel most distinct.</p>
$(ConvertTo-ClaimedPositioningTableHtml $data.usp_ksp_review)
$(ConvertTo-BackToContentsHtml)
    </section>

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Competitive Landscape' -IconKey 'competitive' -Id 'competitive-landscape')
$(ConvertTo-TableHtml $competitiveTableRows @(
      @{ header = 'Competitor'; key = 'competitor'; raw_html = $true },
      @{ header = 'Why it matters'; key = 'why_it_matters' },
      @{ header = 'Positioning pattern'; key = 'positioning_pattern' },
      @{ header = 'Implication for the brand'; key = 'implication' }
  ) -TableClass 'competitive-table')
$(ConvertTo-SimpleBarChartsHtml -Charts @($data.competitive_landscape.charts) -SectionClass 'chart-grid--competitive')
      $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Why Each Competitor Matters' -IconKey 'competitive' -Class 'category-heading')
    $(ConvertTo-RichText ([string]$data.competitive_landscape.why_each_competitor_matters))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Messaging Patterns Across the Market' -IconKey 'patterns' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.competitive_landscape.messaging_patterns))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Content Patterns Across the Market' -IconKey 'content' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.competitive_landscape.content_patterns))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Areas Where the Brand Is Behind, Matched, or Ahead' -IconKey 'summary' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.competitive_landscape.status_summary))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'SEO Audit' -IconKey 'seo' -Id 'seo-audit')
$(ConvertTo-CardGridHtml @($data.seo_audit.cards))
      $(ConvertTo-HeadingHtml -Level 'h3' -Text 'SEMrush Evidence Behind the Diagnosis' -IconKey 'seo' -Class 'category-heading')
$(ConvertTo-CardGridHtml @($data.seo_audit.semrush_evidence))
$(ConvertTo-SimpleBarChartsHtml -Charts @($data.seo_audit.charts) -SectionClass 'chart-grid--seo')
      $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Priority Issues with Evidence, Reason, and Recommended Fix' -IconKey 'issues' -Class 'category-heading')
$(ConvertTo-TableHtml @($data.seo_audit.priority_issues) @(
      @{ header = 'Issue'; key = 'issue' },
    @{ header = 'Evidence'; key = 'evidence' },
    @{ header = 'Why it matters'; key = 'why_it_matters' },
    @{ header = 'Recommended fix'; key = 'recommended_fix' }
))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Content Implications of the SEO Findings' -IconKey 'content' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.seo_audit.content_implications))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Brand Reputation Snapshot' -IconKey 'reputation' -Id 'brand-reputation')
    <p>$(ConvertTo-PillHtml @($data.brand_reputation.pills))</p>
$(ConvertTo-CardGridHtml @($data.brand_reputation.cards))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Platform-Level Readout' -IconKey 'summary' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.brand_reputation.platform_readout))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Most Influential News Stories in the Last Six Months' -IconKey 'news' -Class 'category-heading')
$(ConvertTo-NewsTableHtml @($data.brand_reputation.influential_news))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Reputation Implications and Recommended Actions' -IconKey 'actions' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.brand_reputation.recommended_actions))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Content Implications of the Reputation Findings' -IconKey 'content' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.brand_reputation.content_implications))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Content Strategy Recommendations' -IconKey 'content' -Id 'content-strategy')
$(ConvertTo-CardGridHtml @($data.content_strategy.cards))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Priority Content Opportunities' -IconKey 'opportunities' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.content_strategy.priority_opportunities))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Example Article, Guide, or Asset Ideas' -IconKey 'ideas' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.content_strategy.example_ideas))
    $(ConvertTo-HeadingHtml -Level 'h3' -Text 'How This Strategy Responds to the Findings' -IconKey 'summary' -Class 'category-heading')
    $(ConvertTo-RichText ([string]$data.content_strategy.response_to_findings))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Creative Campaign Ideas' -IconKey 'ideas' -Id 'creative-campaign-ideas')
$(ConvertTo-CreativeCampaignIdeasHtml @($data.creative_campaign_ideas.ideas))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Opportunities' -IconKey 'opportunities' -Id 'opportunities')
$(ConvertTo-TimelineHtml @($data.opportunities.timelines))
$(ConvertTo-BackToContentsHtml)

    $(ConvertTo-HeadingHtml -Level 'h2' -Text 'Appendix' -IconKey 'appendix' -Id 'appendix')
    <div class="source-list">
      $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Sources Reviewed' -IconKey 'sources' -Class 'category-heading')
$(ConvertTo-SourceListHtml @($data.appendix.sources_reviewed))
      $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Missing Data' -IconKey 'missing' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.appendix.missing_data))
      $(ConvertTo-HeadingHtml -Level 'h3' -Text 'Assumptions and Confidence Notes' -IconKey 'notes' -Class 'category-heading')
$(ConvertTo-ListHtml @($data.appendix.assumptions_and_confidence_notes))
    </div>
$(ConvertTo-BackToContentsHtml)

    <p class="footer">$(ConvertTo-HtmlEncoded ([string]$data.footer_note))</p>
"@
}

$body = Get-ReportBodyHtml -data $data -tocItems $tocItems -competitiveTableRows $competitiveTableRows -competitorList $competitorList -assumptionsHtml $assumptionsHtml -brandWebsiteHtml $brandWebsiteHtml

$html = $template.Replace('{{PAGE_TITLE}}', $pageTitle).Replace('{{BODY_CONTENT}}', $body.Trim())
Assert-NoLocalFileUrisInHtml -Html $html
Set-Content -LiteralPath $OutputPath -Value $html -Encoding UTF8

[pscustomobject]@{
    data = $resolvedDataPath
    template = $resolvedTemplatePath
    html = (Resolve-Path -LiteralPath $OutputPath).Path
} | ConvertTo-Json -Compress








