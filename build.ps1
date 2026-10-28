param([string]$Python = 'python')

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -c "import struct,sys; assert sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8, 'Use Python 3.13 x64 with Tcl/Tk'"
if ($LASTEXITCODE -ne 0) { throw 'Use Python 3.13 x64 with Tcl/Tk.' }
& $Python -m venv .build-venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
$buildPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
& $buildPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
$version = (& $buildPython -c 'from papermerge import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid application version.' }
$appName = "PaperMerge-v$version"
& $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name $appName --icon assets\papermerge.ico --add-data 'assets;assets' --add-data 'LICENSE;.' --add-data 'THIRD_PARTY_NOTICES.txt;.' main.py
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
$exe = Join-Path $PSScriptRoot "dist\$appName.exe"
$smokeDir = Join-Path $PSScriptRoot 'build\smoke-test'
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $smokeDir + '"')) -WindowStyle Hidden -PassThru -Wait
if ($process.ExitCode -ne 0) { throw 'Packaged executable self-test failed.' }
$report = Get-Content -LiteralPath (Join-Path $smokeDir 'self-test.json') -Raw | ConvertFrom-Json
if (-not $report.ok) { throw 'Packaged executable self-test did not pass.' }
Copy-Item -LiteralPath LICENSE,README.md,THIRD_PARTY_NOTICES.txt -Destination dist
$checksumName = "$appName.exe.sha256"
$checksumPath = Join-Path $PSScriptRoot "dist\$checksumName"
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $checksumPath -Value "$hash  $appName.exe" -Encoding ascii
$zip = Join-Path $PSScriptRoot "dist\$appName-windows-x64.zip"
Compress-Archive -LiteralPath $exe,'dist\LICENSE','dist\README.md','dist\THIRD_PARTY_NOTICES.txt',$checksumPath -DestinationPath $zip -Force
Write-Host "Verified release: $zip"
