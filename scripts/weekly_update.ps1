# Weekly incremental update. Register with Task Scheduler, e.g.:
#   schtasks /Create /TN "football-elo weekly" /SC WEEKLY /D TUE /ST 07:00 `
#     /TR "powershell -NoProfile -File C:\dev\football-elo\scripts\weekly_update.ps1"
Set-Location $PSScriptRoot\..
python -m football_elo update *>> data\update.log
