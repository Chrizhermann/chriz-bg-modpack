param([string]$BuildDir='C:/tmp/campaign-xp-banking-20261009/research-bundle')
$ErrorActionPreference='Stop'
$build=[System.IO.Path]::GetFullPath($BuildDir)
New-Item -ItemType Directory -Force -Path $build | Out-Null
# These build/execute offline typed native harnesses, never the game. /EHs is
# deliberate: extern-C exports forward potentially throwing C++ engine methods.
& (Join-Path $PSScriptRoot 'identity_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'reset_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'award_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'writer_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'dual_hp_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'dual_native_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'dual_prof_commit.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'dual_skill_rows_check.ps1') -BuildDir $build
& (Join-Path $PSScriptRoot 'dual_old_hla.ps1') -BuildDir $build
$research=Split-Path $PSScriptRoot -Parent
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
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'dual_retired_menu.menu') -Destination $menu
$hashes['resources/CBMDOLD.menu']=(Get-FileHash -Algorithm SHA256 -LiteralPath $menu).Hash.ToLowerInvariant()
$startup=Join-Path $build 'resources/M_CBMBNK.lua'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'M_CBMBNK.lua') -Destination $startup
$hashes['resources/M_CBMBNK.lua']=(Get-FileHash -Algorithm SHA256 -LiteralPath $startup).Hash.ToLowerInvariant()
$manifest=@{researchOnly=$true;usableBankingComponent=$false;nativePlaytestRequired=$true;createdUtc=[DateTime]::UtcNow.ToString('o');files=$hashes}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $build 'research-build.json') -Encoding UTF8
Write-Output 'Built inert research bundle. Nothing installed or registered; no native game acceptance claimed.'
