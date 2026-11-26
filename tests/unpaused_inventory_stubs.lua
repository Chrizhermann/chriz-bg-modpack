-- Bounded EEex memory + runtime stubs for Unpaused Inventory tests.
edits = {}
malloc_mem = {}
local malloc_next = base + 0x5000000

Meter = {
    near = 0, jit = 0, writes = 0, disable = 0, enable = 0,
    registrations = 0, destroyed_registrations = 0, dofile_calls = {},
    logs = {}, targets = {}, sites = {}, assembly = {},
}

local function bounds(a, n)
    assert(a >= base and a + n <= base + #image, 'read outside mapped test image')
    return a - base + 1
end

function EEex_GetImageBase() return base end

function EEex_Read8(a)
    if malloc_mem[a] ~= nil then
        local v = malloc_mem[a]
        return v >= 128 and v - 256 or v
    end
    local v = edits[a] or image:byte(bounds(a, 1))
    return v >= 128 and v - 256 or v
end

function EEex_Read16(a)
    local v = EEex_Read8(a) % 256 + (EEex_Read8(a + 1) % 256) * 256
    return v >= 32768 and v - 65536 or v
end

function EEex_Read32(a)
    local v = EEex_Read16(a) % 65536 + (EEex_Read16(a + 2) % 65536) * 65536
    return v >= 0x80000000 and v - 0x100000000 or v
end

function EEex_ReadLString(a, n)
    assert(n <= 1024, 'unbounded native stack allocation')
    local first = bounds(a, n)
    local value = image:sub(first, first + n - 1)
    for address, v in pairs(edits) do
        local i = address - a + 1
        if i >= 1 and i <= n then
            value = value:sub(1, i - 1) .. string.char(v) .. value:sub(i + 1)
        end
    end
    return value:match('^[^%z]*')
end

function EEex_WriteU8(a, v)
    assert(v >= 0 and v <= 255, 'WriteU8 requires an unsigned byte')
    Meter.writes = Meter.writes + 1
    if a >= base + 0x5000000 and a < malloc_next then
        malloc_mem[a] = v % 256
        return
    end
    bounds(a, 1)
    edits[a] = v % 256
end

function EEex_Malloc(n)
    local addr = malloc_next
    for i = 0, n - 1 do
        malloc_mem[addr + i] = 0
    end
    malloc_next = malloc_next + math.max(64, n)
    return addr
end

function EEex_DisableCodeProtection() Meter.disable = Meter.disable + 1 end
function EEex_EnableCodeProtection() Meter.enable = Meter.enable + 1 end

EEex_LuaCallReturnType = { Boolean = 0, Number = 1 }

function EEex_FlattenTable(t)
    local out = {}
    local function walk(x)
        if type(x) == 'table' then
            for _, v in ipairs(x) do walk(v) end
        elseif x ~= nil then
            out[#out + 1] = x
        end
    end
    walk(t)
    return out
end

function EEex_GenLuaCall(funcName, meta)
    local _ = meta
    return { '#GEN_LUA_CALL:' .. tostring(funcName) }
end

function EEex_JITNear(t)
    Meter.near = Meter.near + 1
    assert(Meter.jit == 0, 'engine write before all trampolines prepared')
    if failure == 'near_throw' and Meter.near == fail_at then error('injected near failure') end
    local at = base + 0x4000000 + Meter.near * 0x1000
    Meter.targets[Meter.near] = at
    Meter.assembly[Meter.near] = type(t) == 'table' and table.concat(t, '\n') or tostring(t)
    return at
end

local function write_unsigned(a, v)
    EEex_WriteU8(a, v)
end

function EEex_JITAt(a, t)
    Meter.jit = Meter.jit + 1
    Meter.sites[Meter.jit] = a
    assert(Meter.near == 4 and Meter.disable == 1 and Meter.enable == 0, 'patch ordering')
    assert(t[1] == 'jmp short ' and t[3] == ' #ENDL' and t[4] == nil, 'unexpected hook assembly')
    if Meter.jit == fail_at then
        if failure == 'jit_throw' then error('injected write failure') end
        if failure == 'silent' then return end
    end
    write_unsigned(a, 0xE9)
    local displacement = (t[2] - a - 5) % 0x100000000
    if failure == 'wrong_target' and Meter.jit == fail_at then displacement = displacement + 1 end
    for i = 0, 3 do write_unsigned(a + 1 + i, math.floor(displacement / 256 ^ i) % 256) end
    if failure == 'partial' and Meter.jit == fail_at then error('injected partial write') end
end

EEex_Active = true

function EEex_DoFile(name)
    Meter.dofile_calls[#Meter.dofile_calls + 1] = name
    if name == 'CZINVUCF' and MockState.configMode ~= nil then
        CZUnpausedInventoryConfig = { mode = MockState.configMode }
    end
end

function EEex_GameState_AddInitializedListener(f)
    Meter.registrations = Meter.registrations + 1
    Meter.listener = f
end

function EEex_GameState_AddDestroyedListener(f)
    Meter.destroyed_registrations = Meter.destroyed_registrations + 1
    Meter.destroyed_listener = f
end

MockState = {
    configMode = 'always',
    party = {},
    seeEnemyFn = nil,
    triggerFreed = 0,
}

function EEex_Trigger_ParseConditionalString(src)
    assert(src == 'See([EVILCUTOFF])', 'unexpected conditional trigger: ' .. tostring(src))
    return {
        evalConditionalAsAIBase = function(_, sprite)
            if MockState.seeEnemyFn then return MockState.seeEnemyFn(sprite) end
            return sprite._seesEnemy or false
        end,
        free = function()
            MockState.triggerFreed = MockState.triggerFreed + 1
        end,
    }
end

function EEex_Sprite_GetNumCharacters() return #MockState.party end
function EEex_Sprite_GetInPortrait(slot) return MockState.party[slot + 1] end
function EEex_Sprite_GetState(sprite) return sprite._state or 0 end

io = { open = function(path, mode)
    assert(path == 'chriz_unpaused_inventory.log' and mode == 'a', 'unexpected file output')
    return { write = function(_, s) Meter.logs[#Meter.logs + 1] = s end, close = function() end }
end }
print = function(s) Meter.logs[#Meter.logs + 1] = s end
Infinity_DisplayString = function() error('in-game notice forbidden') end
