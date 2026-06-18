#Requires -Version 5.1
<#
Native Windows installer for claude-watchdog's Telegram Claude session.

This creates a per-user Scheduled Task that runs scripts\claude-watchdog-windows.ps1
at logon and keeps Claude Code's Telegram channel alive with restart-on-exit.

Claude Code CLI must already be installed and authenticated. Run once
interactively from the workdir if Claude asks first-run trust / permissions
questions, then start the scheduled task again.
#>
[CmdletBinding()]
param(
  [switch]$InstallDeps,
  [string]$Token = $env:TELEGRAM_BOT_TOKEN,
  [string]$TelegramUserId = $env:TELEGRAM_USER_ID,
  [ValidateSet("default", "plan", "acceptEdits", "auto", "dontAsk", "bypassPermissions")]
  [string]$PermissionMode = $(if ($env:CLAUDE_PERMISSION_MODE) { $env:CLAUDE_PERMISSION_MODE } else { "bypassPermissions" }),
  [switch]$Demo,
  [switch]$Start,
  [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateDir = Join-Path $env:USERPROFILE ".claude\channels\telegram"
$WorkDir = Join-Path $StateDir "workdir"
$InstallDir = Join-Path $env:LOCALAPPDATA "claude-watchdog"
$TaskName = "ClaudeWatchdogTelegram"
$Runner = Join-Path $InstallDir "claude-watchdog-windows.ps1"

function Log($Message) { Write-Host "[claude-watchdog] $Message" }
function Warn($Message) { Write-Warning "[claude-watchdog] $Message" }
function Die($Message) { throw "[claude-watchdog] $Message" }
function HasCommand($Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function Confirm-Step($Prompt) {
  if ($Yes) { return $true }
  $answer = Read-Host "$Prompt [y/N]"
  return $answer -match '^(y|yes)$'
}
function Set-EnvKey($Path, $Name, $Value) {
  $lines = @()
  if (Test-Path $Path) { $lines = Get-Content $Path | Where-Object { $_ -notlike "$Name=*" } }
  $lines += "$Name=$Value"
  Set-Content -Path $Path -Value $lines -Encoding UTF8
}
function Protect-PrivateFile($Path) {
  if (Test-Path $Path) {
    icacls $Path /inheritance:r /grant:r "$($env:USERNAME):(R,W)" *> $null
  }
}
function Write-EncryptedToken($Token) {
  $secure = ConvertTo-SecureString -String $Token -AsPlainText -Force
  $encPath = Join-Path $StateDir ".token.enc"
  $secure | ConvertFrom-SecureString | Set-Content -Path $encPath -Encoding ASCII
  Protect-PrivateFile $encPath
}

function Install-Dependencies {
  $missing = @()
  foreach ($cmd in @("git", "bun", "claude")) {
    if (-not (HasCommand $cmd)) { $missing += $cmd }
  }
  if ($missing.Count -eq 0) { return }
  if (-not $InstallDeps) { return }
  if (-not (HasCommand winget)) {
    Die "missing commands ($($missing -join ', ')) and winget is not available. Install deps manually, then re-run."
  }
  if (-not (Confirm-Step "Install missing packages with winget where supported: $($missing -join ', ')?")) {
    Die "dependency install declined"
  }
  if ($missing -contains "git") { winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements }
  if ($missing -contains "bun") { winget install --id Oven-sh.Bun -e --accept-package-agreements --accept-source-agreements }
  if ($missing -contains "claude") {
    Warn "Claude Code CLI installation is not automated here; install/authenticate it from Anthropic docs, then re-run."
  }
}

function Test-PluginInstalled {
  $cache = Join-Path $env:USERPROFILE ".claude\plugins\cache"
  return [bool](Get-ChildItem -Path $cache -Directory -Recurse -Filter telegram -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Install-TelegramPlugin {
  if (-not (HasCommand claude)) {
    Warn "claude not found; skipping telegram plugin install — install/authenticate Claude Code, then re-run"
    return
  }
  try { & claude plugin marketplace add anthropics/claude-plugins-official *> $null } catch { }
  try { & claude plugin install telegram@claude-plugins-official *> $null } catch { }
  if (Test-PluginInstalled) {
    Log "installed plugin telegram@claude-plugins-official"
  } else {
    Warn "could not auto-install telegram plugin — run: claude plugin install telegram@claude-plugins-official"
  }
}

function Write-Config {
  New-Item -ItemType Directory -Force -Path $StateDir, $WorkDir | Out-Null
  $envPath = Join-Path $StateDir ".env"
  if ($Token) {
    if ($Token -notmatch '^[0-9]+:[A-Za-z0-9_-]+$') { Die "Telegram bot token should look like '<bot-id>:<secret>'" }
    Write-EncryptedToken $Token
    Set-Content -Path $envPath -Value @("TELEGRAM_BOT_TOKEN_ENCRYPTED=1", "CLAUDE_PERMISSION_MODE=$PermissionMode", "CLAUDE_WATCHDOG_DEMO=$([int][bool]$Demo)") -Encoding UTF8
    Protect-PrivateFile $envPath
    Log "wrote encrypted token and $StateDir\.env"
  } elseif (-not (Test-Path (Join-Path $StateDir ".env"))) {
    Copy-Item (Join-Path $Root "config\env.example") $envPath
    Set-EnvKey $envPath "CLAUDE_PERMISSION_MODE" $PermissionMode
    Set-EnvKey $envPath "CLAUDE_WATCHDOG_DEMO" $([int][bool]$Demo)
    Protect-PrivateFile $envPath
    Warn "created $StateDir\.env — edit TELEGRAM_BOT_TOKEN before starting"
  } else {
    Set-EnvKey $envPath "CLAUDE_PERMISSION_MODE" $PermissionMode
    Set-EnvKey $envPath "CLAUDE_WATCHDOG_DEMO" $([int][bool]$Demo)
    Protect-PrivateFile $envPath
  }

  if ($TelegramUserId) {
    if ($TelegramUserId -notmatch '^\d+$') { Die "Telegram user ID must be numeric" }
    $payload = [ordered]@{
      dmPolicy = "allowlist"
      allowFrom = @($TelegramUserId)
      groups = @{}
      pending = @{}
      ackReaction = "👀"
      replyToMode = "first"
      textChunkLimit = 4096
      chunkMode = "newline"
    }
    $accessPath = Join-Path $StateDir "access.json"
    $payload | ConvertTo-Json -Depth 5 | Set-Content -Path $accessPath -Encoding UTF8
    Protect-PrivateFile $accessPath
    Log "wrote $StateDir\access.json"
  } elseif (-not (Test-Path (Join-Path $StateDir "access.json"))) {
    $accessPath = Join-Path $StateDir "access.json"
    Copy-Item (Join-Path $Root "config\access.example.json") $accessPath
    Protect-PrivateFile $accessPath
    Warn "created $StateDir\access.json — add your Telegram user ID before starting"
  }
}

function Install-RunnerAndTask {
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
  Copy-Item (Join-Path $Root "scripts\claude-watchdog-windows.ps1") $Runner -Force

  $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
  if ($pwshCmd) { $pwsh = $pwshCmd.Source } else { $pwsh = (Get-Command powershell.exe).Source }
  $action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`" run"
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Claude Code Telegram channel" -Force | Out-Null
  Log "registered Scheduled Task: $TaskName"
}

Install-Dependencies
Write-Config
Install-TelegramPlugin
Install-RunnerAndTask

$missing = @()
foreach ($cmd in @("bun", "claude")) { if (-not (HasCommand $cmd)) { $missing += $cmd } }
if ($missing.Count -gt 0) { Warn "missing commands: $($missing -join ', ')" }

if ($Start) {
  if (-not (HasCommand claude)) { Die "claude CLI is missing; install and authenticate it before -Start" }
  if (-not (Test-PluginInstalled)) { Die "telegram plugin is not installed; run: claude plugin marketplace add anthropics/claude-plugins-official; claude plugin install telegram@claude-plugins-official" }
  Start-ScheduledTask -TaskName $TaskName
  Log "started Scheduled Task: $TaskName"
}

Log "installed"
Log "next: powershell -ExecutionPolicy Bypass -File `"$Runner`" doctor"
if (-not $Start) { Log "then: Start-ScheduledTask -TaskName $TaskName" }
