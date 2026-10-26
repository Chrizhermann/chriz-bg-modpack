param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-writer')
$ErrorActionPreference='Stop'
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation){throw 'MSVC x64 tools unavailable.'}
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$build=[System.IO.Path]::GetFullPath($BuildDir);New-Item -ItemType Directory -Force -Path $build | Out-Null
$identity=Join-Path $PSScriptRoot 'identity_native.cpp';$writer=Join-Path $PSScriptRoot 'writer_native.cpp';$test=Join-Path $PSScriptRoot 'writer_native_test.cpp'
# The writer coordinates with the award bridge in the same DLL (in-flight and uncertain records).
$award=Join-Path $PSScriptRoot 'award_native.cpp'
$exe=Join-Path $build 'writer_native_test.exe'
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$identity" "$award" "$writer" "$test" /Fe"$exe"
@exit /b %errorlevel%
"@
$batchPath=Join-Path $build 'compile-writer.cmd';[System.IO.File]::WriteAllText($batchPath,$batch,[System.Text.Encoding]::ASCII)
Push-Location $build
try{
    $output=(& cmd.exe /d /c $batchPath 2>&1 | Out-String);$code=$LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $build 'writer-msvc-build.log'),$output)
    if($code -ne 0){throw "MSVC writer build failed: $output"}
    & $exe;if($LASTEXITCODE -ne 0){throw 'Native writer assertions failed.'}
    # Another thread's lifetime event leaves every identity unknown for the rest
    # of its process: each of those cases runs in a process of its own.
    foreach($case in 0..3){& $exe foreign $case;if($LASTEXITCODE -ne 0){throw "Native writer foreign case $case failed."}}
}finally{Pop-Location}
