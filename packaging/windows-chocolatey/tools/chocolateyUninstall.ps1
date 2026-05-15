$toolsDir = "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)"
$exePath = Join-Path $toolsDir '"'"'glean.exe'"'"'
if (Test-Path $exePath) { Remove-Item $exePath -Force }
