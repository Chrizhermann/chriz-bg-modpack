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
        memory={}; original={}; labels={}; writes=0; patches=0; exposed=0; nativeFallbacks=0
        nativeEnded=0; nativeKept=0; nativeKeptList=''; nativeReplaced=false; acks={}
        protected=true; log={}; nextJIT=0x141000000; heap=0x800000; procs={}
        images={}; protections={}; granules={}; flushes={}; protects=0; lifetimeAt={}
        local base,eeex=0x140000000,0x7ff000000000
        gameBase,eeexBase=base,eeex
        local function put(at,value,n)
            for i=0,n-1 do memory[at+i]=value%256;value=math.floor(value/256) end
        end
        local function hex(at,text)
            for i=1,#text,2 do memory[at+(i-1)/2]=tonumber(text:sub(i,i+1),16) end
        end
        local function header(at,timestamp,size)
            put(at,0x5a4d,2);put(at+0x3c,0x100,4);put(at+0x100,0x4550,4)
            put(at+0x104,0x8664,2);put(at+0x108,timestamp,4);put(at+0x150,size,4)
            images[at]=size
        end
        -- Windows-like address space: both images plus the pages VirtualAlloc
        -- placed. EEex.dll's code stays PAGE_EXECUTE_READ unless VirtualProtect
        -- changes it; EEex_DisableCodeProtection covers only the game image.
        local PAGE,GRANULE=4096,0x10000
        local function imageAt(at)
            for start,size in pairs(images) do if at>=start and at<start+size then return start end end
        end
        function protectionAt(at)
            return protections[at-at%PAGE] or (imageAt(at)==eeex and 0x20 or nil)
        end
        local ip=dofile(research..'/xp-banking-native/identity_profiles.lua')['2.6']
        local rp=dofile(research..'/xp-banking-native/reset_profiles.lua')['2.6']
        local pp=dofile(research..'/xp-banking-native/party_profiles.lua')['2.6']
        local ap=dofile(research..'/xp-banking-native/award_profiles.lua')['2.6']
        local wp=dofile(research..'/xp-banking-native/writer_profiles.lua')['2.6']
        identityProfiles={fixture=ip};resetProfiles={fixture=rp}
        header(base,ip.gameTimestamp,ip.gameSize);header(eeex,ip.eeexTimestamp,ip.eeexSize)
        for slot,e in pairs(ip.entries) do
            local at=(e.module=='game' and base or eeex)+e.rva;hex(at,e.bytes);lifetimeAt[slot]=at
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
            local image=imageAt(at)
            if image==base then assert(not protected,'code write with protection enabled')
            elseif image or granules[at-at%GRANULE] then
                local protection=protectionAt(at)
                assert(protection==0x04 or protection==0x40,'write to a read-only native page')
            end
            memory[at]=b;writes=writes+1
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
        function EEex_Write64(at,n) configs[at]=n;put(at,n,8) end
        function EEex_Malloc(n) local at=heap;heap=heap+4096;return at end
        function EEex_Free() end
        function EEex_DisableCodeProtection() protected=false end
        function EEex_EnableCodeProtection() protected=true end
        function EEex_GetImageBase() return base end
        function EEex_TryLabel(name) return labels[name] end
        function EEex_DefineAssemblyLabel(name,n) labels[name]=n end
        function EEex_ClearAssemblyLabel(name) labels[name]=nil end
        -- kernel32 as the identity loader's helpers call it: each stub loads its
        -- argument block into rbx ([0] address, [8] size, [16] protection) and
        -- stores results at [24] and [32].
        local kernel,KERNEL={},0x650000
        function kernel.VirtualAlloc(cell)
            local at=read(cell,8);local granule=at-at%GRANULE
            local free=granule>=GRANULE and granule<0x7fffffff0000 and not granules[granule]
                and not imageAt(granule) and not imageAt(granule+PAGE-1) and not (reserved and reserved(granule))
            if free then granules[granule]=true;protections[granule]=0x04 end
            put(cell+24,free and granule or 0,8)
        end
        function kernel.VirtualProtect(cell)
            local at,size,protection=read(cell,8),read(cell+8,8),read(cell+16,4)
            protects=protects+1
            local ok=failProtect~=protects and size>0
            for page=at-at%PAGE,at+size-1,PAGE do ok=ok and protectionAt(page)~=nil end
            if ok then
                put(cell+32,protectionAt(at),4)
                for page=at-at%PAGE,at+size-1,PAGE do protections[page]=protection end
            end
            put(cell+24,ok and 1 or 0,4)
        end
        function kernel.GetCurrentProcess() end
        function kernel.FlushInstructionCache(cell)
            flushes[#flushes+1]={at=read(cell,8),size=read(cell+8,8)};put(cell+24,1,4)
        end
        local exportAt,kernelAt={},{}
        for i,name in ipairs({'VirtualAlloc','VirtualProtect','GetCurrentProcess','FlushInstructionCache'}) do
            exportAt[name]=KERNEL+i*16;kernelAt[KERNEL+i*16]=kernel[name]
        end
        function EEex_LoadLibrary(name)
            if name=='EEex.dll' then return eeex end -- existing loaded module
            if name=='kernel32.dll' then return KERNEL end
            log[#log+1]='dll';return 0x600000
        end
        function EEex_GetProcAddressInternal(module,name)
            if module==KERNEL then return exportAt[name] end
            log[#log+1]=name;procs[name]=0x700000+#log*16;return procs[name]
        end
        function EEex_FlattenTable(t) return t end
        function EEex_StoreBytesAssembly() return {'reviewed original bytes'} end
        function EEex_JITNear() nextJIT=nextJIT+256;return nextJIT end
        -- EEex assembles hook jumps toward the pages EEex_JITNear allocates
        -- beside the game. AsmJit cannot encode a jump beyond rel32 reach and
        -- EEex_JITAt discards that error, leaving the site unchanged. The
        -- unwritten knob models the same silent failure for a reachable site.
        local function jumpAt(at,opcode,to,span,failure)
            patches=patches+1
            local delta=to-(at+5)
            if delta<-2147483648 or delta>2147483647 or unwritten==at then return end
            EEex_WriteU8(at,opcode)
            if failPatch==patches then error(failure) end
            delta=delta%4294967296
            for i=1,4 do EEex_WriteU8(at+i,delta%256);delta=math.floor(delta/256) end
            for i=5,span-1 do EEex_WriteU8(at+i,0x90) end
        end
        function EEex_JITAt(at,assembly)
            local call=type(assembly)=='table' and assembly[1]=='call short '
            local to=type(assembly)=='table' and type(assembly[2])=='number' and assembly[2] or EEex_JITNear()
            jumpAt(at,call and 0xe8 or 0xe9,to,5,'injected partial progression patch')
        end
        function EEex_JITNearAsLuaFunction(name,assembly)
            -- A stub runs the kernel32 calls it assembles on the argument block it loads into rbx.
            local cell,calls=nil,{}
            for i,part in ipairs(type(assembly)=='table' and assembly or {}) do
                local before=assembly[i-1]
                if type(part)=='number' and type(before)=='string' then
                    if before:match('mov rbx, $') then cell=part
                    elseif before:match('call $') and kernelAt[part] then calls[#calls+1]=kernelAt[part] end
                end
            end
            _G[name]=function()
                log[#log+1]=name
                for _,call in ipairs(calls) do call(cell) end
                return true
            end
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
            _G[name]=function(...)
                -- CBMA_LuaFallbacks pushes its total, last reasons, ended and kept
                -- counts and the kept list as text.
                if name=='CBMBank_AwardNativeFallbacks' then
                    return tostring(nativeFallbacks),'5','0',tostring(nativeEnded),tostring(nativeKept),nativeKeptList
                end
                -- CBMI_LuaAckReplaced clears the queried lifetime's replaced-word note.
                if name=='CBMBank_IdentityNativeAckReplaced' then acks[#acks+1]={...};nativeReplaced=false;return true end
                return 'world','world','1',string.rep('a',32),false,true,true,nativeReplaced
            end
        end
        function EEex_HookReplaceFunctionMaintainOriginal(at,span,label,target)
            assert(CBMBank_IdentityNativeQuery,'identity query must be exposed before patch')
            labels[label]=EEex_JITNear()
            -- EEex's shim: jmp qword ptr [rip+2], two filler bytes, the target.
            local shim=EEex_JITNear();hex(shim,'ff2502000000cccc');put(shim+8,target,8)
            jumpAt(at,0xe9,shim,span,'injected partial entry patch')
        end
        function EEex_HookAfterCall(at)
            jumpAt(at,0xe9,EEex_JITNear(),5,'injected partial cap patch')
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
            for page,protection in pairs(protections) do
                assert(imageAt(page)~=eeex or protection==0x20,'EEex code page left writable')
            end
        end
        function useIdentityProfile(gameKey,alternateKey)
            local profile=dofile(research..'/xp-banking-native/identity_profiles.lua')[gameKey]
            local build=alternateKey and profile.eeexAlternates[alternateKey] or profile
            header(base,profile.gameTimestamp,profile.gameSize)
            header(eeex,build.eeexTimestamp,build.eeexSize)
            for _,entries in ipairs({profile.entries,build.entries})do
                for slot,entry in pairs(entries)do
                    local at=(entry.module=='game' and base or eeex)+entry.rva
                    hex(at,entry.bytes);lifetimeAt[slot]=at
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
        -- Native opcode-104 fallbacks reach the notice module through the actual
        -- wiring: one loader-log line per loaded game, counted again after the game
        -- is destroyed, and nothing shown in the game. Each game's line reaches the
        -- log through the runtime's repeat filter.
        assert(bank.notices.fallbacks==bank.award.Fallbacks)
        local printed={};print=function(text)printed[#printed+1]=tostring(text)end
        local function count(lines,text) local n=0;for _,line in ipairs(lines) do if line:find(text,1,true) then n=n+1 end end;return n end
        local function logged() return count(printed,'without the bank') end
        EEex_Action_Private_SpriteStartedActionListeners[1](a);assert(logged()==0)
        local shown=#log -- What the first action showed: only the bank's own notices for a.
        for _,line in ipairs(log) do assert(not line:find('loader log',1,true),line) end
        nativeFallbacks=1;EEex_Action_Private_SpriteStartedActionListeners[1](a)
        EEex_Action_Private_SpriteStartedActionListeners[1](a);assert(logged()==1 and #log==shown)
        EEex_GameState_DestroyedListeners[1]();EEex_Action_Private_SpriteStartedActionListeners[1](a)
        assert(logged()==1 and #log==shown)
        nativeFallbacks=2;EEex_Action_Private_SpriteStartedActionListeners[1](a);assert(logged()==2 and #log==shown)
        assert(count(printed,"ran the game's own code without the bank")==2)
        -- A change whose lifetime ended during preparation wrote nothing: its own
        -- line, once per game, and nothing in the game.
        nativeEnded=1;EEex_Action_Private_SpriteStartedActionListeners[1](a)
        EEex_Action_Private_SpriteStartedActionListeners[1](a)
        assert(count(printed,'wrote nothing')==1 and logged()==2 and #log==shown)
        -- A setter write kept unwritten (status 12): its own line, once per game,
        -- listing it, and nothing in the game.
        nativeKept=1;nativeKeptList='add 1000';EEex_Action_Private_SpriteStartedActionListeners[1](a)
        EEex_Action_Private_SpriteStartedActionListeners[1](a)
        assert(count(printed,'(1 since launch: add 1000) was kept and not applied')==1 and logged()==2 and #log==shown)
        -- The native pushes the kept count and list too: without either, the counts
        -- are unavailable, not those of a source that keeps nothing.
        for _,broken in ipairs({{nil,'add 1000'},{'x','add 1000'},{1,nil},{1,7}}) do
            nativeKept,nativeKeptList=broken[1],broken[2]
            local total,why=bank.award.Fallbacks()
            assert(total==nil and why=='Native XP fallback count unavailable')
        end
        nativeKept,nativeKeptList=1,'add 1000'
    ''')


def test_actual_bootstrap_settles_a_replaced_word_through_the_identity_note(host):
    # The identity query's 8th value reaches the runtime. The next cap check
    # publishes the stored word and acknowledges the note for that address and
    # lifetime; a save before it already writes the matched account.
    host.execute('''
        local bank=bootstrap()
        local a={pointer=0x123456,aux={},m_baseStats={m_xp=1000,m_flags=0,m_level1=1},
            m_startTypeAI={m_Class=2},m_derivedStats={m_nXP=1000}}
        EEex_Sprite_LoadedListeners[1](a)
        local s=a.aux.CBMBank;a.m_baseStats.m_xp=4294967295;s.overflow=199905 -- as a banked award past the word leaves it
        local printed={};print=function(text)printed[#printed+1]=tostring(text)end
        nativeReplaced=true;a.m_baseStats.m_xp=100000 -- the game's own SET after a refusal
        local saved=EEex_Sprite_Private_MarshalHandlers.CBMBank.exporter(a)
        assert(saved.overflow==0 and saved.revision==s.revision+1)
        assert(a.aux.CBMBank==s and s.overflow==199905 and #acks==0)
        a.m_derivedStats.m_nXP=100000;CBMBank_BeforeNativeClamp(a,8000000)
        assert(a.aux.CBMBank.overflow==0 and a.aux.CBMBank.revision==s.revision+1)
        assert(#acks==1 and acks[1][1]=='123456' and acks[1][2]=='1' and not nativeReplaced)
        local found=0
        for _,line in ipairs(printed) do if line:find('199905 XP the bank held above',1,true) then found=found+1 end end
        assert(found==1 and bank.runtime.Snapshot(a,8000000).total==100000 and #acks==1)
    ''')


# EEex's hook writer patches the four game entries (patches 1-4); reset (5-6),
# award (7), cap (8) and progression (9+) follow. The two EEex.dll entries are
# ours: VirtualProtect calls 1-2 seal their relays, 3-6 surround their writes.
@pytest.mark.parametrize("failure",["failPatch=1","failPatch=4","failPatch=5","failPatch=6","failPatch=7","failPatch=8",
                                     "failPartyWrite=true","failLoaded=true","failExpose=1","failExpose=2","failExpose=4",
                                     "failExpose=5","failExpose=8","failAddress=writerAt+7","failAddress=removeAt+2","failAddress=previewAt+3",
                                     "failAddress=manualAt","failAddress=hlaAt","failAddress=entryAt","failMenuListener=true",
                                     "failNoticeListener=true","failAddress=lifetimeAt.construct+2","failAddress=lifetimeAt.destruct",
                                     "failProtect=1","failProtect=4","failProtect=6"])
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


@pytest.mark.parametrize("failure",["failPatch=1","failPatch=3","failPatch=4","failAddress=lifetimeAt.construct",
                                     "failAddress=lifetimeAt.destruct+6","failProtect=3","failProtect=4","failProtect=6",
                                     "unwritten=lifetimeAt.import"])
def test_identity_installer_own_partial_patch_rollback_and_nonretryable_config(host,failure):
    host.execute(failure)
    host.execute('''
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        local ok,why=pcall(id.Install,{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles})
        assert(not ok and tostring(why):find('rolled back'),tostring(why))
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
        -- EEex's hook writer patches the game entries; the EEex.dll entries are ours.
        assert(id.installed and patches==4 and protected)
        assert(lifetimeAt.construct==eeex+0xd350 and lifetimeAt.destruct==eeex+0xd390)
        for slot,handler in pairs({copy='CBMI_Copy',marshal='CBMI_Marshal',export='CBMI_CharacterExport',
            import='CBMI_CharacterImport',construct='CBMI_Construct',destruct='CBMI_Destruct'}) do
            assert(id.JumpTarget(lifetimeAt[slot],p.entries[slot].span)==procs[handler],slot)
        end
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
        id.Install{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles}
        local offer=id.ActorDestroyChain(at)
        assert(offer.schema==1 and offer.entry==at and offer.handler==procs.CBMI_Destruct)
        -- What component 430's authenticate_bank_actor accepts: E9 rel32 90 90
        -- into a relay that starts jmp qword ptr [rip+0] and holds the handler
        -- on an executable page.
        local relay=eeexBase-0x20000
        local delta,rel=(relay-(at+5))%4294967296,{}
        for i=1,4 do rel[i]=string.format('%02x',delta%256);delta=math.floor(delta/256) end
        assert(offer.original=='4c8bdc49894b08' and offer.replacement=='e9'..table.concat(rel)..'9090',offer.replacement)
        assert(EEex_ReadU16(relay)==0x25ff and EEex_ReadU32(relay+2)==0 and EEex_Read64(relay+6)==offer.handler)
        assert(protectionAt(relay)==0x20)
        assert(id.ActorDestroyChain(at+1)==nil)
        offer.handler=0;assert(id.ActorDestroyChain(at).handler>0)
        memory[at+1]=0
        assert(id.ActorDestroyChain(at)==nil)
    ''')


@pytest.mark.parametrize("profile",[None,"collection-1.2"])
def test_eeex_dll_lifetime_entries_jump_through_relays_beside_them(host,profile):
    # EEex's own hook writer cannot reach EEex.dll from its code pages beside
    # the game and leaves the entry unchanged without an error (lab, EEex 1.2.0).
    if profile:
        host.execute(f"useIdentityProfile('2.7','{profile}')")
    host.execute('''
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        id.Install{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles}
        for i,slot in ipairs({'construct','destruct'}) do
            local at=lifetimeAt[slot]
            assert(memory[at]==0xe9 and memory[at+5]==0x90 and memory[at+6]==0x90,slot)
            local relay=at+5+EEex_Read32(at+1)
            -- Nearest free allocation granule; above the entries lies EEex.dll itself.
            assert(relay==eeexBase-i*0x10000,slot)
            for j,b in ipairs({0xff,0x25,0,0,0,0}) do assert(memory[relay+j-1]==b,slot) end
            assert(EEex_Read64(relay+6)==procs[slot=='construct' and 'CBMI_Construct' or 'CBMI_Destruct'],slot)
            assert(protectionAt(relay)==0x20 and protectionAt(at)==0x20,slot)
            local flushed=false
            for _,f in ipairs(flushes) do flushed=flushed or (f.at==at and f.size==7) end
            assert(flushed,slot)
            assert(labels['CBMI::original_'..slot]>0,slot)
        end
    ''')


def test_relay_search_reaches_the_farthest_granule_rel32_allows(host):
    host.execute('''
        local limit,farthest=0x7ffe0000,0
        reserved=function(granule)
            farthest=math.max(farthest,math.abs(granule-eeexBase))
            return granule~=eeexBase+limit and granule~=eeexBase-limit
        end
        local id=dofile(research..'/xp-banking-native/identity_hooks.lua')
        id.Install{researchOnly=true,dllPath='synthetic.dll',profiles=identityProfiles}
        assert(farthest==limit)
        for slot,relay in pairs({construct=eeexBase+limit,destruct=eeexBase-limit}) do
            local at=lifetimeAt[slot]
            local handler=procs[slot=='construct' and 'CBMI_Construct' or 'CBMI_Destruct']
            assert(at+5+EEex_Read32(at+1)==relay and id.JumpTarget(at,7)==handler,slot)
        end
    ''')


@pytest.mark.parametrize("free",["false","granule==eeexBase-0x10000"])
def test_relay_shortage_refuses_and_rolls_back_cleanly(host,free):
    # No granule at all, or one granule only for the construct relay.
    host.execute(f"reserved=function(granule) return not ({free}) end")
    host.execute('''
        local ok,why=pcall(bootstrap)
        why=tostring(why)
        assert(not ok and why:find('No free page within rel32 reach',1,true),why)
        assert(why:find('rolled back; restart required',1,true) and not why:find('rollback failed',1,true),why)
        assertRestored()
    ''')


@pytest.mark.parametrize("site,message",[
    ("lifetimeAt.copy","Native lifetime entry was not installed: copy"),
    ("capAt","Native hook at game+0x34E71C was not written"),
    ("manualAt","Native hook at game+0x"),
])
def test_actual_bootstrap_refuses_a_hook_eeex_left_unwritten(host,site,message):
    host.execute(f"unwritten={site}")
    host.globals().expected=message
    host.execute('''
        local ok,why=pcall(bootstrap)
        assert(not ok and tostring(why):find(expected,1,true),tostring(why))
        assert(tostring(why):find('rolled back; restart required',1,true),tostring(why))
        assertRestored()
    ''')


def test_actual_bootstrap_names_a_changed_eeex_entry_by_its_full_address(host):
    # Stock Lua 5.1/5.2 cannot format a 64-bit address with %X.
    host.execute('''
        memory[lifetimeAt.destruct+1]=0
        local ok,why=pcall(bootstrap)
        assert(not ok and writes==0 and #log==0 and protected)
        assert(tostring(why):find('ABI mismatch at 0x7FF00000E8C0 (expected 4C8BDC49894B08, found 4C00DC49894B08)',1,true),
            tostring(why))
    ''')
