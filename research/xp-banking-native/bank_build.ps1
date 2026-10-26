param([Parameter(Mandatory=$true)][string]$BuildDir)
$ErrorActionPreference='Stop'
$build=[System.IO.Path]::GetFullPath($BuildDir)
# One build per folder. --capture claims a new or empty $build, freezes the
# research sources into $build/src and hashes every native input there; every
# check below runs from that copy, and each packaged DLL embeds the digest of
# its inputs and this build's identifier (cbm_build_inputs.cpp). Only this run
# holds the secret --record needs, so only it can describe what it compiled,
# once and after every check passed: a record needs one whole build.
$sync=Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'tools/sync_campaign_xp.py'
$random=New-Object byte[] 32
$generator=[System.Security.Cryptography.RandomNumberGenerator]::Create()
try {$generator.GetBytes($random)} finally {$generator.Dispose()}
$secret=-join ($random | ForEach-Object {$_.ToString('x2')})
function Invoke-Sync([string]$step) {
    $env:CBM_BUILD_SECRET=$secret
    try {& python -I $sync $step $build} finally {Remove-Item Env:CBM_BUILD_SECRET -ErrorAction SilentlyContinue}
    if($LASTEXITCODE -ne 0){throw "Native build $step failed."}
}
Invoke-Sync '--capture'
$capture=Get-Content -Raw -LiteralPath (Join-Path $build 'native-inputs.json') | ConvertFrom-Json
$sources=Join-Path $build 'src/research/xp-banking-native'
# These build/execute offline typed native harnesses, never the game. /EHs is
# deliberate: extern-C exports forward potentially throwing C++ engine methods.
# A builder of a packaged DLL embeds the digest captured for that DLL. cl and
# link also take options from the environment; each check runs without them,
# so that only the frozen scripts decide how a DLL compiles.
$injected='CL','_CL_','LINK','_LINK_'
function Invoke-Check([string]$script) {
    $saved=@{}
    foreach($name in $injected){$saved[$name]=[Environment]::GetEnvironmentVariable($name);[Environment]::SetEnvironmentVariable($name,$null)}
    $env:CBM_BUILD_INPUTS=[string]$capture.embed.$script
    $env:CBM_BUILD_ID=$capture.build
    try {& (Join-Path $sources $script) -BuildDir $build}
    finally {
        Remove-Item Env:CBM_BUILD_INPUTS,Env:CBM_BUILD_ID -ErrorAction SilentlyContinue
        foreach($name in $injected){[Environment]::SetEnvironmentVariable($name,$saved[$name])}
    }
}
Invoke-Check 'identity_check.ps1'
Invoke-Check 'reset_check.ps1'
Invoke-Check 'award_check.ps1'
Invoke-Check 'writer_check.ps1'
Invoke-Check 'dual_hp_check.ps1'
Invoke-Check 'dual_native_check.ps1'
Invoke-Check 'dual_prof_commit.ps1'
Invoke-Check 'dual_skill_rows_check.ps1'
Invoke-Check 'dual_old_hla.ps1'
# Record how the six DLLs were built: the toolchain the scripts above resolved,
# and per DLL its script, compiled sources and local headers as frozen above
# (native-build.json; refused if the build rewrote an input or a DLL does not
# embed this build and its inputs; tools/sync_campaign_xp.py checks it and keeps
# it). Files the probes regenerated return to the checkout where it still has
# them as frozen.
$installation=& 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe' -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation){throw 'MSVC x64 tools unavailable.'}
$vcvars=Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$batch=@"
@call "$vcvars" >nul
@if errorlevel 1 exit /b 1
@cl 2>&1 | findstr /b /c:"Microsoft (R)"
@link /? 2>&1 | findstr /b /c:"Microsoft (R)"
@ml64 /? 2>&1 | findstr /b /c:"Microsoft (R)"
@echo VCToolsVersion=%VCToolsVersion%
@echo WindowsSDKVersion=%WindowsSDKVersion%
@echo UCRTVersion=%UCRTVersion%
@exit /b 0
"@
$batchPath=Join-Path $build 'toolchain.cmd'
[IO.File]::WriteAllText($batchPath,$batch,[Text.Encoding]::ASCII)
$toolchain=(& cmd.exe /d /c $batchPath 2>&1 | Out-String)
if($LASTEXITCODE -ne 0){throw "Toolchain capture failed: $toolchain"}
[IO.File]::WriteAllText((Join-Path $build 'toolchain.txt'),$toolchain)
Invoke-Sync '--record'
$research=Join-Path $build 'src/research'
$files=@(
    'xp-banking-native/callback_abi.lua',
    'xp-banking-native/bank_bootstrap.lua','xp-banking-native/identity_hooks.lua',
    'xp-banking-native/identity_profiles.lua','xp-banking-native/reset_hooks.lua',
    'xp-banking-native/reset_profiles.lua','xp-banking-native/party_hooks.lua',
    'xp-banking-native/party_profiles.lua','xp-banking-native/cap_hook.lua',
    'xp-banking-native/award_hooks.lua','xp-banking-native/award_profiles.lua',
    'xp-banking-native/writer_hooks.lua','xp-banking-native/writer_profiles.lua',
    'xp-banking-native/bank_compat.lua','xp-banking-native/bank_notice.lua',
    'xp-banking-native/bank_record.lua',
    'xp-banking-native/bank_runtime.lua','xp-banking-native/dual_reward_receipts.lua',
    'xp-banking-native/dual_bootstrap.lua','xp-banking-native/dual_manual_hooks.lua',
    'xp-banking-native/dual_manual_profiles.lua','xp-banking-native/dual_manual_receipts.lua',
    'xp-banking-native/dual_manual_ledger.lua','xp-banking-native/dual_combined_hooks.lua',
    'xp-banking-native/dual_combined_profiles.lua','xp-banking-native/dual_prof_commit_profiles.lua',
    'xp-banking-native/dual_rules_bridge.lua','xp-banking-native/dual_skill_rows_bridge.lua',
    'xp-banking-native/dual_old_hla.lua','xp-banking-native/dual_old_hla_profiles.lua',
    'xp-banking-native/dual_old_hla_hooks.lua','xp-banking-native/dual_old_hla_receipts.lua',
    'xp-banking-native/dual_retired_picker.lua','xp-banking-native/dual_retired_rows.lua',
    'xp-banking-native/dual_retired_flow.lua','xp-banking-native/dual_retired_controller.lua',
    'xp-banking-native/dual_entry_hooks.lua','xp-banking-native/dual_entry_profiles.lua',
    'xp-banking/cbmbank_policy.lua','xp-banking/native_account.lua','xp-banking/cbmbank_store.lua')
$hashes=@{}
foreach($relative in $files) {
    $destination=Join-Path (Join-Path $build 'research') $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
    Copy-Item -LiteralPath (Join-Path $research $relative) -Destination $destination
    $hashes[$relative]=(Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
}
foreach($dll in @('cbmbank_identity.dll','dual_hp_observer.dll','dual_native_proficiency.dll','dual_prof_commit.dll','dual_skill_rows.dll','dual_old_hla.dll')) {
    $hashes[$dll]=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $build $dll)).Hash.ToLowerInvariant()
}
New-Item -ItemType Directory -Force -Path (Join-Path $build 'resources') | Out-Null
$menu=Join-Path $build 'resources/CBMDOLD.menu'
Copy-Item -LiteralPath (Join-Path $sources 'dual_retired_menu.menu') -Destination $menu
$hashes['resources/CBMDOLD.menu']=(Get-FileHash -Algorithm SHA256 -LiteralPath $menu).Hash.ToLowerInvariant()
$startup=Join-Path $build 'resources/M_CBMBNK.lua'
Copy-Item -LiteralPath (Join-Path $sources 'M_CBMBNK.lua') -Destination $startup
$hashes['resources/M_CBMBNK.lua']=(Get-FileHash -Algorithm SHA256 -LiteralPath $startup).Hash.ToLowerInvariant()
$manifest=@{researchOnly=$true;usableBankingComponent=$false;nativePlaytestRequired=$true;createdUtc=[DateTime]::UtcNow.ToString('o');files=$hashes}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $build 'research-build.json') -Encoding UTF8
Write-Output 'Built inert research bundle. Nothing installed or registered; no native game acceptance claimed.'
