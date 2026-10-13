param(
    [string]$BuildDir = 'C:/tmp/campaign-xp-banking-20261009/native-dual',
    [switch]$WithWsl
)
$ErrorActionPreference = 'Stop'
$sourceDir = $PSScriptRoot
$vswhere = 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
if (!(Test-Path -LiteralPath $vswhere)) { throw 'MSVC discovery tool is missing.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'MSVC x64 C++ tools are unavailable; no check was skipped.' }
$vcvars = Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$build = [System.IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$core = Join-Path $sourceDir 'dual_transaction.cpp'
$test = Join-Path $sourceDir 'dual_transaction_test.cpp'
$exe = Join-Path $build 'dual_transaction_test.exe'
$dll = Join-Path $build 'dual_transaction.dll'
# Commands compile our research source only. No game executable is run or linked.
$batch = @"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /LD "$core" /Fe"$dll"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 "$core" "$test" /Fe"$exe"
@if errorlevel 1 exit /b 1
dumpbin /nologo /exports "$dll"
@exit /b %errorlevel%
"@
$batchPath = Join-Path $build 'compile-dual.cmd'
[System.IO.File]::WriteAllText($batchPath, $batch, [System.Text.Encoding]::ASCII)
Push-Location $build
try {
    $output = (& cmd.exe /d /c $batchPath 2>&1 | Out-String)
    $compileExit = $LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $build 'msvc-build.log'), $output)
    if ($compileExit -ne 0) { throw "MSVC build failed: $output" }
    $exports = @('Create','Destroy','Begin','Choose','GetPreview','Commit','Cancel','Resolve','GetPhase','Reset')
    foreach($name in $exports) {
        if ($output -notmatch "\bCBMD_$name\b") { throw "Missing C ABI export CBMD_$name" }
    }
    $result = & $exe
    if ($LASTEXITCODE -ne 0) { throw 'Windows contract tests failed.' }
    $windows = $result | ConvertFrom-Json
    $report = [ordered]@{ windows_msvc = $windows; verified_c_exports = $exports.Count;
        native_engine_binding = $false; game_launched = $false; source_sha256 = @{} }
    foreach($name in @('dual_transaction.h','dual_transaction.cpp','dual_transaction_test.cpp')) {
        $report.source_sha256[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $sourceDir $name)).Hash.ToLower()
    }
    if ($WithWsl) {
        $linuxDir = (& wsl --exec wslpath -u $sourceDir).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve the WSL source path.' }
        # Reject shell metacharacters rather than interpolate ambiguous paths.
        if ($linuxDir -notmatch '^/[a-zA-Z0-9_./ -]+$') { throw 'Unsupported source path characters.' }
        $command = "g++ -std=c++17 -pthread -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -fno-omit-frame-pointer -g '$linuxDir/dual_transaction.cpp' '$linuxDir/dual_transaction_test.cpp' -o /tmp/cbm-dual-transaction-test && /tmp/cbm-dual-transaction-test"
        $linux = & wsl --exec sh -lc $command
        if ($LASTEXITCODE -ne 0) { throw 'GCC sanitizer build or tests failed; no check was skipped.' }
        $report.gcc_asan_ubsan = $linux | ConvertFrom-Json
    }
} finally { Pop-Location }
$report | ConvertTo-Json -Depth 6
