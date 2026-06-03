#Requires -Version 5.1
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet("run", "start", "stop", "restart", "status", "logs", "doctor")]
  [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$StateDir = Join-Path $env:USERPROFILE ".claude\channels\telegram"
$WorkDir = Join-Path $StateDir "workdir"
$PidFile = Join-Path $StateDir "claude.pid"
$OutLog = Join-Path $StateDir "claude-watchdog.out.log"
$ErrLog = Join-Path $StateDir "claude-watchdog.err.log"
$TaskName = "ClaudeWatchdogTelegram"

function Log($Message) { Write-Host "[claude-watchdog] $Message" }
function Warn($Message) { Write-Warning "[claude-watchdog] $Message" }
function Die($Message) { throw "[claude-watchdog] $Message" }
function HasCommand($Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Get-ClaudeProcess {
  if (-not (Test-Path $PidFile)) { return $null }
  $pidText = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pidText -notmatch '^\d+$') { return $null }
  return Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
}

function Test-PluginInstalled {
  $cache = Join-Path $env:USERPROFILE ".claude\plugins\cache"
  return [bool](Get-ChildItem -Path $cache -Directory -Recurse -Filter telegram -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Start-ClaudeLoop {
  New-Item -ItemType Directory -Force -Path $StateDir, $WorkDir | Out-Null
  if (-not (HasCommand claude)) { Die "claude CLI missing" }
  if (-not (Test-Path (Join-Path $StateDir ".env"))) { Die "missing $StateDir\.env" }
  if (-not (Test-Path (Join-Path $StateDir "access.json"))) { Die "missing $StateDir\access.json" }
  if (-not (Test-PluginInstalled)) { Die "telegram plugin missing" }

  while ($true) {
    Log "starting Claude Telegram channel"
    Push-Location $WorkDir
    try {
      # Native Windows beta deliberately starts a fresh Claude process without
      # --continue. Claude's transcript slugging for Windows paths is not stable
      # across shells, and a broad --continue can resume the user's unrelated
      # interactive session. WSL2/Linux mode provides full transcript-resume
      # parity today.
      $args = @("--dangerously-skip-permissions", "--channels", "plugin:telegram@claude-plugins-official")
      $proc = Start-Process -FilePath "claude" -ArgumentList $args -NoNewWindow -PassThru -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
      Set-Content -Path $PidFile -Value $proc.Id -Encoding ASCII
      $proc.WaitForExit()
      Log "claude exited with code $($proc.ExitCode); restarting in 30s"
    } finally {
      Pop-Location
      Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 30
  }
}

function Stop-Claude {
  $proc = Get-ClaudeProcess
  if ($proc) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Log "stopped Claude process $($proc.Id)"
  } else {
    Log "Claude process not running"
  }
}

function Show-Status {
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($task) { Log "task: $($task.State)" } else { Warn "task: not registered" }
  $proc = Get-ClaudeProcess
  if ($proc) { Log "claude: pid $($proc.Id)" } else { Warn "claude: not running" }
  if (Test-PluginInstalled) { Log "telegram plugin: installed" } else { Warn "telegram plugin: missing" }
}

function Show-Logs {
  foreach ($path in @($OutLog, $ErrLog)) {
    if (Test-Path $path) {
      Write-Host "--- $path ---"
      Get-Content $path -Tail 100
    }
  }
}

function Doctor {
  if (-not (HasCommand claude)) { Die "claude CLI missing" } else { Log "claude installed" }
  if (-not (HasCommand bun)) { Die "bun missing" } else { & bun --version *> $null; Log "bun runs" }
  if (-not (Test-Path (Join-Path $StateDir ".env"))) { Die "missing $StateDir\.env" } else { Log ".env present" }
  if (-not (Test-Path (Join-Path $StateDir "access.json"))) { Die "missing $StateDir\access.json" } else { Log "access.json present" }
  if (-not (Test-PluginInstalled)) { Die "telegram plugin missing" } else { Log "telegram plugin installed" }
  Log "all checks passed"
}

switch ($Command) {
  "run" { Start-ClaudeLoop }
  "start" { Start-ScheduledTask -TaskName $TaskName; Log "started task $TaskName" }
  "stop" { Stop-Claude; Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Log "stopped task $TaskName" }
  "restart" { Stop-Claude; Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Start-ScheduledTask -TaskName $TaskName; Log "restarted task $TaskName" }
  "status" { Show-Status }
  "logs" { Show-Logs }
  "doctor" { Doctor }
}
