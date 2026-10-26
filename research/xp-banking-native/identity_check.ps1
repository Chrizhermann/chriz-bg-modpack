param([string]$BuildDir = 'C:/tmp/campaign-xp-banking-20261009/native-identity')
$ErrorActionPreference = 'Stop'
$sourceDir = $PSScriptRoot
$vswhere = 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'MSVC x64 tools unavailable.' }
$vcvars = Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$build = [System.IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$core = Join-Path $sourceDir 'identity_native.cpp'
$test = Join-Path $sourceDir 'identity_native_test.cpp'
$exe = Join-Path $build 'identity_native_test.exe'
$dll = Join-Path $build 'cbmbank_identity_only.dll'
$batch = @"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$core" /Fe"$dll"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$core" "$test" /Fe"$exe"
@if errorlevel 1 exit /b 1
dumpbin /nologo /exports "$dll"
@exit /b %errorlevel%
"@
$batchPath = Join-Path $build 'compile-identity.cmd'
[System.IO.File]::WriteAllText($batchPath,$batch,[System.Text.Encoding]::ASCII)
Push-Location $build
try {
    $output = (& cmd.exe /d /c $batchPath 2>&1 | Out-String)
    $compileExit = $LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $build 'msvc-build.log'),$output)
    if ($compileExit -ne 0) { throw "MSVC failed: $output" }
    foreach($name in @('Configure','Query','LuaQuery','LuaAckReplaced','Copy','Marshal','CharacterExport','CharacterImport','Construct','Destruct','CanMutate')) {
        if ($output -notmatch "\bCBMI_$name\b") { throw "Missing C ABI export CBMI_$name" }
    }
    & $exe
    if ($LASTEXITCODE -ne 0) { throw 'Identity native shim assertions failed.' }
    # Another thread's lifetime event leaves every identity unknown for the rest of
    # its process: that case runs in a process of its own.
    & $exe foreign 0
    if ($LASTEXITCODE -ne 0) { throw 'Identity native foreign case failed.' }
} finally { Pop-Location }
