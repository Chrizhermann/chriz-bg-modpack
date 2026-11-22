-- Chriz Scroll Learn Fix 0.1.0. Windows x64, engine 2.7.3.0, EEex 1.2.0 / 1.3.1.
-- Applies the +15%/-15% specialist scroll-learning modifier only to Mage-class
-- characters (Mage and Mage multiclasses) carrying a wizard specialist school
-- mask (bits 0x0040..0x2000). Bards (Blade, Jester, Skald, mod kits), Wild Mages,
-- Trueclass Mages, and kitted dual-class Mages learn at 0% modifier (RAW).

CZScrollLearnFix = CZScrollLearnFix or {status='not initialized'}
local state=CZScrollLearnFix
if state.queued then return end
state.queued=true

local function log(message)
    state.status=message
    if state.logged then return end
    state.logged=true
    message=message:gsub('[\r\n]+',' ')
    if io and io.open then
        local f=io.open('chriz_scroll_learn_fix.log','a')
        if f then f:write('Chriz Scroll Learn Fix: '..message..'\n'); f:close(); return end
    end
    print('Chriz Scroll Learn Fix: '..message) -- engine log only; never a game notice/dialog
end

local function bytes(hex)
    return (hex:gsub('%x%x',function(pair) return string.char(tonumber(pair,16)) end))
end

local function signed32(v)
    v=v%0x100000000
    return v>=0x80000000 and v-0x100000000 or v
end

local function install()
    -- ReadLString stops at NUL; bounded chunks plus explicit NULs preserve binary
    -- data without LuaJIT/ffi. Small reads also bound the binding's stack allocation.
    local function read(address,n)
        local parts={}
        while n>0 do
            local limit=math.min(n,1024)
            local part=EEex_ReadLString(address,limit)
            parts[#parts+1]=part
            address=address+#part
            n=n-#part
            if #part<limit then
                parts[#parts+1]='\0'
                address=address+1
                n=n-1
            end
        end
        return table.concat(parts)
    end

    local base=EEex_GetImageBase()
    assert(read(base,2)=='MZ','unsupported executable header')
    local peOffset=EEex_Read32(base+0x3C)
    assert(peOffset>=0x40 and peOffset<=0x800,'invalid PE header offset')
    local pe=base+peOffset
    assert(read(pe,4)=='PE\0\0' and EEex_Read16(pe+4)%0x10000==0x8664,'unsupported executable format')
    local count=EEex_Read16(pe+6)
    local optsize=EEex_Read16(pe+20)
    assert(count>0 and count<=96 and optsize>=112 and peOffset+24+optsize+count*40<=0x1000,
        'invalid executable sections')
    assert(EEex_Read16(pe+24)==0x20B,'unsupported optional header')
    local imageSize=EEex_Read32(pe+24+56)

    -- Official 2.7.3.0 Windows x64 builds only. Byte guards below remain mandatory.
    local builds={
        [0x6A18D6DC]={size=0x3524000,name='BG:EE 2.7.3.0'},
        [0x6A18D73D]={size=0x3532000,name='BG2:EE / EET 2.7.3.0'},
        [0x6A18D7E9]={size=0x3563000,name='IWD:EE 2.7.3.0'},
    }
    local build=builds[EEex_Read32(pe+8)]
    assert(build and build.size==imageSize,'unsupported engine build')

    local execSections={}
    for i=0,count-1 do
        local section=pe+24+optsize+i*40
        local size=EEex_Read32(section+8)
        local rva=EEex_Read32(section+12)
        if math.floor(EEex_Read32(section+36)/0x20000000)%2==1 then
            assert(rva>0 and size>0 and rva+size<=imageSize,'invalid executable section bounds')
            execSections[#execSections+1]={
                first=base+rva,
                last=base+rva+size,
                text=read(base+rva,size),
            }
        end
    end

    local function findUnique(label,hex)
        local pat=bytes(hex)
        local hits={}
        for _,sec in ipairs(execSections) do
            local from=1
            while true do
                local at=sec.text:find(pat,from,true)
                if not at then break end
                hits[#hits+1]={address=sec.first+at-1,first=sec.first,last=sec.last}
                from=at+1
            end
        end
        assert(#hits==1,'unsupported or modified engine: expected one '..label..' pattern, found '..#hits)
        return hits[1]
    end

    local function inExecBounds(address,length)
        for _,sec in ipairs(execSections) do
            if address>=sec.first and address+length<=sec.last then
                return true
            end
        end
        return false
    end

    local function checkAt(fn,label,offset,hex)
        local expected=bytes(hex)
        assert(read(fn+offset,#expected)==expected,
            'engine layout mismatch in '..label..' at '..string.format('%X',offset))
    end

    local hitLearn=findUnique('LearnSpell',
        '410FB78E9E0700000FBFE8B800400000663BC8743B')
    local fnLearn=hitLearn.address
    assert(fnLearn>=hitLearn.first and fnLearn+0x56<=hitLearn.last,'invalid LearnSpell bounds')

    local hitKitMask=findUnique('GetKitMask',
        '4883EC280FB7819E0700000FB7919C070000C1E2100BD0F7C2FFBFFFFF0F95C10FBAE20E0F92C084C87476')
    local fnKitMask=hitKitMask.address
    assert(fnKitMask>=hitKitMask.first and fnKitMask+0xA8<=hitKitMask.last,'invalid GetKitMask bounds')

    local hitCanWrite=findUnique('CanWriteSpellScroll',
        '817A1093000000')
    local fnCanWrite=hitCanWrite.address
    assert(fnCanWrite>=hitCanWrite.first and fnCanWrite+0x2B<=hitCanWrite.last,'invalid CanWriteSpellScroll bounds')

    checkAt(fnLearn,'LearnSpell',0x15,'488B05')
    checkAt(fnLearn,'LearnSpell',0x1C,'0FB7D1488B8890100000E8')
    checkAt(fnLearn,'LearnSpell',0x2B,'488BCF0FB6D8E8')
    checkAt(fnLearn,'LearnSpell',0x36,'3AD88B442460750983C00F89442460EB0D83E80F89442460EB048B4424603BF0')
    checkAt(fnKitMask,'GetKitMask',0x98,'8B4424304883C428C38BC24883C428C3')
    checkAt(fnCanWrite,'CanWriteSpellScroll',0x17,'4881C1504B0000')
    checkAt(fnCanWrite,'CanWriteSpellScroll',0x26,'E8')

    local fnGetSpellSchool=fnLearn+0x36+signed32(EEex_Read32(fnLearn+0x32))
    assert(inExecBounds(fnGetSpellSchool,0x5A),'invalid CSpell::GetSchool bounds')
    checkAt(fnGetSpellSchool,'GetSpellSchool',0x00,'48895C2408574883EC20488BD9488D15')
    checkAt(fnGetSpellSchool,'GetSpellSchool',0x44,'488B40680FB67825488B5C2430400FB6C74883C4205F')

    local fnIsUsableSubClass=fnCanWrite+0x2B+signed32(EEex_Read32(fnCanWrite+0x27))
    assert(inExecBounds(fnIsUsableSubClass,0x28),'invalid CAIObjectType::IsUsableSubClass bounds')
    checkAt(fnIsUsableSubClass,'IsUsableSubClass',0x24,'0FB6560B')

    -- Lua 5.2 on Windows formats %d as 32-bit; tostring() can round large ASLR
    -- addresses into scientific notation. %.0f preserves these exact integers.
    local function target(value)
        return type(value)=='number' and string.format('%.0f',value) or value
    end

    -- Mage class mask across CLASS.IDS:
    -- 1 (MAGE) + 7 (FIGHTER_MAGE) + 10 (FIGHTER_MAGE_THIEF) + 13 (MAGE_THIEF)
    -- + 14 (CLERIC_MAGE) + 17 (FIGHTER_MAGE_CLERIC) = 0x00026482.
    -- Specialist school mask bits (KITLIST UNUSABLE bits 6..13) = 0x3FC0.
    local asm=string.format([[
        movsx ebp, ax
        cmp ebp, 1
        jne done
        movzx ecx, byte ptr [r14+0x4B5B]
        cmp ecx, 31
        ja done
        mov eax, 0x00026482
        shr eax, cl
        test al, 1
        jz done
        mov rcx, r14
        call %s
        and eax, 0x3FC0
        jz done
        mov ebx, eax
        mov rcx, rdi
        call %s
        movzx ecx, al
        sub ecx, 1
        cmp ecx, 7
        ja penalty
        add ecx, 6
        mov eax, 1
        shl eax, cl
        test ebx, eax
        jz penalty
        add dword ptr [rsp+0x60], 15
        jmp done
    penalty:
        sub dword ptr [rsp+0x60], 15
    done:
        jmp %s
    ]],target(fnKitMask),target(fnGetSpellSchool),target(fnLearn+0x50))

    local original=read(fnLearn,6)
    local trampoline=EEex_JITNear({asm})

    EEex_DisableCodeProtection()
    local ok,err=pcall(function()
        assert(read(fnLearn,6)==original,'hook site changed during installation')
        EEex_JITAt(fnLearn,{'jmp short ',trampoline,' #ENDL nop #ENDL'})
        local disp=signed32(EEex_Read32(fnLearn+1))
        assert(EEex_Read8(fnLearn)%256==0xE9 and EEex_Read8(fnLearn+5)%256==0x90
            and fnLearn+5+disp==trampoline,'hook write verification failed')
    end)
    if not ok then
        for i=1,#original do
            EEex_WriteU8(fnLearn+i-1,original:byte(i))
        end
    end
    EEex_EnableCodeProtection()
    assert(ok,err)

    state.hookSite=fnLearn
    state.trampoline=trampoline
    state.installed=true
    log('active; '..build.name..'; RAW specialist-only scroll learning (+15%/-15% for the 8 specialist mage schools; 0% for bards, Wild Mages, and other kits)')
end

if not EEex_Active then
    log('inactive: EEex is required')
    return
end
for _,name in ipairs({
    'EEex_GameState_AddInitializedListener','EEex_GetImageBase','EEex_ReadLString',
    'EEex_Read8','EEex_Read16','EEex_Read32','EEex_WriteU8','EEex_JITNear','EEex_JITAt',
    'EEex_DisableCodeProtection','EEex_EnableCodeProtection',
}) do
    if type(_G[name])~='function' then
        log('inactive: missing EEex API '..name)
        return
    end
end
EEex_GameState_AddInitializedListener(function()
    if state.attempted then return end
    state.attempted=true
    local ok,err=pcall(install)
    if not ok then log('inactive; native behavior retained: '..tostring(err)) end
end)
