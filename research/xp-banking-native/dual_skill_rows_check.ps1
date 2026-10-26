param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-skill-rows')
$ErrorActionPreference='Stop'
$build=[IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation){throw 'MSVC x64 compiler required'}
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
# MSVC names anonymous namespaces after the compiled path: mapping this folder
# (/pathmap needs /experimental:deterministic) lays the DLL out the same in every build folder.
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$PSScriptRoot/dual_skill_rows.cpp" "$PSScriptRoot/dual_skill_rows_lua.cpp" "$PSScriptRoot/cbm_build_inputs.cpp" /experimental:deterministic /pathmap:"$PSScriptRoot"=research\xp-banking-native /DCBM_BUILD_INPUTS=%CBM_BUILD_INPUTS% /DCBM_BUILD_ID=%CBM_BUILD_ID% /Fe"$build/dual_skill_rows.dll" /Fo"$build/" /link /MAP:"$build/dual_skill_rows.map"
@exit /b %errorlevel%
"@
$batchPath=Join-Path $build 'build.cmd'
[IO.File]::WriteAllText($batchPath,$batch,[Text.Encoding]::ASCII)
$prior=$env:PYTHONPATH
try{
 $env:PYTHONPATH='C:/tmp/xp-banking-analysis-deps'
 & python (Join-Path $PSScriptRoot 'dual_skill_rows_probe.py') --generate
 if($LASTEXITCODE -ne 0){throw 'Skill row signature generation failed'}
 & cmd.exe /d /c $batchPath
 if($LASTEXITCODE -ne 0){throw 'Skill row adapter build failed'}
 & python (Join-Path $PSScriptRoot 'dual_skill_rows_probe.py') --dll (Join-Path $build 'dual_skill_rows.dll')
 if($LASTEXITCODE -ne 0){throw 'Skill row instruction checks failed'}
}finally{$env:PYTHONPATH=$prior}
