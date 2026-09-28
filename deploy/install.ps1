# Run once on the PC: start the service at logon (auto-restart) and allow wake timers.
# Main access is https://light.example.com:8444 via the local Caddy; also allow plain
# http://<pc-lan-ip>:8765 from the local subnet only (user request).
$dir = "$env:USERPROFILE\sunlight"
$action = New-ScheduledTaskAction -Execute "$dir\venv\Scripts\pythonw.exe" `
  -Argument "-m sunlight.main --data $dir" -WorkingDirectory "$dir\service"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName Sunlight -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
if (-not (Get-NetFirewallRule -DisplayName "Sunlight 8765 LAN" -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName "Sunlight 8765 LAN" -Direction Inbound -Protocol TCP -LocalPort 8765 `
    -RemoteAddress LocalSubnet -Action Allow | Out-Null
}
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1   # allow wake timers on AC
powercfg /setactive SCHEME_CURRENT
Start-ScheduledTask -TaskName Sunlight
"installed"
