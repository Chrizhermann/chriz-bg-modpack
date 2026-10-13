param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-identity')
$ErrorActionPreference='Stop'
$sourceDir=$PSScriptRoot
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'MSVC x64 tools unavailable.' }
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$build=[System.IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$identity=Join-Path $sourceDir 'identity_native.cpp'
$reset=Join-Path $sourceDir 'reset_native.cpp'
$party=Join-Path $sourceDir 'party_native.cpp'
$award=Join-Path $sourceDir 'award_native.cpp'
$writer=Join-Path $sourceDir 'writer_native.cpp'
$test=Join-Path $sourceDir 'reset_native_test.cpp'
$dll=Join-Path $build 'cbmbank_identity.dll'
$exe=Join-Path $build 'reset_native_test.exe'
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$identity" "$reset" "$party" "$award" "$writer" /Fe"$dll"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$identity" "$reset" "$party" "$test" /Fe"$exe"
@exit /b %errorlevel%
"@
$batchPath=Join-Path $build 'compile-reset.cmd'
[System.IO.File]::WriteAllText($batchPath,$batch,[System.Text.Encoding]::ASCII)
Push-Location $build
try {
    $output=(& cmd.exe /d /c $batchPath 2>&1 | Out-String)
    $code=$LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $build 'reset-msvc-build.log'),$output)
    if ($code -ne 0) {throw "MSVC reset build failed: $output"}
    & $exe
    if ($LASTEXITCODE -ne 0) {throw 'Reset native shim tests failed.'}
} finally {Pop-Location}
