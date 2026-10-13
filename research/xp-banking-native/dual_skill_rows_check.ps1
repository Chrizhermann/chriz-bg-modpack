param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/native-skill-rows')
$ErrorActionPreference='Stop'
$build=[IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
$vswhere='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation){throw 'MSVC x64 compiler required'}
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHs /W4 /WX /O2 /LD "$PSScriptRoot/dual_skill_rows.cpp" "$PSScriptRoot/dual_skill_rows_lua.cpp" /Fe"$build/dual_skill_rows.dll" /Fo"$build/" /link /MAP:"$build/dual_skill_rows.map"
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
