-- Private disposable-trial loader. Copy only after the exact trial is approved.
-- The game must start with its working directory set to that disposable folder.
if CBMBankTrialAttempted then return end
CBMBankTrialAttempted=true
if EEex_Active~=true then
 print("[CBM campaign XP] Trial not started: EEex is unavailable.")
 return
end
local root="cbm-bank-trial"
local ok,result=pcall(function()
 local bootstrap=assert(dofile(root.."/research/xp-banking-native/bank_bootstrap.lua"))
 return bootstrap.Install{researchOnly=true,researchDir=root.."/research",
  dllPath=root.."/cbmbank_identity.dll",progressionDLLDirectory=root,policy="bg1_sod"}
end)
if not ok then
 print("[CBM campaign XP] Trial startup failed; stop this trial and review its log: "..tostring(result))
else
 print("[CBM campaign XP] Private trial initialized. No native acceptance is implied.")
end
