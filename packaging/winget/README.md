# WinGet Manifest

This directory contains the WinGet manifest template for submitting to
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs).

## Initial submission

1. Fork `microsoft/winget-pkgs`
2. Copy `Jaypetez.Glean.yaml` to `manifests/j/Jaypetez/Glean/1.0.0/`
3. Update `InstallerSha256` with the real hash from the GitHub Release
4. Submit a PR

## Automated updates

After the initial submission, add this step to the release workflow:
```powershell
wingetcreate update Jaypetez.Glean --version $version --urls $url --submit --token $env:WINGET_TOKEN
```
