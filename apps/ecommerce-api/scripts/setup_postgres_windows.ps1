param(
    [Alias("Host")]
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$Database = "ecommerce",
    [string]$AppUser = "ecommerce",
    [string]$AppPassword = "ecommerce",
    [string]$AdminUser = "postgres",
    [switch]$PersistUserEnv,
    [switch]$WriteDotEnv,
    [switch]$Force,
    [switch]$ResetAppUserPassword
)

$ErrorActionPreference = "Stop"

function Quote-SqlLiteral([string]$Value) {
    return "'" + ($Value -replace "'", "''") + "'"
}

function Quote-SqlIdentifier([string]$Value) {
    return '"' + ($Value -replace '"', '""') + '"'
}

function Invoke-PsqlText([string]$DatabaseName, [string]$Sql) {
    $Sql | & psql -h $HostName -p $Port -U $AdminUser -d $DatabaseName -v ON_ERROR_STOP=1 -q
    if ($LASTEXITCODE -ne 0) {
        throw "psql command failed."
    }
}

function Invoke-PsqlScalar([string]$DatabaseName, [string]$Sql) {
    $result = $Sql | & psql -h $HostName -p $Port -U $AdminUser -d $DatabaseName -v ON_ERROR_STOP=1 -At -q
    if ($LASTEXITCODE -ne 0) {
        throw "psql command failed."
    }
    return (($result | Select-Object -First 1) -as [string]).Trim()
}

function ConvertTo-PlainText([securestring]$SecureValue) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    throw "psql is not available on PATH. Install native Windows PostgreSQL or add PostgreSQL bin to PATH."
}

$previousPgPassword = $env:PGPASSWORD
$setPgPassword = $false
if (-not $env:PGPASSWORD) {
    $secureAdminPassword = Read-Host "Enter PostgreSQL admin password for '$AdminUser'" -AsSecureString
    $env:PGPASSWORD = ConvertTo-PlainText $secureAdminPassword
    $setPgPassword = $true
}

try {
    $appUserLiteral = Quote-SqlLiteral $AppUser
    $appUserIdentifier = Quote-SqlIdentifier $AppUser
    $databaseLiteral = Quote-SqlLiteral $Database
    $databaseIdentifier = Quote-SqlIdentifier $Database
    $appPasswordLiteral = Quote-SqlLiteral $AppPassword

    $roleExists = Invoke-PsqlScalar "postgres" "select 1 from pg_roles where rolname = $appUserLiteral;"
    if ($roleExists -ne "1") {
        Invoke-PsqlText "postgres" "create user $appUserIdentifier with password $appPasswordLiteral;"
        Write-Host "Created application role '$AppUser'."
    }
    else {
        Write-Host "Application role '$AppUser' already exists."
        if ($ResetAppUserPassword) {
            Invoke-PsqlText "postgres" "alter user $appUserIdentifier with password $appPasswordLiteral;"
            Write-Host "Reset application role password because -ResetAppUserPassword was supplied."
        }
    }

    $databaseExists = Invoke-PsqlScalar "postgres" "select 1 from pg_database where datname = $databaseLiteral;"
    if ($databaseExists -ne "1") {
        Invoke-PsqlText "postgres" "create database $databaseIdentifier owner $appUserIdentifier;"
        Write-Host "Created database '$Database'."
    }
    else {
        Write-Host "Database '$Database' already exists."
    }

    Invoke-PsqlText "postgres" "grant all privileges on database $databaseIdentifier to $appUserIdentifier;"
    Invoke-PsqlText $Database "grant all on schema public to $appUserIdentifier;"

    $rawUrl = "postgresql+psycopg://${AppUser}:${AppPassword}@${HostName}:${Port}/${Database}"
    $sanitizedUrl = "postgresql+psycopg://${AppUser}:***@${HostName}:${Port}/${Database}"

    Write-Host ""
    Write-Host "Sanitized connection URL:"
    Write-Host $sanitizedUrl

    if ($PersistUserEnv) {
        [Environment]::SetEnvironmentVariable("ECOMMERCE_DATABASE_URL", $rawUrl, "User")
        Write-Host "Persisted ECOMMERCE_DATABASE_URL for the current Windows user."
        Write-Host "Open a new PowerShell terminal before running commands that use the persisted variable."
    }
    else {
        Write-Host "Set ECOMMERCE_DATABASE_URL in the current terminal before running migrations."
        Write-Host "Do not paste real credentials into shared logs or tickets."
    }

    if ($WriteDotEnv) {
        $envPath = Join-Path (Get-Location) ".env"
        $examplePath = Join-Path (Get-Location) ".env.example"
        if ((Test-Path $envPath) -and -not $Force) {
            Write-Host ".env already exists. Re-run with -Force to overwrite it."
        }
        else {
            if (Test-Path $examplePath) {
                Copy-Item $examplePath $envPath -Force:$Force
                $content = Get-Content $envPath -Raw
                $content = $content -replace "ECOMMERCE_DATABASE_URL=.*", "ECOMMERCE_DATABASE_URL=$rawUrl"
                Set-Content -Path $envPath -Value $content -Encoding UTF8
            }
            else {
                Set-Content -Path $envPath -Value "ECOMMERCE_DATABASE_URL=$rawUrl`n" -Encoding UTF8
            }
            Write-Host "Wrote local .env. Do not commit it."
        }
    }

    Write-Host ""
    Write-Host "Next commands:"
    if ($PersistUserEnv) {
        Write-Host "1. Open a new PowerShell terminal."
    }
    Write-Host "alembic upgrade head"
    Write-Host "python -m ecommerce.jobs.check_db_setup"
}
finally {
    if ($setPgPassword) {
        if ($null -eq $previousPgPassword) {
            Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        }
        else {
            $env:PGPASSWORD = $previousPgPassword
        }
    }
}
