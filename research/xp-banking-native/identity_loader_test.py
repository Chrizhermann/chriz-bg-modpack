"""Execute actual inert/bootstrap Lua using explicit native-host API doubles.

Real profile bytes are placed in synthetic memory. These tests prove loader
ordering, preserved bytes and failure cleanup, not JIT/native game execution.
Independent C++ and Unicorn tests cover typed shims and reviewed PE windows.
"""
from importlib import import_module
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parent


@pytest.fixture(params=["lua51","lua52","luajit21"])
def host(request):
    lua=import_module("lupa."+request.param).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().research=str(ROOT.parent).replace("\\","/")
    lua.execute(r'''
        memory={}; original={}; labels={}; writes=0; patches=0; exposed=0
        protected=true; log={}; nextJIT=0x141000000
        local base,eeex=0x140000000,0x7ff000000000
        local function put(at,value,n)
            for i=0,n-1 do memory[at+i]=value%256;value=math.floor(value/256) end
        end
        local function hex(at,text)
            for i=1,#text,2 do memory[at+(i-1)/2]=tonumber(text:sub(i,i+1),16) end
        end
        local function header(at,timestamp,size)
            put(at,0x5a4d,2);put(at+0x3c,0x100,4);put(at+0x100,0x4550,4)
            put(at+0x104,0x8664,2);put(at+0x108,timestamp,4);put(at+0x150,size,4)
        end
        local ip=dofile(research..'/xp-banking-native/identity_profiles.lua')['2.6']
        local rp=dofile(research..'/xp-banking-native/reset_profiles.lua')['2.6']
        local pp=dofile(research..'/xp-banking-native/party_profiles.lua')['2.6']
        local ap=dofile(research..'/xp-banking-native/award_profiles.lua')['2.6']
        local wp=dofile(research..'/xp-banking-native/writer_profiles.lua')['2.6']
        identityProfiles={fixture=ip};resetProfiles={fixture=rp}
        header(base,ip.gameTimestamp,ip.gameSize);header(eeex,ip.eeexTimestamp,ip.eeexSize)
        for _,e in pairs(ip.entries) do
            local at=(e.module=='game' and base or eeex)+e.rva;hex(at,e.bytes)
            if e.label then labels[e.label]=at end
        end
        hex(base+rp.entry.rva,rp.entry.bytes);hex(base+rp.capRva,rp.capBytes)
        hex(base+rp.createEntry.rva,rp.createEntry.bytes);hex(base+rp.denyRva,rp.denyBytes)
        for _,call in ipairs({rp.removeCall,rp.previewCall}) do
            hex(base+call.caller,call.callerBytes);hex(base+call.target,call.targetBytes)
        end
        removeAt=base+rp.removeCall.site;previewAt=base+rp.previewCall.site
        hex(base+pp.caller,pp.callerBytes);hex(base+pp.target,pp.targetBytes)
        hex(base+ap.rva,ap.bytes)
        hex(base+wp.rva,wp.entryBytes);hex(base+wp.rva+wp.branch,wp.branchBytes)
        hex(base+wp.rva+wp.tail,wp.tailBytes);put(base+wp.rva+wp.tableXP,wp.rva+wp.branch,4)
        writerAt=base+wp.rva+wp.branch
        capAt=base+0x34e71c
        hex(capAt-6,'488BD6498BCDE8');put(capAt+1,(base+rp.capRva-capAt-5)%4294967296,4)
        hex(capAt+5,'4C8D442450488BCE488D542451448BF0')
        local function progression(name)
            local p=dofile(research..'/xp-banking-native/'..name..'.lua')[1]
            for _,f in pairs(p.functions or{})do hex(base+f.rva,f.bytes)end
            for _,f in pairs(p.entries or{})do hex(base+f.rva,f.bytes)end
            return p
        end
        local mp=progression('dual_manual_profiles')
        for _,f in ipairs(mp.choiceCalls)do hex(base+f.rva,f.bytes)end
        hex(base+mp.manualCall.rva,mp.manualCall.bytes);hex(base+mp.contribution.rva,mp.contribution.bytes)
        local cp=progression('dual_combined_profiles');progression('dual_prof_commit_profiles')
        for _,name in ipairs({'nextCalls','getterCalls'})do for _,f in ipairs(cp[name])do hex(base+f.rva,f.bytes)end end
        for _,name in ipairs({'combineCall','firstSpecialCall','untouchedSpecialReplay'})do local f=cp[name];hex(base+f.rva,f.bytes)end
        local ep=progression('dual_entry_profiles');hex(base+ep.eligibilityQuery.rva,ep.eligibilityQuery.bytes)
        local hp=progression('dual_old_hla_profiles')
        put(base+hp.listVtable,base+hp.listDestructor,8)
        for _,f in ipairs(hp.activeCalls)do hex(base+f.contextRva,f.contextBytes)end
        manualAt=base+mp.entries.reset.rva;entryAt=base+ep.entries.click.rva;hlaAt=base+hp.activeCalls[1].rva+1
        for at,b in pairs(memory) do original[at]=b end
        -- Only actual active-provider labels exist. Unprefixed lua_* fails.
        for i,name in ipairs({'Hardcoded_lua_tolstring','Hardcoded_lua_pushstring',
            'Hardcoded_lua_pushboolean','EEex::bStripUUID','EEex::bNoUUID','g_pBaldurChitin'}) do labels[name]=0x500000+i*16 end
        function EEex_ReadU8(at) return memory[at] or 0 end
        local function read(at,n)
            local v=0;for i=n-1,0,-1 do v=v*256+EEex_ReadU8(at+i) end;return v
        end
        function EEex_ReadU16(at) return read(at,2) end
        function EEex_ReadU32(at) return read(at,4) end
        function EEex_Read64(at) return read(at,8) end
        function EEex_Read32(at) local n=read(at,4);return n>=2147483648 and n-4294967296 or n end
        local function cbm_checked(value,min,max)
            assert(type(value)=='number' and value==math.floor(value),'arg #2 must be an integer')
            if value>max then error(('arg #2 (%d) too large (max: %d)'):format(value,max)) end
            if value<min then error(('arg #2 (%d) too small (min: %d)'):format(value,min)) end
            return value
        end
        function EEex_WriteU8(at,b)
            cbm_checked(b,0,255)
            assert(not protected,'code write with protection enabled');memory[at]=b;writes=writes+1
            if failAddress==at then failAddress=nil;error('injected partial write') end
        end
        -- InfinityLoader's EEex_Write8 is int8: code bytes above 127 are refused.
        function EEex_Write8(at,b) EEex_WriteU8(at,cbm_checked(b,-128,127)%256) end
        function EEex_Write32(at,b)
            b=cbm_checked(b,-2147483648,2147483647)%4294967296
            for i=0,3 do EEex_WriteU8(at+i,b%256);b=math.floor(b/256) end
            if failPartyWrite then failPartyWrite=false;error('injected partial party patch') end
        end
        configs={}
        function EEex_Write64(at,n) configs[at]=n end
        function EEex_Malloc() return 0x800000+#log*100 end
        function EEex_Free() end
        function EEex_DisableCodeProtection() protected=false end
        function EEex_EnableCodeProtection() protected=true end
        function EEex_GetImageBase() return base end
        function EEex_TryLabel(name) return labels[name] end
        function EEex_DefineAssemblyLabel(name,n) labels[name]=n end
        function EEex_ClearAssemblyLabel(name) labels[name]=nil end
        function EEex_LoadLibrary(name)
            if name=='EEex.dll' then return eeex end -- existing loaded module
            log[#log+1]='dll';return 0x600000
        end
        function EEex_GetProcAddressInternal(_,name)
            log[#log+1]=name;return 0x700000+#log*16
        end
        function EEex_FlattenTable(t) return t end
        function EEex_StoreBytesAssembly() return {'reviewed original bytes'} end
        function EEex_JITNear() nextJIT=nextJIT+256;return nextJIT end
        function EEex_JITAt(at)
            patches=patches+1;EEex_WriteU8(at,0xe9)
            if failPatch==patches then error('injected partial progression patch')end
        end
        function EEex_JITNearAsLuaFunction(name)
            _G[name]=function() log[#log+1]=name;return true end
        end
        EEex_LuaCallReturnType={Boolean=0,Number=1}
        function EEex_GenLuaCall(name,options)
            -- Invoke the actual callback argument emitters, without claiming
            -- the resulting assembly is executed by this host double.
            for i,argument in ipairs(options.args) do argument(i*8) end
            return {'#ALIGN mov qword ptr ss:[rsp+8],0 #ENDL mov qword ptr ss:[rsp],0 #ENDL '..
                'call #L(Hardcoded_lua_pcallk) #ENDL #ALIGN_END',name}
        end
        function EEex_ExposeToLua(_,name)
            exposed=exposed+1
            if failExpose==exposed then error('injected expose failure') end
            _G[name]=function()
                return 'world','world','1',string.rep('a',32),false,true,true
            end
        end
        function EEex_HookReplaceFunctionMaintainOriginal(at,span)
            assert(CBMBank_IdentityNativeQuery,'identity query must be exposed before patch')
            patches=patches+1
            EEex_WriteU8(at,0xe9)
            if failPatch==patches then error('injected partial entry patch') end
            for i=1,span-1 do EEex_WriteU8(at+i,0xcc) end
        end
        function EEex_HookAfterCall(at)
            patches=patches+1;EEex_WriteU8(at,0xe9)
            if failPatch==patches then error('injected partial cap patch') end
            for i=1,4 do EEex_WriteU8(at+i,0xcc) end
        end
        EEex_Active=true;EEex_GameState_Private_AlreadyInitialized=false
        EEex_Sprite_Private_MarshalHandlers={};EEex_Sprite_LoadedListeners={};EEex_GameState_DestroyedListeners={}
        EEex_Menu_AfterMainFileLoadedListeners={};menuLoads=0
        function EEex_Menu_AddAfterMainFileLoadedListener(fn)
            table.insert(EEex_Menu_AfterMainFileLoadedListeners,fn)
            if failMenuListener then error('injected menu listener failure')end
        end
        function EEex_Menu_LoadFile(name)assert(name=='CBMDOLD');menuLoads=menuLoads+1 end
        EEex_Action_Private_SpriteStartedActionListeners={}
        function EEex_Action_AddSpriteStartedActionListener(fn)
            table.insert(EEex_Action_Private_SpriteStartedActionListeners,fn)
            if failNoticeListener then error('injected notice listener failure')end
        end
        function Infinity_DisplayString(text)log[#log+1]=text end
        function EEex_Sprite_GetSelected()return nil end
        function EEex_Sprite_AddMarshalHandlers(key,exporter,importer)
            EEex_Sprite_Private_MarshalHandlers[key]={exporter=exporter,importer=importer}
        end
        function EEex_Sprite_AddLoadedListener(fn)
            table.insert(EEex_Sprite_LoadedListeners,fn)
            if failLoaded then error('injected listener registration failure') end
        end
        function EEex_GameState_AddDestroyedListener(fn) table.insert(EEex_GameState_DestroyedListeners,fn) end
        function EEex_UDToPtr(actor) return actor.pointer end
        function EEex_GetUDAux(actor) return actor.aux end
        function EEex_Sprite_GetCharacterIndex() return 0 end
        function EEex_GameState_GetGlobalInt() return 0 end
        EngineGlobals={g_pBaldurChitin={m_pObjectGame={pointer=0x987600,m_ruleTables={pointer=0x123400},
            m_sCurrentCampaign={m_pchData={get=function() return 'BG1' end}}}}}
        function assertRestored()
            assert(protected,'protection not restored')
            for at,b in pairs(original) do assert(memory[at]==b,'native byte was not restored') end
        end
        function useIdentityProfile(gameKey,alternateKey)
            local profile=dofile(research..'/xp-banking-native/identity_profiles.lua')[gameKey]
            local build=alternateKey and profile.eeexAlternates[alternateKey] or profile
            header(base,profile.gameTimestamp,profile.gameSize)
            header(eeex,build.eeexTimestamp,build.eeexSize)
            for _,entries in ipairs({profile.entries,build.entries})do
                for _,entry in pairs(entries)do
                    local at=(entry.module=='game' and base or eeex)+entry.rva
                    hex(at,entry.bytes)
                    if entry.label then labels[entry.label]=at end
                end
            end
            identityProfiles={fixture=profile}
            original={};for at,value in pairs(memory)do original[at]=value end
        end
        function bootstrap()
            bank=dofile(research..'/xp-banking-native/bank_bootstrap.lua')
            return bank.Install({researchOnly=true,researchDir=research,dllPath='synthetic.dll',policy='bg1_sod',
                progressionDLLDirectory='synthetic-progression'})
        end
    ''')
    return lua


def test_actual_bootstrap_inert_then_connects_real_modules(host):
    host.execute('''
        local b=dofile(research..'/xp-banking-native/bank_bootstrap.lua')
        assert(not b.installed and writes==0 and #log==0)
        local bank=bootstrap()
        assert(bank.installed and bank.usable==false and bank.experimental)
        assert(protected and #EEex_Sprite_LoadedListeners==1 and #EEex_GameState_DestroyedListeners==1)
        assert(bank.progression and bank.runtime.oldHLAs and CBMDOldEligible and CBMDHLADeliverNative)
        assert(menuLoads==0 and #EEex_Menu_AfterMainFileLoadedListeners==1)
        assert(CBMBank_Status and #EEex_Action_Private_SpriteStartedActionListeners==1)
        local a={pointer=0x123456,aux={},m_baseStats={m_xp=1000,m_flags=0,m_level1=1},
            m_startTypeAI={m_Class=2},m_derivedStats={m_nXP=600000}}
        EEex_Sprite_LoadedListeners[1](a)
        a.m_baseStats.m_xp=600000
        CBMBank_BeforeNativeClamp(a,8000000)
        assert(a.m_derivedStats.m_nXP==161000 and a.m_baseStats.m_xp==600000)
        local handler=EEex_Sprite_Private_MarshalHandlers.CBMBank
        local saved=handler.exporter(a)
        assert(saved.ownerKey==string.rep('a',32) and saved.floor==1000)
        local other={pointer=0x654321,aux={},m_baseStats=a.m_baseStats,m_startTypeAI={m_Class=2}}
        handler.importer(other,saved)
        assert(bank.runtime.Snapshot(other,8000000).activeBank==439000)
    ''')


@pytest.mark.parametrize("failure",["failPatch=1","failPatch=4","failPatch=7","failPatch=8","failPatch=9",
                                     "failPartyWrite=true","failLoaded=true","failExpose=1","failExpose=3","failExpose=4",
                                     "failExpose=7","failAddress=writerAt+7","failAddress=removeAt+2","failAddress=previewAt+3",
                                     "failAddress=manualAt","failAddress=hlaAt","failAddress=entryAt","failMenuListener=true","failNoticeListener=true"])
def test_actual_bootstrap_restores_all_owned_bytes_and_callbacks_on_failure(host,failure):
    host.execute(failure)
    host.execute('''
        local foreign=function() end
        EEex_Sprite_LoadedListeners[1]=foreign
        EEex_GameState_DestroyedListeners[1]=foreign
        local ok,why=pcall(bootstrap)
        assert(not ok and tostring(why):find('restart required'),tostring(why))
        assertRestored()
        assert(bank.failed and not bank.installed)
        assert(EEex_Sprite_Private_MarshalHandlers.CBMBank==nil)
        assert(#EEex_Sprite_LoadedListeners==1 and EEex_Sprite_LoadedListeners[1]==foreign)
        assert(#EEex_GameState_DestroyedListeners==1 and EEex_GameState_DestroyedListeners[1]==foreign)
        assert(#EEex_Menu_AfterMainFileLoadedListeners==0)
        assert(#EEex_Action_Private_SpriteStartedActionListeners==0)
        for name in pairs(_G) do assert(not name:match('^CBMBank_'),'leaked banking callback: '..name) end
        for name in pairs(_G)do assert(not name:match('^CBMD'),'leaked progression callback: '..name)end
        assert(labels['CBMBank::GetXPCap']==nil)
    ''')


@pytest.mark.parametrize("guard",["EEex_GameState_Private_AlreadyInitialized=true",
                                  "EEex_Sprite_Private_MarshalHandlers.CBMBank={foreign=true}",
                                  "memory[capAt+5]=0x90","memory[writerAt+5]=0x90","memory[manualAt]=0x90"])
def test_actual_bootstrap_refuses_late_conflicting_or_modified_host_before_native_calls(host,guard):
    host.execute(guard)
    host.execute('''
        local ok=pcall(bootstrap)
        assert(not ok and writes==0 and #log==0 and protected)
    ''')


@pytest.mark.parametrize("failure",[1,3,6])
def test_identity_installer_own_partial_patch_rollback_and_nonretryable_config(host,failure):
    host.globals().failPatch=failure
    host.execute('''
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        local ok,why=pcall(id.Install,{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles})
        assert(not ok and tostring(why):find('rolled back'))
        assertRestored();assert(not id.installed and id.attempted)
        assert(CBMBank_IdentityNativeQuery==nil and CBMBank_Identity==nil)
        local again,msg=pcall(id.Install,{researchOnly=true})
        assert(not again and tostring(msg):find('restart required'))
    ''')


def test_collection_eeex_12_lifetime_profile_uses_actual_module_and_entries(host):
    host.execute('''
        useIdentityProfile('2.7','collection-1.2')
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        local p,key,game,eeex=id.ResolveProfile(identityProfiles)
        assert(key=='fixture' and game==0x140000000 and eeex==0x7ff000000000)
        assert(p.entries.construct.rva==0xd350 and p.entries.destruct.rva==0xd390)
        assert(identityProfiles.fixture.entries.construct.rva~=p.entries.construct.rva)
        id.Install{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles}
        assert(id.installed and patches==6 and protected)
        assert(memory[eeex+0xd350]==0xe9 and memory[eeex+0xd390]==0xe9)
    ''')


@pytest.mark.parametrize('guard',[
    'memory[0x7ff000000108]=0',
    "labels['EEex::Sprite_Hook_OnDestruct']=labels['EEex::Sprite_Hook_OnDestruct']+1",
])
def test_collection_eeex_12_refuses_unknown_module_or_changed_lifetime_label(host,guard):
    host.execute("useIdentityProfile('2.7','collection-1.2')")
    host.execute(guard)
    host.execute('''
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        local ok=pcall(id.Install,{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles})
        assert(not ok and writes==0 and #log==0 and protected)
    ''')


def test_scroll_chain_offer_is_exact_owned_destructor_and_refuses_later_changes(host):
    host.execute('''
        useIdentityProfile('2.7','collection-1.2')
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        local at=labels['EEex::Sprite_Hook_OnDestruct']
        assert(id.ActorDestroyChain(at)==nil)
        local hook=EEex_HookReplaceFunctionMaintainOriginal
        function EEex_HookReplaceFunctionMaintainOriginal(address,span,label,target)
            hook(address,span,label,target)
            -- Actual upstream shape: five-byte E9 plus two NOPs. The model
            -- does not execute this displacement; native scroll checks do.
            EEex_WriteU8(address+5,0x90);EEex_WriteU8(address+6,0x90)
        end
        id.Install{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles}
        local offer=id.ActorDestroyChain(at)
        assert(offer.schema==1 and offer.entry==at and offer.handler>0)
        assert(offer.original=='4c8bdc49894b08' and offer.replacement=='e9cccccccc9090')
        assert(id.ActorDestroyChain(at+1)==nil)
        offer.handler=0;assert(id.ActorDestroyChain(at).handler>0)
        memory[at+1]=0
        assert(id.ActorDestroyChain(at)==nil)
    ''')
