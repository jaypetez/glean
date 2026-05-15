$ErrorActionPreference = '"'"'Stop'"'"'

$packageName = '"'"'glean'"'"'
$url64 = "https://github.com/jaypetez/glean/releases/download/v$($env:chocolateyPackageVersion)/glean-windows-x86_64.exe"

$toolsDir = "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)"
$exePath = Join-Path $toolsDir '"'"'glean.exe'"'"'

Get-ChocolateyWebFile -PackageName $packageName `
  -FileFullPath $exePath `
  -Url64bit $url64 `
  -ChecksumType64 '"'"'sha256'"'"'
