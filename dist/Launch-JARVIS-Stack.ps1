[CmdletBinding()]
param(
    [switch]$NoPortReclaim,
    [switch]$NoJarvisLaunch,
    [switch]$NoObsidianLaunch
)

$ErrorActionPreference = 'Stop'
$DistDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $DistDir
$JarvisExe = Join-Path $DistDir 'JARVIS.exe'
$PythonwExe = Join-Path $ProjectDir '.venv\Scripts\pythonw.exe'
$PythonExe = Join-Path $ProjectDir '.venv\Scripts\python.exe'
$SrcMain = Join-Path $ProjectDir 'src\main.py'
$SrcCfg = Join-Path $ProjectDir 'src\jarvis.cfg'
$DistCfg = Join-Path $DistDir 'jarvis.cfg'
$RootCfg = Join-Path $ProjectDir 'jarvis.cfg'
$LaunchLog = Join-Path $DistDir 'launch-stack.log'
$TailscaleExe = 'C:\Program Files\Tailscale\tailscale.exe'
$ObsidianExeDefault = 'C:\Program Files\Obsidian\Obsidian.exe'
$OllamaExe = 'C:\Users\jamie\AppData\Local\Programs\Ollama\ollama.exe'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

function Write-LaunchLog {
    param([string]$Message)
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    Add-Content -Path $LaunchLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-IniValue {
    param([string]$Path,[string]$Section,[string]$Key,[string]$Default)
    if (-not (Test-Path $Path)) { return $Default }
    $currentSection = ''
    foreach ($rawLine in Get-Content -Path $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#') -or $line.StartsWith(';')) { continue }
        if ($line -match '^\[(.+)\]$') { $currentSection = $matches[1].Trim(); continue }
        if ($currentSection -ieq $Section -and $line -match '^([^=]+?)\s*=\s*(.*)$') {
            if ($matches[1].Trim() -ieq $Key) { return $matches[2].Trim() }
        }
    }
    return $Default
}

function Test-PortListening { param([int]$Port) return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) }

function Wait-Until {
    param([scriptblock]$Condition,[int]$TimeoutSeconds = 60,[int]$DelaySeconds = 2,[string]$FailureMessage = 'Timed out waiting for condition.')
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try { if (& $Condition) { return $true } } catch {}
        Start-Sleep -Seconds $DelaySeconds
    }
    throw $FailureMessage
}

function Stop-ProcessesOnPorts {
    param([int[]]$Ports)
    $pids = New-Object System.Collections.Generic.HashSet[int]
    foreach ($port in $Ports) {
        $owners = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($owner in @($owners)) { if ($owner) { [void]$pids.Add([int]$owner) } }
    }
    foreach ($procId in $pids) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-LaunchLog ("Stopping PID {0} ({1})" -f $procId, $proc.ProcessName)
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-JsonEndpoint {
    param([string[]]$Uris)
    foreach ($uri in $Uris) {
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

function Start-JarvisSource {
    param([string]$TlsFlag,[string]$VaultPath,[string]$ObsidianApiUrl)
    if (-not (Test-Path $PythonExe)) {
        throw "Venv python not found at $PythonExe"
    }
    $env:JARVIS_ENABLE_TLS = $TlsFlag
    $env:JARVIS_OBSIDIAN_PATH = $VaultPath
    $env:JARVIS_OBSIDIAN_API_URL = $ObsidianApiUrl
    Start-Process -FilePath $PythonExe -ArgumentList @($SrcMain) -WorkingDirectory $ProjectDir -WindowStyle Hidden | Out-Null
}

New-Item -Path $LaunchLog -ItemType File -Force | Out-Null
Write-LaunchLog 'Launcher started'

if (Test-Path $RootCfg) {
    Copy-Item -Path $RootCfg -Destination $DistCfg -Force
    if (Test-Path (Split-Path -Parent $SrcCfg)) { Copy-Item -Path $RootCfg -Destination $SrcCfg -Force }
    Write-LaunchLog 'Synced root jarvis.cfg into dist and src configs'
}
if (-not (Test-Path $DistCfg)) { throw "jarvis.cfg not found at $DistCfg" }

$HudPort = [int](Get-IniValue -Path $DistCfg -Section 'jarvis' -Key 'hud_port' -Default '7474')
$VaultPath = Get-IniValue -Path $DistCfg -Section 'obsidian' -Key 'path' -Default 'C:\Users\jamie\Documents\JARVIS-Brain'
$ObsidianApiUrl = Get-IniValue -Path $DistCfg -Section 'obsidian' -Key 'api_url' -Default 'http://127.0.0.1:27123'
$ObsidianExe = if (Test-Path $ObsidianExeDefault) { $ObsidianExeDefault } else { $null }

$CertDir = Join-Path $ProjectDir 'src\jarvis_data\certs'
New-Item -ItemType Directory -Path $CertDir -Force | Out-Null
$CertFile = Join-Path $CertDir 'home-1.tail79f127.ts.net.crt'
$KeyFile = Join-Path $CertDir 'home-1.tail79f127.ts.net.key'
if ((-not (Test-Path $CertFile)) -and (Test-Path $TailscaleExe)) {
    try {
        & $TailscaleExe cert --cert-file $CertFile --key-file $KeyFile 'home-1.tail79f127.ts.net' | Out-Null
        Write-LaunchLog 'Generated Tailscale certificates'
    } catch {
        Write-LaunchLog ("Certificate generation failed: {0}" -f $_.Exception.Message)
    }
}
$EnableJarvisTls = $false
$LocalScheme = 'http'
$TlsFlag = '0'
Write-LaunchLog ("TLS disabled by user request")

if (-not $NoPortReclaim) {
    Stop-ProcessesOnPorts -Ports @($HudPort)
    Start-Sleep -Seconds 1
}

if (Test-Path $OllamaExe) {
    try {
        if (-not (Test-JsonEndpoint -Uris @('http://127.0.0.1:11434/api/tags'))) {
            Write-LaunchLog 'Starting Ollama'
            Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
            Wait-Until -Condition { Test-JsonEndpoint -Uris @('http://127.0.0.1:11434/api/tags') } -TimeoutSeconds 60 -DelaySeconds 2 -FailureMessage 'Ollama did not become ready in time.' | Out-Null
        } else {
            Write-LaunchLog 'Ollama already ready'
        }
    } catch {
        Write-LaunchLog ("Ollama startup warning: {0}" -f $_.Exception.Message)
    }
}

if ((-not $NoObsidianLaunch) -and $ObsidianExe -and (Test-Path $VaultPath)) {
    try {
        Start-Process -FilePath $ObsidianExe -ArgumentList @('--vault', $VaultPath) -WindowStyle Hidden | Out-Null
        Write-LaunchLog 'Obsidian launched'
    } catch {
        Write-LaunchLog ("Obsidian launch warning: {0}" -f $_.Exception.Message)
    }
}

if (-not $NoJarvisLaunch) {
    if ((Test-Path $PythonwExe) -and (Test-Path $SrcMain)) {
        Write-LaunchLog 'Starting JARVIS from source venv'
        Start-JarvisSource -TlsFlag $TlsFlag -VaultPath $VaultPath -ObsidianApiUrl $ObsidianApiUrl
    } elseif (Test-Path $JarvisExe) {
        Write-LaunchLog 'Starting JARVIS.exe fallback'
        $env:JARVIS_ENABLE_TLS = $TlsFlag
        Start-Process -FilePath $JarvisExe -WorkingDirectory $DistDir | Out-Null
    } else {
        throw 'No JARVIS launch target found.'
    }
}

$localUris = if ($EnableJarvisTls) { @("https://127.0.0.1:$HudPort/api/sysinfo") } else { @("http://127.0.0.1:$HudPort/api/sysinfo") }
Wait-Until -Condition { Test-JsonEndpoint -Uris $localUris } -TimeoutSeconds 90 -DelaySeconds 3 -FailureMessage 'JARVIS API did not come online.' | Out-Null
Write-LaunchLog 'JARVIS API responding'

if (Test-Path $TailscaleExe) {
    try {
        $tailscale = & $TailscaleExe status --json | ConvertFrom-Json
        $tailDns = (($tailscale.Self.DNSName | Out-String).Trim()).TrimEnd('.')
        if ($tailDns) {
            $remoteScheme = if ($EnableJarvisTls) { 'https' } else { 'http' }
            $remoteUrl = "${remoteScheme}://$tailDns`:$HudPort/api/sysinfo"
            Write-LaunchLog ("Tailnet URL: {0}" -f $remoteUrl)
        }
    } catch {
        Write-LaunchLog ("Tailscale status warning: {0}" -f $_.Exception.Message)
    }
}

Write-LaunchLog 'Launcher completed successfully'
