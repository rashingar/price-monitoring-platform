param(
    [string]$ProductFactoryBaseUrl = "http://127.0.0.1:8000",
    [string]$EcommerceBaseUrl = "http://127.0.0.1:8001",
    [string]$WebBaseUrl = "http://127.0.0.1:5173",
    [switch]$SkipWeb,
    [switch]$Json,
    [int]$TimeoutSeconds = 5
)

$ErrorActionPreference = "Stop"

$results = New-Object System.Collections.Generic.List[object]
$timeout = [Math]::Max(1, $TimeoutSeconds)

function Join-Url {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][string]$Path
    )
    return "$($BaseUrl.TrimEnd('/'))/$($Path.TrimStart('/'))"
}

function New-SmokeResult {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Status,
        [string]$Url,
        [Nullable[int]]$HttpStatus,
        [Parameter(Mandatory = $true)][string]$Message,
        [int]$ElapsedMs = 0
    )
    return [pscustomobject]@{
        id = $Id
        label = $Label
        status = $Status
        url = $Url
        http_status = $HttpStatus
        message = $Message
        elapsed_ms = $ElapsedMs
    }
}

function Invoke-SmokeGet {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Url,
        [bool]$Required = $true,
        [scriptblock]$Validate
    )

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $httpStatus = $null
    $body = $null
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $timeout -UseBasicParsing
        $watch.Stop()
        $httpStatus = [int]$response.StatusCode
        $body = [string]$response.Content
    }
    catch {
        $watch.Stop()
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $httpStatus = [int]$_.Exception.Response.StatusCode
        }
        $status = if ($Required) { "failed" } else { "warn" }
        $message = if ($httpStatus) { "HTTP $httpStatus" } else { $_.Exception.Message }
        $script:results.Add((New-SmokeResult -Id $Id -Label $Label -Status $status -Url $Url -HttpStatus $httpStatus -Message $message -ElapsedMs ([int]$watch.ElapsedMilliseconds))) | Out-Null
        return $null
    }

    $payload = $null
    if ($body) {
        try {
            $payload = $body | ConvertFrom-Json
        }
        catch {
            $payload = $null
        }
    }

    $status = "passed"
    $message = "HTTP $httpStatus"
    if ($httpStatus -lt 200 -or $httpStatus -ge 300) {
        $status = if ($Required) { "failed" } else { "warn" }
    }

    if ($status -eq "passed" -and $Validate) {
        try {
            $validationMessage = & $Validate $payload $body
            if ($validationMessage) {
                $message = [string]$validationMessage
            }
        }
        catch {
            $status = if ($Required) { "failed" } else { "warn" }
            $message = $_.Exception.Message
        }
    }

    $script:results.Add((New-SmokeResult -Id $Id -Label $Label -Status $status -Url $Url -HttpStatus $httpStatus -Message $message -ElapsedMs ([int]$watch.ElapsedMilliseconds))) | Out-Null
    return $payload
}

function Add-SkippedCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Label,
        [string]$Url,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $script:results.Add((New-SmokeResult -Id $Id -Label $Label -Status "skipped" -Url $Url -HttpStatus $null -Message $Message -ElapsedMs 0)) | Out-Null
}

$productFactoryHealthUrl = Join-Url $ProductFactoryBaseUrl "/api/health"
$ecommerceHealthUrl = Join-Url $EcommerceBaseUrl "/api/health"
$priceMonitoringDbStatusUrl = Join-Url $EcommerceBaseUrl "/api/price-monitoring/db/status"
$catalogSummaryUrl = Join-Url $EcommerceBaseUrl "/api/catalog/summary"
$jobsUrl = Join-Url $EcommerceBaseUrl "/api/jobs?limit=1"
$latestCatalogUpdateUrl = Join-Url $EcommerceBaseUrl "/api/catalog/update-db/latest"
$vendorSourceSummaryUrl = Join-Url $EcommerceBaseUrl "/api/vendor-sources/source-urls/summary"

Invoke-SmokeGet -Id "product_factory_health" -Label "Product Factory API health" -Url $productFactoryHealthUrl -Validate {
    param($payload, $_body)
    if (-not $payload -or $payload.status -ne "ok") {
        throw "Health payload did not report status=ok."
    }
    return "status=ok"
} | Out-Null

Invoke-SmokeGet -Id "ecommerce_health" -Label "Ecommerce API health" -Url $ecommerceHealthUrl -Validate {
    param($payload, $_body)
    if (-not $payload -or $payload.status -ne "ok") {
        throw "Health payload did not report status=ok."
    }
    return "status=ok"
} | Out-Null

$dbStatus = Invoke-SmokeGet -Id "price_monitoring_db_status" -Label "Price Monitoring DB status endpoint" -Url $priceMonitoringDbStatusUrl -Validate {
    param($payload, $_body)
    if (-not $payload) {
        throw "DB status response was not JSON."
    }
    return "mode=$($payload.price_monitoring_database_mode)"
}

if ($null -ne $dbStatus) {
    $dbReadyMessage = "configured=$($dbStatus.configured), reachable=$($dbStatus.reachable), tables=$($dbStatus.required_tables_present)"
    if ($dbStatus.ready_for_catalog -and $dbStatus.ready_for_price_monitoring) {
        $results.Add((New-SmokeResult -Id "ecommerce_db_readiness" -Label "Ecommerce DB readiness" -Status "passed" -Url $priceMonitoringDbStatusUrl -HttpStatus 200 -Message $dbReadyMessage -ElapsedMs 0)) | Out-Null
    } else {
        $reasons = @($dbStatus.blocking_reasons) -join ", "
        if (-not $reasons) {
            $reasons = "database is not ready for catalog/price monitoring"
        }
        $results.Add((New-SmokeResult -Id "ecommerce_db_readiness" -Label "Ecommerce DB readiness" -Status "failed" -Url $priceMonitoringDbStatusUrl -HttpStatus 200 -Message $reasons -ElapsedMs 0)) | Out-Null
    }

    if ($dbStatus.alembic_up_to_date -eq $false) {
        $results.Add((New-SmokeResult -Id "alembic_at_head" -Label "Alembic status at head" -Status "failed" -Url $priceMonitoringDbStatusUrl -HttpStatus 200 -Message "alembic_current_revision=$($dbStatus.alembic_current_revision), alembic_head_revision=$($dbStatus.alembic_head_revision)" -ElapsedMs 0)) | Out-Null
    } elseif ($dbStatus.alembic_up_to_date -eq $true) {
        $results.Add((New-SmokeResult -Id "alembic_at_head" -Label "Alembic status at head" -Status "passed" -Url $priceMonitoringDbStatusUrl -HttpStatus 200 -Message "current revision matches head" -ElapsedMs 0)) | Out-Null
    } else {
        $results.Add((New-SmokeResult -Id "alembic_at_head" -Label "Alembic status at head" -Status "warn" -Url $priceMonitoringDbStatusUrl -HttpStatus 200 -Message "migration revision could not be confirmed by DB status endpoint" -ElapsedMs 0)) | Out-Null
    }
} else {
    $results.Add((New-SmokeResult -Id "ecommerce_db_readiness" -Label "Ecommerce DB readiness" -Status "failed" -Url $priceMonitoringDbStatusUrl -HttpStatus $null -Message "DB status endpoint did not respond." -ElapsedMs 0)) | Out-Null
    $results.Add((New-SmokeResult -Id "alembic_at_head" -Label "Alembic status at head" -Status "failed" -Url $priceMonitoringDbStatusUrl -HttpStatus $null -Message "DB status endpoint did not respond." -ElapsedMs 0)) | Out-Null
}

Invoke-SmokeGet -Id "catalog_summary" -Label "Catalog summary" -Url $catalogSummaryUrl -Validate {
    param($payload, $_body)
    if (-not $payload -or $null -eq $payload.total_products) {
        throw "Catalog summary did not include total_products."
    }
    return "total_products=$($payload.total_products)"
} | Out-Null

Invoke-SmokeGet -Id "durable_jobs_api" -Label "Durable jobs API" -Url $jobsUrl -Validate {
    param($payload, $_body)
    if (-not $payload -or $null -eq $payload.items) {
        throw "Durable jobs response did not include items."
    }
    return "items=$(@($payload.items).Count)"
} | Out-Null

Invoke-SmokeGet -Id "latest_catalog_update_job" -Label "Latest catalog update job" -Url $latestCatalogUpdateUrl -Validate {
    param($_payload, $_body)
    return "endpoint responded"
} | Out-Null

Invoke-SmokeGet -Id "vendor_sources_summary" -Label "Vendor Sources summary" -Url $vendorSourceSummaryUrl -Validate {
    param($payload, $_body)
    if (-not $payload) {
        throw "Vendor Sources summary response was not JSON."
    }
    return "summary responded"
} | Out-Null

if ($SkipWeb) {
    Add-SkippedCheck -Id "web_dev_server" -Label "Web dev server" -Url $WebBaseUrl -Message "Skipped by -SkipWeb."
} else {
    Invoke-SmokeGet -Id "web_dev_server" -Label "Web dev server" -Url $WebBaseUrl -Required $false -Validate {
        param($_payload, $body)
        if ([string]::IsNullOrWhiteSpace($body)) {
            throw "Web server responded with an empty body."
        }
        return "web server responded"
    } | Out-Null
}

if ($Json) {
    $results | ConvertTo-Json -Depth 6
} else {
    Write-Host ""
    Write-Host "Operator smoke check"
    Write-Host "This script only calls read/status endpoints. It does not run OpenCart export, scraping, capture, or fetch workflows."
    Write-Host ""
    $results |
        Select-Object `
            @{Name = "Check"; Expression = { $_.label } },
            @{Name = "Status"; Expression = { $_.status } },
            @{Name = "HTTP"; Expression = { if ($null -eq $_.http_status) { "" } else { $_.http_status } } },
            @{Name = "Message"; Expression = { $_.message } } |
        Format-Table -AutoSize
}

$failedRequired = @($results | Where-Object { $_.status -eq "failed" })
if ($failedRequired.Count -gt 0) {
    exit 1
}

exit 0
