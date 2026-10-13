param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/bridge',
    [string]$LoaderRoot='C:/tmp/scroll-hook-research-20261009/InfinityLoader/InfinityLoaderDLL')
$ErrorActionPreference='Stop'
$build=[IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) {throw 'MSVC unavailable; no bridge checks skipped.'}
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$sources=@((Join-Path $PSScriptRoot 'bridge_assembler.cpp'))
$sources+=Get-ChildItem -LiteralPath (Join-Path $LoaderRoot 'asmjit'),(Join-Path $LoaderRoot 'asmtk') -Filter '*.cpp' -Recurse | ForEach-Object {$_.FullName}
$response=Join-Path $build 'bridge-compile.rsp'
$arguments=@('/nologo','/std:c++17','/EHs','/W3','/O1','/MP8','/DASMJIT_STATIC','/DASMTK_STATIC',
    "/I`"$LoaderRoot`"","/Fe`"$build/bridge_assembler.exe`"")
$arguments+=$sources | ForEach-Object {'"'+$_+'"'}
[IO.File]::WriteAllLines($response,$arguments,[Text.Encoding]::ASCII)
$batch="@call `"$vcvars`" >nul`r`n@if errorlevel 1 exit /b 1`r`ncl @`"$response`"`r`n@exit /b %errorlevel%`r`n"
$batchPath=Join-Path $build 'compile-bridge.cmd'
[IO.File]::WriteAllText($batchPath,$batch,[Text.Encoding]::ASCII)
Push-Location $build
try {
    & cmd.exe /d /c $batchPath
    if($LASTEXITCODE -ne 0){throw 'Actual loader assembler compilation failed.'}
} finally {Pop-Location}
