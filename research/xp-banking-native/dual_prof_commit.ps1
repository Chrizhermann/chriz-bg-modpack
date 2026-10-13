param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-prof-commit')
$ErrorActionPreference='Stop'
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) {throw 'MSVC x64 tools unavailable.'}
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$build=[System.IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$source=Join-Path $PSScriptRoot 'dual_prof_commit.cpp'
$test=Join-Path $PSScriptRoot 'dual-prof-commit-test.cpp'
$exe=Join-Path $build 'dual-prof-commit-test.exe'
$dll=Join-Path $build 'dual_prof_commit.dll'
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$source" "$test" /Fe"$exe"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$source" /Fe"$dll"
@exit /b %errorlevel%
"@
$batchPath=Join-Path $build 'compile-prof-commit.cmd'
[System.IO.File]::WriteAllText($batchPath,$batch,[System.Text.Encoding]::ASCII)
Push-Location $build
try {
    $output=(& cmd.exe /d /c $batchPath 2>&1 | Out-String)
    $code=$LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $build 'prof-commit-msvc-build.log'),$output)
    if($code -ne 0){throw "MSVC proficiency primitive build failed: $output"}
    & $exe
    if($LASTEXITCODE -ne 0){throw 'Proficiency primitive tests failed.'}
}finally{Pop-Location}
