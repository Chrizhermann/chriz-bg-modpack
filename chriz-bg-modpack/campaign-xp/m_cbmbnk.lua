-- Experimental, unreleased component 650/651. Native capability/signature checks
-- remain mandatory. Startup runs at EEex initialization: the game object and its
-- rule tables exist from then on, and no actor has loaded yet. When this file
-- loads (UI includes) the game object does not exist yet (lab, 2026-10-13).
if CBMBankStartupAttempted then return end
CBMBankStartupAttempted=true
local started=false
local function start()
 if started then return end
 started=true
 local ok,result=pcall(function()
  assert(EEex_Active==true,"EEex is unavailable; launch using InfinityLoader")
  Infinity_DoFile("CBMBKCFG")
  assert(type(CBMBank_Config)=="table" and CBMBank_Config.schema==1,"Campaign XP configuration is missing")
  local root="chriz-bg-modpack/campaign-xp"
  local bootstrap=assert(dofile(root.."/runtime/xp-banking-native/bank_bootstrap.lua"))
  return bootstrap.Install{researchOnly=true,researchDir=root.."/runtime",
   dllPath=root.."/native/cbmbank_identity.dll",progressionDLLDirectory=root.."/native",
   policy=CBMBank_Config.policy}
 end)
 if not ok then
  print("[CBM campaign XP] Startup failed; stop and review the log before playing: "..tostring(result))
  -- Installing 650 routed Imoen's Spellhold XP and the owned SoA recruitment
  -- catch-up through the bank. Without a running bank they keep their pre-650
  -- behavior: the native XP value and a plain ChangeStat SET. Names that a
  -- partial startup still owns are left alone.
  local function setXP(sprite,target)
   EEex_Action_ExecuteResponseStringOnAIBaseInstantly(string.format("ChangeStat(Myself,XP,%d,SET)",target),sprite)
  end
  if CBMBank_ActiveXP==nil then CBMBank_ActiveXP=function(sprite) return sprite.m_baseStats.m_xp end end
  if CBMBank_ImoenXPSet==nil then CBMBank_ImoenXPSet=setXP end
  if CBMBank_Catchup==nil then
   CBMBank_Catchup=function(sprite,target)
    setXP(sprite,target)
    EEex_Sprite_SetLocalInt(sprite,"CBM_SoARecruitXP",1)
   end
  end
 else
  print("[CBM campaign XP] Experimental component initialized. Game testing is still pending.")
 end
end
-- Scroll casting (430) chains onto the bank's actor lifetime hook from an
-- initialized listener that EEex registered before this file loaded; it calls
-- CBMBank_Start first so the bank still installs before it.
CBMBank_Start=start
if EEex_Active==true and type(EEex_GameState_AddInitializedListener)=="function" then
 EEex_GameState_AddInitializedListener(start)
else
 -- Without EEex nothing can start; report it now and keep the pre-650 behavior.
 start()
end
