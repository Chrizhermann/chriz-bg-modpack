-- Chriz Unpaused Inventory 0.1.0. Windows x64, engine 2.7.3.0 (and 2.6.6.0), EEex 1.2.0 / 1.3.1.
-- Supports component 699 (always unpaused in Inventory) and component 700 (unpaused in combat only).
-- Singleplayer only; other screens (Record, Spellbook, Map, Options) and multiplayer keep native behavior.

local STATE_DEAD_BIT = 0x800
local WORLD_OFFSET_CHITIN = 0x1110
local INVENTORY_OFFSET_CHITIN = 0x10C8
local GAME_OFFSET_CHITIN = 0x1090
local ACTIVE_ENGINE_OFFSET_CHITIN = 0x208
local MULTIPLAYER_OFFSET_CHITIN = 0x2C9
local WORLD_PAUSED_OFFSET = 0xBC
local WORLD_PICKPARTY_OFFSET = 0xBA4
local WORLD_DIALOG_A_OFFSET = 0xB9C
local WORLD_DIALOG_B_OFFSET = 0xB98
local INV_WAS_PAUSED_OFFSET = 0x76C
local GAME_WORLD_TIMER_OFFSET = 0x3FA0
local GAME_VIS_AREA_IDX_OFFSET = 0x6590
local GAME_AREAS_OFFSET = 0x6598
local AREA_BATTLESONG_OFFSET = 0xFA4
local AREA_COMBAT_OFFSET = 0xFA8

CZUnpausedInventory = CZUnpausedInventory or {status = 'not initialized'}
local state = CZUnpausedInventory
if state.queued then return end
state.queued = true

local function log(message)
    state.status = message
    if state.logged then return end
    state.logged = true
    message = tostring(message):gsub('[\r\n]+', ' ')
    if io and io.open then
        local f = io.open('chriz_unpaused_inventory.log', 'a')
        if f then f:write('Chriz Unpaused Inventory: ' .. message .. '\n'); f:close(); return end
    end
    print('Chriz Unpaused Inventory: ' .. message) -- engine log only; never a game notice/dialog
end

local function bytes(hex)
    return (hex:gsub('%x%x', function(pair) return string.char(tonumber(pair, 16)) end))
end

local function signed32(v)
    v = v % 0x100000000
    return v >= 0x80000000 and v - 0x100000000 or v
end

local function readPtr(addr)
    if type(addr) ~= 'number' or addr == 0 then return 0 end
    local lo = EEex_Read32(addr) % 0x100000000
    local hi = EEex_Read32(addr + 4) % 0x100000000
    return lo + hi * 0x100000000
end

local function resolveMode()
    if type(_G.CZUnpausedInventoryConfig) ~= 'table' then
        if type(_G.Infinity_DoFile) == 'function' then
            pcall(Infinity_DoFile, 'CZINVUCF')
        end
        if type(_G.CZUnpausedInventoryConfig) ~= 'table' and type(_G.EEex_DoFile) == 'function' then
            pcall(EEex_DoFile, 'CZINVUCF')
        end
    end
    local cfg = _G.CZUnpausedInventoryConfig
    if type(cfg) == 'table' and (cfg.mode == 'always' or cfg.mode == 'combat') then
        return cfg.mode
    end
    return nil
end

local function freeEnemyTrigger()
    if state.enemyTrigger ~= nil then
        pcall(function() state.enemyTrigger:free() end)
        state.enemyTrigger = nil
    end
end

local function getEnemyTrigger()
    if state.enemyTrigger ~= nil then
        return state.enemyTrigger
    end
    local ok, parsed = pcall(EEex_Trigger_ParseConditionalString, 'See([EVILCUTOFF])')
    if ok and parsed ~= nil then
        state.enemyTrigger = parsed
        return parsed
    end
    return nil
end

local function isInCombat()
    local pChitin = state.pChitin
    if type(pChitin) ~= 'number' or pChitin == 0 then return false end
    local chitin = readPtr(pChitin)
    if chitin == 0 then return false end
    local game = readPtr(chitin + GAME_OFFSET_CHITIN)
    if game == 0 then return false end

    local visIdx = EEex_Read8(game + GAME_VIS_AREA_IDX_OFFSET) % 256
    if visIdx < 12 then
        local area = readPtr(game + GAME_AREAS_OFFSET + visIdx * 8)
        if area ~= 0 then
            local battleSong = signed32(EEex_Read32(area + AREA_BATTLESONG_OFFSET))
            local combatCount = signed32(EEex_Read32(area + AREA_COMBAT_OFFSET))
            if battleSong > 0 or combatCount > 0 then
                return true
            end
        end
    end

    local numChars = math.floor(tonumber(EEex_Sprite_GetNumCharacters()) or 0)
    if numChars <= 0 then return false end
    local trigger = getEnemyTrigger()
    if not trigger then return false end
    local limit = math.min(5, numChars - 1)
    for slot = 0, limit do
        local sprite = EEex_Sprite_GetInPortrait(slot)
        if sprite ~= nil then
            local gstate = math.floor(tonumber(EEex_Sprite_GetState(sprite)) or 0)
            if math.floor(gstate / STATE_DEAD_BIT) % 2 == 0 then
                local ok, seen = pcall(function() return trigger:evalConditionalAsAIBase(sprite) end)
                if ok and seen ~= nil and seen ~= false and seen ~= 0 then
                    return true
                end
            end
        end
    end
    return false
end

local function shouldUnpause()
    local mode = state.mode or resolveMode()
    if mode == 'always' then return 1 end
    if mode == 'combat' then
        return isInCombat() and 1 or 0
    end
    return 0
end

state._test = {
    readPtr = readPtr,
    resolveMode = resolveMode,
    isInCombat = isInCombat,
    shouldUnpause = shouldUnpause,
    freeEnemyTrigger = freeEnemyTrigger,
}

local function install()
    local mode = resolveMode()
    assert(mode == 'always' or mode == 'combat', 'missing or invalid CZINVUCF.lua configuration')

    -- ReadLString stops at NUL; bounded chunks plus explicit NULs preserve binary data.
    local function read(address, n)
        local parts = {}
        while n > 0 do
            local limit = math.min(n, 1024)
            local part = EEex_ReadLString(address, limit)
            parts[#parts + 1] = part
            address = address + #part
            n = n - #part
            if #part < limit then
                parts[#parts + 1] = '\0'
                address = address + 1
                n = n - 1
            end
        end
        return table.concat(parts)
    end

    local base = EEex_GetImageBase()
    assert(read(base, 2) == 'MZ', 'unsupported executable header')
    local peOffset = EEex_Read32(base + 0x3C)
    assert(peOffset >= 0x40 and peOffset <= 0x800, 'invalid PE header offset')
    local pe = base + peOffset
    assert(read(pe, 4) == 'PE\0\0' and EEex_Read16(pe + 4) % 0x10000 == 0x8664, 'unsupported executable format')
    local count = EEex_Read16(pe + 6)
    local optsize = EEex_Read16(pe + 20)
    assert(count > 0 and count <= 96 and optsize >= 112 and peOffset + 24 + optsize + count * 40 <= 0x1000,
        'invalid executable sections')
    assert(EEex_Read16(pe + 24) == 0x20B, 'unsupported optional header')
    local imageSize = EEex_Read32(pe + 24 + 56)

    local builds = {
        [0x6A18D6DC] = { size = 0x3524000, name = 'BG:EE 2.7.3.0' },
        [0x6A18D73D] = { size = 0x3532000, name = 'BG2:EE / EET 2.7.3.0' },
        [0x6A18D7E9] = { size = 0x3563000, name = 'IWD:EE 2.7.3.0' },
        [0x609437B3] = { size = 0x3530000, name = 'BG2:EE / EET 2.6.6.0' },
    }
    local build = builds[EEex_Read32(pe + 8)]
    assert(build and build.size == imageSize, 'unsupported engine build')

    local execSections = {}
    for i = 0, count - 1 do
        local section = pe + 24 + optsize + i * 40
        local size = EEex_Read32(section + 8)
        local rva = EEex_Read32(section + 12)
        if math.floor(EEex_Read32(section + 36) / 0x20000000) % 2 == 1 then
            assert(rva > 0 and size > 0 and rva + size <= imageSize, 'invalid executable section bounds')
            execSections[#execSections + 1] = {
                first = base + rva,
                last = base + rva + size,
                text = read(base + rva, size),
            }
        end
    end

    local function findUnique(label, hex)
        local pat = bytes(hex)
        local hits = {}
        for _, sec in ipairs(execSections) do
            local from = 1
            while true do
                local at = sec.text:find(pat, from, true)
                if not at then break end
                hits[#hits + 1] = { address = sec.first + at - 1, first = sec.first, last = sec.last }
                from = at + 1
            end
        end
        assert(#hits == 1, 'unsupported or modified engine: expected one ' .. label .. ' pattern, found ' .. #hits)
        return hits[1]
    end

    local function checkAt(fn, label, offset, hex)
        local expected = bytes(hex)
        assert(read(fn + offset, #expected) == expected,
            'engine layout mismatch in ' .. label .. ' at ' .. string.format('%X', offset))
    end

    -- 1. CScreenInventory::EngineActivated
    local hitAct = findUnique('InvAct', '488B90101100000FB682BC00000089836C07000085C07536')
    local fnAct = hitAct.address - 0x29
    assert(fnAct >= hitAct.first and fnAct + 0x78 <= hitAct.last, 'invalid InvAct function bounds')
    checkAt(fnAct, 'InvAct', 0x00, '48895C2408574883EC30488BD9')
    assert(EEex_Read8(fnAct + 0x0D) % 256 == 0xE8, 'engine layout mismatch in InvAct call')
    checkAt(fnAct, 'InvAct', 0x19, '80B8C9020000007555488B05')
    checkAt(fnAct, 'InvAct', 0x41, '488B0D')
    checkAt(fnAct, 'InvAct', 0x48, '4533C98844242841B00133D288442420488B8910110000E8')

    -- 2. CScreenWorld::TogglePauseGame
    local hitTog = findUnique('TogglePause', '33FF39BBA40B00000F8531060000440FB683BC000000')
    local fnTog = hitTog.address - 0x47
    assert(fnTog >= hitTog.first and fnTog + 0x6A0 <= hitTog.last, 'invalid TogglePause bounds')
    assert(fnAct + 0x64 + signed32(EEex_Read32(fnAct + 0x60)) == fnTog, 'InvAct call does not target TogglePause')
    checkAt(hitTog.address, 'TogglePause', 0x0E, '440FB683BC0000004C8B0D')
    checkAt(hitTog.address, 'TogglePause', 0x1D, '4180F801')
    local togEpilogue = (hitTog.address + 0x0E) + signed32(EEex_Read32(hitTog.address + 0x0A))
    assert(togEpilogue >= fnTog + 0x400 and togEpilogue + 0x20 <= hitTog.last, 'invalid TogglePause epilogue')
    checkAt(fnTog, 'TogglePauseStartTime', 0x448, '4881C1A03F0000E8')
    local fnStartTime = (fnTog + 0x454) + signed32(EEex_Read32(fnTog + 0x450))
    checkAt(fnStartTime, 'StartTime', 0x00, 'C6410401488B15')

    -- 3. CScreenInventory::TimerAsynchronousUpdate
    local hitAsy = findUnique('InvAsync', '8B83D806000085C00F88B40100000F85A6010000')
    local fnAsy = hitAsy.address - 0x2D
    assert(fnAsy >= hitAsy.first and fnAsy + 0x210 <= hitAsy.last, 'invalid InvAsync bounds')
    checkAt(hitAsy.address, 'InvAsync', 0x14, '488B05')

    -- Verify shared g_pBaldurChitin pointer slot across all three sites.
    local pAct = (fnAct + 0x29) + signed32(EEex_Read32(fnAct + 0x25))
    local pCall = (fnAct + 0x48) + signed32(EEex_Read32(fnAct + 0x44))
    local pAsy = (hitAsy.address + 0x1B) + signed32(EEex_Read32(hitAsy.address + 0x17))
    assert(pAct == pCall and pAct == pAsy, 'inconsistent global chitin pointer reference')

    state.mode = mode
    state.pChitin = pAct

    CBM_UnpausedInventory_ShouldUnpause = function()
        local ok, res = pcall(shouldUnpause)
        if ok and res == 1 then return 1 end
        return 0
    end

    local function target(value)
        return type(value) == 'number' and string.format('%.0f', value) or value
    end

    local queryCallee = EEex_JITNear(EEex_FlattenTable({
        {'#STACK_MOD(8) #ENDL'},
        EEex_GenLuaCall('CBM_UnpausedInventory_ShouldUnpause', {
            returnType = EEex_LuaCallReturnType.Number,
            labelSuffix = '_czinvu',
        }),
        {'jmp done_czinvu #ENDL call_error_czinvu: #ENDL xor eax, eax #ENDL done_czinvu: #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL'},
    }))
    assert(type(queryCallee) == 'number' and queryCallee > 0, 'query callee allocation failed')

    local plans = {
        {
            -- fnAct + 0x30 (15 bytes): movzx eax, [rdx+0xBC]; mov [rbx+0x76C], eax; test eax, eax
            at = fnAct + 0x30,
            size = 15,
            asm = string.format([[
                call %s
                mov rcx, %s
                mov rcx, qword ptr [rcx]
                xor edx, edx
                test rcx, rcx
                jz czinvu_act_after_rdx
                mov rdx, qword ptr [rcx+0x1110]
            czinvu_act_after_rdx:
                test eax, eax
                jz czinvu_act_vanilla
                mov dword ptr [rbx+0x76C], 1
                test rdx, rdx
                jz czinvu_act_done_unpaused
                cmp byte ptr [rdx+0xBC], 0
                je czinvu_act_resume_timer
                mov rcx, rdx
                xor edx, edx
                mov r8b, 1
                xor r9d, r9d
                mov byte ptr [rsp+0x20], 0
                mov byte ptr [rsp+0x28], 0
                call %s
                jmp czinvu_act_done_unpaused
            czinvu_act_resume_timer:
                test rcx, rcx
                jz czinvu_act_done_unpaused
                mov rcx, qword ptr [rcx+0x1090]
                test rcx, rcx
                jz czinvu_act_done_unpaused
                add rcx, 0x3FA0
                call %s
            czinvu_act_done_unpaused:
                mov eax, 1
                test eax, eax
                jmp %s
            czinvu_act_vanilla:
                test rdx, rdx
                jz czinvu_act_vanilla_zero
                movzx eax, byte ptr [rdx+0xBC]
                jmp czinvu_act_store_vanilla
            czinvu_act_vanilla_zero:
                xor eax, eax
            czinvu_act_store_vanilla:
                mov dword ptr [rbx+0x76C], eax
                test eax, eax
                jmp %s
            ]], target(queryCallee), target(pAct), target(fnTog), target(fnStartTime),
                target(fnAct + 0x3F), target(fnAct + 0x3F)),
        },
        {
            -- fnTog + 0x55 (8 bytes): movzx r8d, byte ptr [rbx+0xBC]
            at = fnTog + 0x55,
            size = 8,
            asm = string.format([[
                cmp byte ptr [rbx+0xBC], 0
                jne czinvu_tog_allow
                mov rax, %s
                mov rax, qword ptr [rax]
                test rax, rax
                jz czinvu_tog_allow
                cmp byte ptr [rax+0x2C9], 0
                jne czinvu_tog_allow
                mov rcx, qword ptr [rax+0x208]
                test rcx, rcx
                jz czinvu_tog_allow
                cmp rcx, qword ptr [rax+0x10C8]
                jne czinvu_tog_allow
                sub rsp, 0x20
                call %s
                add rsp, 0x20
                test eax, eax
                jnz %s
            czinvu_tog_allow:
                movzx r8d, byte ptr [rbx+0xBC]
                jmp %s
            ]], target(pAct), target(queryCallee), target(togEpilogue), target(fnTog + 0x5D)),
        },
        {
            -- fnAsy + 0x2D (8 bytes): mov eax, dword ptr [rbx+0x6D8]; test eax, eax
            at = hitAsy.address,
            size = 8,
            asm = string.format([[
                mov rax, %s
                mov rax, qword ptr [rax]
                test rax, rax
                jz czinvu_asy_orig
                cmp byte ptr [rax+0x2C9], 0
                jne czinvu_asy_orig
                cmp qword ptr [rax+0x208], rbx
                jne czinvu_asy_orig
                mov rdx, qword ptr [rax+0x1110]
                test rdx, rdx
                jz czinvu_asy_orig
                cmp byte ptr [rdx+0xBC], 0
                je czinvu_asy_orig
                cmp dword ptr [rdx+0xBA4], 0
                jne czinvu_asy_orig
                cmp dword ptr [rdx+0xB9C], 0
                jne czinvu_asy_orig
                cmp dword ptr [rdx+0xB98], 0
                jne czinvu_asy_orig
                sub rsp, 0x30
                call %s
                test eax, eax
                jz czinvu_asy_after_frame
                mov rax, %s
                mov rax, qword ptr [rax]
                test rax, rax
                jz czinvu_asy_after_frame
                mov rcx, qword ptr [rax+0x1110]
                test rcx, rcx
                jz czinvu_asy_after_frame
                cmp byte ptr [rcx+0xBC], 0
                je czinvu_asy_after_frame
                mov dword ptr [rbx+0x76C], 1
                xor edx, edx
                mov r8b, 1
                xor r9d, r9d
                mov byte ptr [rsp+0x20], 0
                mov byte ptr [rsp+0x28], 0
                call %s
            czinvu_asy_after_frame:
                add rsp, 0x30
            czinvu_asy_orig:
                mov eax, dword ptr [rbx+0x6D8]
                test eax, eax
                jmp %s
            ]], target(pAct), target(queryCallee), target(pAct), target(fnTog), target(hitAsy.address + 8)),
        },
    }

    for _, p in ipairs(plans) do
        p.original = read(p.at, p.size)
        p.trampoline = EEex_JITNear({p.asm})
    end

    EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        for _, p in ipairs(plans) do
            assert(read(p.at, p.size) == p.original, 'hook site changed during installation')
            EEex_JITAt(p.at, {'jmp short ', p.trampoline, ' #ENDL'})
            for i = 5, p.size - 1 do
                EEex_WriteU8(p.at + i, 0x90)
            end
            local disp = signed32(EEex_Read32(p.at + 1))
            assert(EEex_Read8(p.at) % 256 == 0xE9 and p.at + 5 + disp == p.trampoline,
                'hook write verification failed')
            for i = 5, p.size - 1 do
                assert(EEex_Read8(p.at + i) % 256 == 0x90, 'hook nop verification failed')
            end
        end
    end)
    if not ok then
        for _, p in ipairs(plans) do
            for i = 1, #p.original do
                EEex_WriteU8(p.at + i - 1, p.original:byte(i))
            end
        end
    end
    EEex_EnableCodeProtection()
    assert(ok, err)

    EEex_GameState_AddDestroyedListener(freeEnemyTrigger)

    state.queryCallee = queryCallee
    state.hookSites = { fnAct + 0x30, fnTog + 0x55, hitAsy.address }
    state.installed = true
    log('active; ' .. build.name .. '; mode=' .. mode)
end

if not EEex_Active then
    log('inactive: EEex is required')
    return
end
for _, name in ipairs({
    'EEex_GameState_AddInitializedListener', 'EEex_GameState_AddDestroyedListener',
    'EEex_GetImageBase', 'EEex_ReadLString',
    'EEex_Read8', 'EEex_Read16', 'EEex_Read32', 'EEex_WriteU8',
    'EEex_JITNear', 'EEex_JITAt',
    'EEex_DisableCodeProtection', 'EEex_EnableCodeProtection',
    'EEex_GenLuaCall', 'EEex_FlattenTable',
    'EEex_Trigger_ParseConditionalString',
    'EEex_Sprite_GetNumCharacters', 'EEex_Sprite_GetInPortrait', 'EEex_Sprite_GetState',
}) do
    if type(_G[name]) ~= 'function' then
        log('inactive: missing EEex API ' .. name)
        return
    end
end
if type(_G.EEex_LuaCallReturnType) ~= 'table' or type(EEex_LuaCallReturnType.Number) ~= 'number' then
    log('inactive: missing EEex API EEex_LuaCallReturnType')
    return
end
EEex_GameState_AddInitializedListener(function()
    if state.attempted then return end
    state.attempted = true
    local ok, err = pcall(install)
    if not ok then log('inactive; native behavior retained: ' .. tostring(err)) end
end)
