param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-dual')
$ErrorActionPreference='Stop'
$sourceDir=$PSScriptRoot
$build=[IO.Path]::GetFullPath($BuildDir)
$installation=& 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe' -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'MSVC x64 tools are required.' }
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
New-Item -ItemType Directory -Force -Path $build | Out-Null
# MSVC names anonymous namespaces after the compiled path: mapping this folder
# (/pathmap needs /experimental:deterministic) lays the DLL out the same in every build folder.
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
ml64 /nologo /c /Fo"$build/dual_hp_thunks.obj" "$sourceDir/dual_hp_thunks.asm"
@if errorlevel 1 exit /b 1
ml64 /nologo /c /Fo"$build/dual_choice_thunks.obj" "$sourceDir/dual_choice_thunks.asm"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$sourceDir/dual_hp_observer.cpp" "$sourceDir/dual_choice_observer.cpp" "$sourceDir/dual_manual_session.cpp" "$sourceDir/dual_manual_lua.cpp" "$sourceDir/dual_combined_preview.cpp" "$sourceDir/dual_entry.cpp" "$sourceDir/cbm_build_inputs.cpp" "$build/dual_hp_thunks.obj" "$build/dual_choice_thunks.obj" /experimental:deterministic /pathmap:"$sourceDir"=research\xp-banking-native /DCBM_BUILD_INPUTS=%CBM_BUILD_INPUTS% /DCBM_BUILD_ID=%CBM_BUILD_ID% /Fe"$build/dual_hp_observer.dll" /Fo"$build/" /link /EXPORT:CBMDH_ManualCallThunk /EXPORT:CBMDH_ContributionThunk /EXPORT:CBMDC_ActiveThunk /EXPORT:CBMDC_InactiveThunk
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_hp_observer_test.cpp" "$sourceDir/dual_hp_observer.cpp" /Fe"$build/dual_hp_observer_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_hp_observer_test.exe"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_choice_observer_test.cpp" "$sourceDir/dual_choice_observer.cpp" /Fe"$build/dual_choice_observer_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_choice_observer_test.exe"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_manual_session_test.cpp" "$sourceDir/dual_manual_session.cpp" "$sourceDir/dual_choice_observer.cpp" /Fe"$build/dual_manual_session_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_manual_session_test.exe"
@if errorlevel 1 exit /b 1
"$build/dual_manual_session_test.exe" -1
@if errorlevel 1 exit /b 1
"$build/dual_manual_session_test.exe" 0
@if errorlevel 1 exit /b 1
"$build/dual_manual_session_test.exe" 3
@if errorlevel 1 exit /b 1
"$build/dual_manual_session_test.exe" bound-pass
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_combined_preview_test.cpp" "$sourceDir/dual_combined_preview.cpp" /Fe"$build/dual_combined_preview_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_combined_preview_test.exe"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_combined_lua_test.cpp" "$sourceDir/dual_manual_lua.cpp" /Fe"$build/dual_combined_lua_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_combined_lua_test.exe"
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 "$sourceDir/dual_entry_test.cpp" "$sourceDir/dual_entry.cpp" /Fe"$build/dual_entry_test.exe" /Fo"$build/"
@if errorlevel 1 exit /b 1
"$build/dual_entry_test.exe"
@exit /b %errorlevel%
"@
$batchPath=Join-Path $build 'compile-hp-observer.cmd'
[IO.File]::WriteAllText($batchPath,$batch,[Text.Encoding]::ASCII)
$output=(& cmd.exe /d /c $batchPath 2>&1 | Out-String)
[IO.File]::WriteAllText((Join-Path $build 'hp-observer-build.log'),$output)
if ($LASTEXITCODE -ne 0) { throw $output }
Write-Output $output
$prior=$env:PYTHONPATH
try {
 $env:PYTHONPATH='C:/tmp/xp-banking-analysis-deps'
 & python (Join-Path $sourceDir 'dual_hp_probe.py') --dll (Join-Path $build 'dual_hp_observer.dll')
 if ($LASTEXITCODE -ne 0) {throw 'HP observer instruction checks failed.'}
} finally {$env:PYTHONPATH=$prior}
