param(
    [string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-dual',
    [string]$AnalysisDependencies='C:/tmp/xp-banking-analysis-deps'
)
$ErrorActionPreference='Stop'
$sourceDir=$PSScriptRoot
$build=[IO.Path]::GetFullPath($BuildDir)
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'MSVC x64 compiler is required; no validation skipped.' }
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
New-Item -ItemType Directory -Force -Path $build | Out-Null
$dll=Join-Path $build 'dual_native_proficiency.dll'
# MSVC names anonymous namespaces after the compiled path: mapping this folder
# (/pathmap needs /experimental:deterministic) lays the DLL out the same in every build folder.
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$sourceDir/dual_native_proficiency.cpp" "$sourceDir/dual_rules_lua.cpp" "$sourceDir/cbm_build_inputs.cpp" /experimental:deterministic /pathmap:"$sourceDir"=research\xp-banking-native /DCBM_BUILD_INPUTS=%CBM_BUILD_INPUTS% /DCBM_BUILD_ID=%CBM_BUILD_ID% /Fe"$dll" /Fo"$build/" /link /MAP:"$build/dual_native_proficiency.map"
@if errorlevel 1 exit /b 1
dumpbin /nologo /exports "$dll"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_rules_lua.cpp" "$sourceDir/dual_rules_lua_test.cpp" /Fe"$build/dual_rules_lua_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_rules_lua_test.exe"
@exit /b %errorlevel%
"@
$batchPath=Join-Path $build 'compile-proficiency.cmd'
[IO.File]::WriteAllText($batchPath,$batch,[Text.Encoding]::ASCII)
$previousPythonPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH=$AnalysisDependencies
    & python (Join-Path $sourceDir 'dual_proficiency_probe.py') --generate
    if ($LASTEXITCODE -ne 0) { throw 'Offline signature verification failed.' }
    $output=(& cmd.exe /d /c $batchPath 2>&1 | Out-String)
    [IO.File]::WriteAllText((Join-Path $build 'native-proficiency-build.log'),$output)
    if ($LASTEXITCODE -ne 0) { throw "Native binding compilation failed: $output" }
    foreach ($name in @('Bind','Destroy','GetSlots','GetChoiceCap','GetSkillBudget','RollOldHP','RollOldPlan','ApplyOldSkills','ApplyOldPlanSkills','ApplySelectedOldSkills','GetOldTarget','GetOldPlan','GetOldCap','IsEngineThread','ConfigureLua','LuaOldTarget','LuaOldPlan','LuaOldCap','LuaOldRoll')) {
        if ($output -notmatch "\bCBMDP_$name\b") { throw "Missing export CBMDP_$name" }
    }
    # Only our DLL executes in Python. Game instruction bytes execute in Unicorn.
    & python (Join-Path $sourceDir 'dual_proficiency_probe.py') --dll $dll
    if ($LASTEXITCODE -ne 0) { throw 'Native binding instruction checks failed.' }
} finally { $env:PYTHONPATH=$previousPythonPath }
