-- Chriz Fast Traps 0.2.0. Windows x64, engine 2.7.3.0, EEex 1.2.0 / 1.3.1.
-- Owns only trap-check scheduling. Native rules and other modal clocks stay intact.
local PERIOD_TICKS = 15 -- 15 AI ticks = about one second at normal game speed.

CZFastTraps = CZFastTraps or {status='not initialized'}
local state=CZFastTraps
if state.queued then return end
state.queued=true

local function log(message)
    state.status=message
    if state.logged then return end
    state.logged=true
    message=message:gsub('[\r\n]+',' ')
    if io and io.open then
        local f=io.open('chriz_fast_traps.log','a')
        if f then f:write('Chriz Fast Traps: '..message..'\n'); f:close(); return end
    end
    print('Chriz Fast Traps: '..message) -- engine log only; never a game notice/dialog
end

local function bytes(hex)
    return (hex:gsub('%x%x',function(pair) return string.char(tonumber(pair,16)) end))
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
    -- Native executable identities, not game data or mod-stack prerequisites.
    -- The byte guards below are still mandatory even on a recognized build.
    local builds={
        [0x6A18D6DC]={size=0x3524000,name='BG:EE 2.7.3.0'},
        [0x6A18D73D]={size=0x3532000,name='BG2:EE / EET 2.7.3.0'},
        [0x6A18D7E9]={size=0x3563000,name='IWD:EE 2.7.3.0'},
    }
    local build=builds[EEex_Read32(pe+8)]
    assert(build and build.size==imageSize,'unsupported engine build')
    -- Unique unsigned modulo-100 gate in CheckModal. No mandatory loader pattern DB:
    -- an absent/ambiguous signature logs an inactive status and leaves the game running.
    local pattern=bytes('448B81A4030000B81F85EB51448B4948488BF141F7E0418BC9C1EA056BC264442BC0B81F85EB5141F7E1C1EA056BC2642BC8443BC1')
    local hits={}
    for i=0,count-1 do
        local section=pe+24+optsize+i*40
        local size=EEex_Read32(section+8)
        local rva=EEex_Read32(section+12)
        if math.floor(EEex_Read32(section+36)/0x20000000)%2==1 then
            assert(rva>0 and size>0 and rva+size<=imageSize,'invalid executable section bounds')
            local text=read(base+rva,size)
            local from=1
            while true do
                local at=text:find(pattern,from,true)
                if not at then break end
                hits[#hits+1]={address=base+rva+at-1,first=base+rva,last=base+rva+size}
                from=at+1
            end
        end
    end
    assert(#hits==1,'unsupported or modified engine: expected one Find Traps pattern, found '..#hits)
    local hit=hits[1]
    local fn=hit.address-0x23
    assert(fn>=hit.first and fn+0x1E20<=hit.last,'invalid function bounds')
    local function check(offset,hex)
        local expected=bytes(hex)
        assert(read(fn+offset,#expected)==expected,'engine layout mismatch at '..string.format('%X',offset))
    end
    check(0,'405556488DAC2418FFFFFF4881ECE8010000')
    check(0x58,'0F859D1D0000FF864C4E0000')
    check(0x64,'B8201100008B96A44E0000B9C81D000085D20F44C1F704302F0800800F85751D0000')
    check(0x11C,'0F84E6010000')
    check(0x308,'0FB68E293A000083E9010F842F14000083E9010F840E0A0000')
    -- Only the RIP-relative address of the door-type byte differs between games.
    check(0xF2C,'3A05')
    check(0xF32,'0F841D010000')
    check(0x16FB,'4D85ED0F85FCF7FFFF')
    check(0x1DFB,'488B8DC00000004833CC')
    local displacement=EEex_Read32(fn+0xF2E)
    if displacement>=0x80000000 then displacement=displacement-0x100000000 end
    local doorType=fn+0xF32+displacement
    assert(doorType>=base and doorType<base+imageSize,'invalid door type address')
    assert(EEex_Read8(doorType)==33,'unexpected door type')

    -- Lua 5.2 on Windows formats %d as 32-bit; tostring() can round large ASLR
    -- addresses into scientific notation. %.0f preserves these exact integers.
    local function target(value)
        return type(value)=='number' and string.format('%.0f',value) or value
    end
    -- Preserve all scratch registers. Each branch consumes only the comparison flags.
    local function due(period,yes,no)
        return string.format([[
            push rax
            push rcx
            push rdx
            push r8
            mov eax,dword ptr [rsi+0x3A4]
            xor edx,edx
            mov ecx,%d
            div ecx
            mov r8d,edx
            mov eax,dword ptr [rsi+0x48]
            xor edx,edx
            div ecx
            cmp edx,r8d
            pop r8
            pop rdx
            pop rcx
            pop rax
            je %s
            jmp %s
        ]],period,target(yes),target(no))
    end
    local plans={
        -- Filter native trap targets independently from native Detect Illusion sprites.
        {at=fn+0xF2C,asm=string.format([[
            cmp al,0x21
            je trap
            cmp al,0x11
            je trap
            cmp al,0x41
            je trap
            %s
        trap:
            %s
        allow:
            cmp al,0x21
            jmp %s
        ]],due(100,'allow',fn+0x16FB),due(PERIOD_TICKS,'allow',fn+0x16FB),target(fn+0xF32))},
        -- Passive secret-door searches remain on the original modulo-100 schedule.
        {at=fn+0x11C,asm=string.format('je %s\n%s',target(fn+0x308),due(100,fn+0x122,fn+0x308))},
        -- Native due passes keep the shared increment. Extra trap passes skip it,
        -- retaining native incapacitation/time-stop checks and the modal dispatch.
        {at=fn+0x58,asm=string.format([[
            je %s
            cmp byte ptr [rsi+0x3A29],2
            jne %s
            %s
        ]],target(fn+0x5E),target(fn+0x1DFB),due(PERIOD_TICKS,fn+0x64,fn+0x1DFB))},
    }
    -- Allocate/assemble all trampolines before touching any engine instruction.
    for _,p in ipairs(plans) do
        p.original=read(p.at,6)
        p.trampoline=EEex_JITNear({p.asm})
    end
    EEex_DisableCodeProtection()
    local ok,err=pcall(function()
        for _,p in ipairs(plans) do
            assert(read(p.at,6)==p.original,'hook site changed during installation')
            EEex_JITAt(p.at,{'jmp short ',p.trampoline,' #ENDL nop #ENDL'})
            local displacement=EEex_Read32(p.at+1)
            if displacement>=0x80000000 then displacement=displacement-0x100000000 end
            assert(EEex_Read8(p.at)%256==0xE9 and EEex_Read8(p.at+5)%256==0x90
                and p.at+5+displacement==p.trampoline,'hook write verification failed')
        end
    end)
    if not ok then
        for _,p in ipairs(plans) do
            for i=1,#p.original do
                local b=p.original:byte(i)
                EEex_Write8(p.at+i-1,b>=128 and b-256 or b)
            end
        end
    end
    EEex_EnableCodeProtection()
    assert(ok,err)
    state.periodTicks=PERIOD_TICKS
    state.installed=true
    log('active; '..build.name..'; trap period '..PERIOD_TICKS..' AI ticks; other modal timing unchanged')
end

if not EEex_Active then
    log('inactive: EEex is required')
    return
end
for _,name in ipairs({
    'EEex_GameState_AddInitializedListener','EEex_GetImageBase','EEex_ReadLString',
    'EEex_Read8','EEex_Read16','EEex_Read32','EEex_Write8','EEex_JITNear','EEex_JITAt',
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
