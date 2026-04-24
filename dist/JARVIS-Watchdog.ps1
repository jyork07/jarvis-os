[CmdletBinding()]
param(
    [int]$CheckIntervalSeconds = 60,
    [int]$LaunchCooldownSeconds = 45
)

$ErrorActionPreference = 'Continue'
$DistDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $DistDir 'Launch-JARVIS-Stack.ps1'
$LogFile = Join-Path $DistDir 'jarvis-watchdog.log'
$TailscaleExe = 'C:\Program Files\Tailscale\tailscale.exe'
$LastLaunch = [datetime]::MinValue
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

function Write-WatchdogLog {
    param([string]$Message)
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Test-JarvisLocal {
    foreach ($uri in @('https://127.0.0.1:7474/api/sysinfo','http://127.0.0.1:7474/api/sysinfo')) {
        try {
            if ($uri -like 'https://*') {
                $resp = & curl.exe -k -sS --max-time 5 $uri
                if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($resp)) { return $true }
            } else {
                $resp = Invoke-RestMethod -Uri $uri -TimeoutSec 5
                if ($null -ne $resp) { return $true }
            }
        } catch {}
    }
    return $false
}

function Get-TailDns {
    try {
        if (-not (Test-Path $TailscaleExe)) { return $null }
        $status = & $TailscaleExe status --json | ConvertFrom-Json
        if ($status.BackendState -ne 'Running') { return $null }
        return ((($status.Self.DNSName | Out-String).Trim()).TrimEnd('.'))
    } catch {
        return $null
    }
}

function Test-JarvisTailnet {
    $dns = Get-TailDns
    if (-not $dns) { return $false }
    foreach ($uri in @(("https://{0}:7474/api/sysinfo" -f $dns), ("http://{0}:7474/api/sysinfo" -f $dns))) {
        try {
            if ($uri -like 'https://*') {
                $resp = & curl.exe -k -sS --max-time 8 $uri
                if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($resp)) { return $true }
            } else {
                $resp = Invoke-RestMethod -Uri $uri -TimeoutSec 8
                if ($null -ne $resp) { return $true }
            }
        } catch {}
    }
    return $false
}

function Invoke-Launcher {
    if (-not (Test-Path $Launcher)) {
        Write-WatchdogLog "Launcher missing: $Launcher"
        return
    }
    $since = ((Get-Date) - $LastLaunch).TotalSeconds
    if ($since -lt $LaunchCooldownSeconds) {
        Write-WatchdogLog ("Launch skipped; cooldown active ({0:N0}s < {1}s)" -f $since, $LaunchCooldownSeconds)
        return
    }
    Write-WatchdogLog 'Invoking Launch-JARVIS-Stack.ps1'
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Launcher
        $LastLaunch = Get-Date
        Write-WatchdogLog 'Launcher invocation completed'
    } catch {
        $LastLaunch = Get-Date
        Write-WatchdogLog ("Launcher invocation failed: {0}" -f $_.Exception.Message)
    }
}

New-Item -Path $LogFile -ItemType File -Force | Out-Null
Write-WatchdogLog 'Watchdog started'
Invoke-Launcher

while ($true) {
    $localOk = Test-JarvisLocal
    $tailOk = Test-JarvisTailnet
    if ($localOk -and $tailOk) {
        Write-WatchdogLog 'Health OK (local + tailnet)'
    } else {
        Write-WatchdogLog ("Health degraded: local={0} tailnet={1}" -f $localOk, $tailOk)
        Invoke-Launcher
    }
    Start-Sleep -Seconds $CheckIntervalSeconds
}
