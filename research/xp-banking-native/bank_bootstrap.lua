-- UNINSTALLED research bootstrap. Loading this file performs no registrations,
-- writes or native calls. This is an offline candidate assembly, not a claim of
-- completed native playtest acceptance or an installable released component.
local M={experimental=true,usable=false}
local ownedGlobals={"CBMBank_Identity","CBMBank_IdentityNativeQuery","CBMBank_IdentityConfigure",
    "CBMBank_Reset","CBMBank_PrepareDual","CBMBank_CompleteDual","CBMBank_UncertainDual",
    "CBMBank_ResetConfigure","CBMBank_ResetNativeQuery","CBMBank_ResetNativeCap",
    "CBMBank_CaptureDualPreview","CBMBank_ResetNativePreviewQuery",
    "CBMBank_OnPartyReady","CBMBank_PartyConfigure","CBMBank_BeforeNativeClamp","CBMBank_Research",
    "CBMBank_Award","CBMBank_BeforeAward","CBMBank_CompleteAward","CBMBank_UncertainAward",
    "CBMBank_AwardConfigure","CBMBank_AwardNativeQuery",
    "CBMBank_Writer","CBMBank_BeforeWrite","CBMBank_CompleteWrite","CBMBank_UncertainWrite",
    "CBMBank_WriterConfigure","CBMBank_WriterNativeQuery","CBMBank_WriterNativePlan","CBMBank_WriterNativeOwnedSet",
    "CBMBank_ActiveXP","CBMBank_ImoenXPSet","CBMBank_Catchup","CBMBank_Status"}
local function verify(at,hex)
    assert(type(hex)=="string" and #hex%2==0,"Invalid native profile bytes")
    for i=1,#hex,2 do
        if EEex_ReadU8(at+(i-1)/2)~=tonumber(hex:sub(i,i+1),16) then
            -- Name the place and what is there, so a log shows which hook got there first.
            local found={};for j=0,#hex/2-1 do found[#found+1]=("%02X"):format(EEex_ReadU8(at+j)) end
            local base=EEex_GetImageBase()
            local size=EEex_ReadU32(base+EEex_ReadU32(base+0x3C)+0x50)
            local where=(at>=base and at<base+size) and ("game+0x%X"):format(at-base) or ("0x%X"):format(at)
            error(("Native bootstrap ABI mismatch at %s (expected %s, found %s); no hooks installed")
                :format(where,hex:upper(),table.concat(found)),2)
        end
    end
end
local function choose(profiles,timestamp,size)
    local selected,key
    for name,p in pairs(profiles) do
        if p.gameTimestamp==timestamp and p.gameSize==size then
            assert(not selected,"Ambiguous native bootstrap profile");selected,key=p,name
        end
    end
    assert(selected,"Unreviewed native bootstrap build");return selected,key
end
function M.Install(options)
    assert(not M.attempted,"Research bootstrap already attempted; restart required")
    assert(type(options)=="table" and options.researchOnly==true,"Explicit research-only install required")
    assert(type(options.researchDir)=="string" and type(options.dllPath)=="string")
    assert(type(options.progressionDLLDirectory)=="string","Explicit private progression DLL directory required")
    assert(options.policy=="bg1_sod" or options.policy=="bg1_sod_soa","Unknown banking policy")
    assert(EEex_Active==true,"EEex is required")
    -- Actual EEex startup state, not a caller assertion. The flag is set once
    -- after engine Lua initialization; a main-menu/hot-load is too late.
    assert(EEex_GameState_Private_AlreadyInitialized==false,
        "Install must run during initial EEex startup before actors can load")
    for _,name in ipairs(ownedGlobals) do assert(_G[name]==nil,"Bank namespace already owned: "..name) end
    for _,name in ipairs({"EEex_GetImageBase","EEex_ReadU8","EEex_ReadU16","EEex_ReadU32","EEex_Read32",
        "EEex_WriteU8","EEex_DisableCodeProtection","EEex_EnableCodeProtection","EEex_TryLabel",
        "EEex_DefineAssemblyLabel","EEex_ClearAssemblyLabel","EEex_Sprite_AddMarshalHandlers",
        "EEex_Sprite_AddLoadedListener","EEex_GameState_AddDestroyedListener"}) do
        assert(type(_G[name])=="function","Missing native startup capability: "..name)
    end
    assert(type(EEex_Sprite_Private_MarshalHandlers)=="table" and
        EEex_Sprite_Private_MarshalHandlers.CBMBank==nil,"Bank marshal handler already owned")
    assert(type(EEex_Sprite_LoadedListeners)=="table" and type(EEex_GameState_DestroyedListeners)=="table",
        "Reviewed listener storage unavailable")
    local root=options.researchDir:gsub("[/\\]+$","")
    local function load(name) return assert(dofile(root.."/"..name)) end
    local callbacks=load("xp-banking-native/callback_abi.lua")
    local identity=load("xp-banking-native/identity_hooks.lua")
    local reset=load("xp-banking-native/reset_hooks.lua")
    local party=load("xp-banking-native/party_hooks.lua")
    local award=load("xp-banking-native/award_hooks.lua")
    local writer=load("xp-banking-native/writer_hooks.lua")
    local cap=load("xp-banking-native/cap_hook.lua")
    local runtime=load("xp-banking-native/bank_runtime.lua")
    local compat=load("xp-banking-native/bank_compat.lua")
    local progression=load("xp-banking-native/dual_bootstrap.lua")
    local notices=load("xp-banking-native/bank_notice.lua")
    local record=load("xp-banking-native/bank_record.lua")
    local ip=load("xp-banking-native/identity_profiles.lua")
    local rp=load("xp-banking-native/reset_profiles.lua")
    local pp=load("xp-banking-native/party_profiles.lua")
    local ap=load("xp-banking-native/award_profiles.lua")
    local wp=load("xp-banking-native/writer_profiles.lua")
    local base=EEex_GetImageBase()
    assert(EEex_ReadU16(base)==0x5A4D,"Invalid game module")
    local pe=base+EEex_ReadU32(base+0x3C)
    assert(EEex_ReadU32(pe)==0x4550 and EEex_ReadU16(pe+4)==0x8664,"Not a Win64 PE")
    local stamp,size=EEex_ReadU32(pe+8),EEex_ReadU32(pe+0x50)
    local id,key,identityGame,eeex=identity.ResolveProfile(ip)
    assert(identityGame==base,"Native game identity changed during startup")
    local re=choose(rp,stamp,size)
    local pa=choose(pp,stamp,size)
    local aw=choose(ap,stamp,size)
    local wr=choose(wp,stamp,size)
    local ranges={}
    local function remember(at,count)
        local bytes={};for i=0,count-1 do bytes[i]=EEex_ReadU8(at+i) end
        ranges[#ranges+1]={at=at,count=count,bytes=bytes}
    end
    for _,entry in pairs(id.entries) do
        local at=(entry.module=="game" and base or eeex)+entry.rva
        if entry.label then assert(EEex_TryLabel(entry.label)==at,"Native lifetime label mismatch")end
        verify(at,entry.bytes);remember(at,entry.span)
    end
    verify(base+re.entry.rva,re.entry.bytes);verify(base+re.capRva,re.capBytes)
    remember(base+re.entry.rva,re.entry.span)
    verify(base+re.createEntry.rva,re.createEntry.bytes);remember(base+re.createEntry.rva,re.createEntry.span)
    verify(base+re.denyRva,re.denyBytes)
    for _,call in ipairs({re.removeCall,re.previewCall}) do
        verify(base+call.caller,call.callerBytes);verify(base+call.target,call.targetBytes)
        remember(base+call.site,5)
    end
    verify(base+pa.caller,pa.callerBytes);verify(base+pa.target,pa.targetBytes)
    remember(base+pa.site,5)
    verify(base+aw.rva,aw.bytes);remember(base+aw.rva,aw.span)
    verify(base+wr.rva,wr.entryBytes);verify(base+wr.rva+wr.branch,wr.branchBytes)
    verify(base+wr.rva+wr.tail,wr.tailBytes)
    assert(EEex_ReadU32(base+wr.rva+wr.tableXP)==wr.rva+wr.branch,"Native stat44 dispatch changed")
    remember(base+wr.rva+wr.branch,#wr.branchBytes/2)
    -- These are the precise call RVAs independently checked by check_cap.py;
    -- no installer-side loader database modification is required.
    local capRvas={["2.6"]=0x34E71C,["2.7"]=0x34ED5C}
    assert(capRvas[key],"Native cap call not reviewed")
    local capAt,capTarget=base+capRvas[key],base+re.capRva
    verify(capAt-6,"488BD6498BCD")
    verify(capAt+5,"4C8D442450488BCE488D542451448BF0")
    assert(EEex_ReadU8(capAt)==0xE8 and capAt+5+EEex_Read32(capAt+1)==capTarget,"Unexpected native cap target")
    remember(capAt,5)
    local dual=progression.Preflight(load,base,stamp,size,options.progressionDLLDirectory,remember)
    local labels={["CBMBank::CheckStatsChangeGetXPCap"]=capAt,["CBMBank::GetXPCap"]=capTarget}
    local priorLabels={}
    for name,value in pairs(labels) do
        priorLabels[name]=EEex_TryLabel(name)
        assert(priorLabels[name]==nil or priorLabels[name]==value,"Bank cap label already owned")
    end
    local account=load("xp-banking/native_account.lua")
    local wire=load("xp-banking/cbmbank_store.lua")
    local rewardReceipts=load("xp-banking-native/dual_reward_receipts.lua")
    runtime.Configure(load("xp-banking/cbmbank_policy.lua"),account,wire,options.policy,rewardReceipts)
    local active=false
    local loaded=function(sprite)
        if active then local ok,why=pcall(runtime.OnLoaded,sprite);if not ok then runtime.Report(why) end end
    end
    local destroyed=function() if active then runtime.ResetResourceCache() end end
    local function removeOwn(list,fn)
        for i=#list,1,-1 do if list[i]==fn then table.remove(list,i) end end
    end
    M.attempted=true
    local ok,why=pcall(function()
        for name,value in pairs(labels) do EEex_DefineAssemblyLabel(name,value) end
        identity.Install({researchOnly=true,dllPath=options.dllPath,profiles=ip})
        reset.Install({researchOnly=true,dllPath=options.dllPath,profiles=rp,runtime=runtime,callbacks=callbacks})
        party.Install({researchOnly=true,dllPath=options.dllPath,profiles=pp,runtime=runtime,resetHooks=reset})
        award.Install({researchOnly=true,dllPath=options.dllPath,profiles=ap,runtime=runtime,callbacks=callbacks})
        writer.Install({researchOnly=true,dllPath=options.dllPath,profiles=wp,runtime=runtime,callbacks=callbacks})
        compat.Install(runtime)
        cap.Install({researchOnly=true,snapshot=runtime.Snapshot,report=runtime.Report,callbacks=callbacks})
        progression.Install(dual,{runtime=runtime,wire=wire,account=account,rewardReceipts=rewardReceipts,
            identityDLLPath=options.dllPath,callbacks=callbacks})
        notices.Install{researchOnly=true,runtime=runtime,reset=reset}
        record.Install{runtime=runtime,reset=reset}
        -- Register only after all native boundaries exist. These real EEex APIs
        -- append/store callbacks synchronously; no actor is loaded by them.
        EEex_Sprite_AddMarshalHandlers(runtime.key,runtime.Export,runtime.Import)
        EEex_Sprite_AddLoadedListener(loaded)
        EEex_GameState_AddDestroyedListener(destroyed)
        runtime.registered=true;active=true
    end)
    if not ok then
        active=false
        record.Remove()
        notices.Remove()
        local handler=EEex_Sprite_Private_MarshalHandlers[runtime.key]
        if handler and handler.exporter==runtime.Export and handler.importer==runtime.Import then
            EEex_Sprite_Private_MarshalHandlers[runtime.key]=nil
        end
        removeOwn(EEex_Sprite_LoadedListeners,loaded)
        removeOwn(EEex_GameState_DestroyedListeners,destroyed)
        local restored,restoreWhy=pcall(function()
            EEex_DisableCodeProtection()
            for _,r in ipairs(ranges) do for i=0,r.count-1 do
                if EEex_ReadU8(r.at+i)~=r.bytes[i] then EEex_WriteU8(r.at+i,r.bytes[i]) end
            end end
        end)
        EEex_EnableCodeProtection()
        if restored then
            progression.Cleanup(dual)
            for _,name in ipairs(ownedGlobals) do _G[name]=nil end
            for name in pairs(labels) do
                if priorLabels[name] then EEex_DefineAssemblyLabel(name,priorLabels[name]) else EEex_ClearAssemblyLabel(name) end
            end
        end
        M.failed=true
        assert(restored,"Bank bootstrap rollback failed; restart required: "..tostring(restoreWhy)..
            " (after install failure: "..tostring(why)..")")
        error("Bank research bootstrap rolled back; restart required: "..tostring(why))
    end
    M.installed=true;M.runtime=runtime;M.identity=identity;M.reset=reset;M.party=party;M.cap=cap;M.award=award;M.writer=writer;M.compat=compat
    M.progression=dual
    M.notices=notices
    M.record=record
    _G.CBMBank_Research=M
    return M
end
return M
