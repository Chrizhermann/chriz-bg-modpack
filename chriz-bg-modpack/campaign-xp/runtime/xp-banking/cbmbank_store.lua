-- Uninstalled actor-owned storage prototype. No EEex registration, engine calls,
-- native XP writes, file I/O or global actor index. Keep one handle per verified
-- actor lifetime; object ID, name, portrait and party slot are not identity.
--
-- Envelope: {storeSchema=1, ownerKey=<save-scoped verified identity>, revision=N,
--   mode="active"|"recovering"|"disabled", payload=<policy-owned table>, ...}
-- The payload's own schema, active/retired banks, class IDs, reset observations
-- and accounting arithmetic belong to the policy adapter, never this module.
-- Unknown envelope/payload schemas are retained opaquely, not migrated.
--
-- M.New(adapter): optional, injectable callbacks (no registration is performed):
-- validatePayload(payload) -> true | "opaque",reason | nil,reason
-- validateTransition(beforeEnvelope, afterEnvelope, operation) -> true | nil,reason
-- verifyCommit(beforeEnvelope, afterEnvelope, operation, observed) -> true | nil,reason
-- bankEmpty(payload) -> true | nil,reason
-- Every callback receives detached snapshots. It must not perform native writes.
-- verifyCommit must verify revision/identity and bounded before/after observations;
-- a caller-supplied boolean is deliberately not an observed-state receipt.
--
-- Begin locks a private proposed snapshot; Commit requires its opaque token and
-- adapter-verified observations; Abort leaves committed data intact. Export sees
-- only the committed snapshot while a transaction is pending. This is NOT an
-- atomic native XP/marshal transaction: the integration must exclude a save after
-- native XP changed but before Commit, and reconcile failed commits explicitly.
-- Abort never claims to undo native XP. No pending token is serialized.
--
-- Contexts must be proved by the native adapter, not IsMarshallingCopy alone:
-- {verified=true, reason="save"|"chr_export"|"magical_clone"|"preview",
--  ownerKey=...} for Export; "save_load"|"chr_import" for Import.
-- A CHR import requires independently verified legitimate owner association.
-- Clones/previews get an explicit empty exclusion record; the owner is untouched.
-- An unsupported context returns an error and retains the original snapshot.
-- The adapter must block that unclassified operation before serialization; it
-- MUST NOT translate the error to nil/{} in a registered marshal exporter.
-- View/Rejected expose detached recovery evidence, not a guessed safe carrier.
--
-- Recovery is per actor. BeginRecovery/BeginRelease/BeginDisable neither locate
-- unloaded owners nor establish that all banks in a save have been recovered.
local M = {}
local MAX = 9007199254740991
local MAX_DEPTH, MAX_FIELDS, MAX_BYTES, MAX_STRING = 16, 4096, 262144, 65535
local modes = {active = true, recovering = true, disabled = true}

local function integer(n)
    return type(n) == "number" and n >= 0 and n <= MAX and n % 1 == 0
end

local function wireInteger(n)
    if type(n) ~= "number" or n < -MAX or n > MAX or n % 1 ~= 0 then return false end
    -- EEex a6d21abe signed-width selection uses -0x100/-0x10000/-0x100000000.
    -- Reject their overflow gaps rather than truncate an unknown extension.
    if n < -128 and n >= -256 then return false end
    if n < -32768 and n >= -65536 then return false end
    if n < -2147483648 and n >= -4294967296 then return false end
    return true
end

-- Bounds limit serializer recursion/work; errors never trim/drop individual data.
-- Shared tables are copied independently, matching marshal's value semantics.
function M.WireSnapshot(input)
    if type(input) ~= "table" then return nil, "Marshal payload must be a table." end
    local ancestors, fields, bytes = {}, 0, 0
    local function scalar(value)
        local kind = type(value)
        if kind == "boolean" then return true end
        if kind == "number" then
            if not wireInteger(value) then return nil, "Number cannot round-trip exactly through marshal." end
            bytes = bytes + 9
        elseif kind == "string" then
            if #value > MAX_STRING or string.find(value, "\0", 1, true) then
                return nil, "String exceeds marshal bounds or contains NUL."
            end
            bytes = bytes + #value + 2
        else return nil, "Unsupported marshal key or value type: " .. kind end
        if bytes > MAX_BYTES then return nil, "Marshal payload exceeds byte budget." end
        return true
    end
    local copy
    copy = function(value, depth)
        if depth > MAX_DEPTH then return nil, "Marshal payload exceeds depth budget." end
        if getmetatable(value) ~= nil then return nil, "Metatables cannot round-trip through marshal." end
        if ancestors[value] then return nil, "Cyclic marshal payload." end
        ancestors[value] = true
        local output = {}
        for key, item in next, value do
            fields = fields + 1
            bytes = bytes + 2
            if fields > MAX_FIELDS then return nil, "Marshal payload exceeds field budget." end
            local ok, reason = scalar(key)
            if not ok then return nil, reason end
            if type(item) == "table" then
                local nested
                nested, reason = copy(item, depth + 1)
                if not nested then return nil, reason end
                output[key] = nested
            else
                ok, reason = scalar(item)
                if not ok then return nil, reason end
                output[key] = item
            end
        end
        ancestors[value] = nil
        return output
    end
    return copy(input, 1)
end

local function validContext(context, owner, reasons)
    if type(context) ~= "table" or context.verified ~= true
        or type(owner) ~= "string" or owner == "" or #owner > MAX_STRING
        or owner:find("\0", 1, true) or not reasons[context.reason]
        or context.ownerKey ~= owner then
        return nil, "Unverified or unsupported actor serialization context; payload retained."
    end
    return true
end

function M.New(adapter)
    if type(adapter) ~= "table" then return nil, "An explicit policy adapter is required." end
    local callbacks = {}
    for _, key in ipairs({"validatePayload", "validateTransition", "verifyCommit", "bankEmpty"}) do
        if adapter[key] ~= nil and type(adapter[key]) ~= "function" then
            return nil, "Invalid adapter callback: " .. key
        end
        callbacks[key] = adapter[key]
    end
    local committed, status, diagnostic, rejectedPayload, pending, busy, actorOwner
    status = "absent"
    local handle = {}
    local function detached(value)
        return value and M.WireSnapshot(value) or nil
    end
    local function invoke(name, ...)
        if not callbacks[name] then return nil, "Missing adapter capability: " .. name end
        busy = true
        local ok, answer, reason = pcall(callbacks[name], ...)
        busy = false
        if not ok then
            return nil, "Adapter " .. name .. " failed: "
                .. (type(answer) == "string" and answer or "non-string error")
        end
        if answer ~= true and answer ~= "opaque" then
            return nil, type(reason) == "string" and reason or "Adapter rejected " .. name .. "."
        end
        return answer, reason
    end
    local function validateEnvelope(envelope)
        if envelope.storeSchema ~= 1 then return "opaque", "Unknown storage schema; preserve payload." end
        if type(envelope.ownerKey) ~= "string" or envelope.ownerKey == ""
            or not integer(envelope.revision) or not modes[envelope.mode]
            or type(envelope.payload) ~= "table" then
            return nil, "Malformed storage envelope; payload retained."
        end
        local answer, reason = invoke("validatePayload", detached(envelope.payload))
        if answer == true and envelope.mode == "disabled" then
            answer, reason = invoke("bankEmpty", detached(envelope.payload))
            if answer ~= true then return nil, reason or "Disabled actor still has an unreleased bank." end
        end
        return answer, reason
    end
    local function writable()
        if busy then return nil, "Reentrant storage mutation rejected." end
        if pending then return nil, "A transaction is already pending." end
        if status ~= "ready" then return nil, diagnostic or "No validated actor state." end
        if committed.mode == "disabled" then return nil, "This actor's banking is disabled." end
        return true
    end

    function handle:View()
        return detached(committed), status, diagnostic
    end
    function handle:Rejected()
        return detached(rejectedPayload)
    end
    function handle:Pending()
        if not pending then return nil end
        return detached(pending.after), pending.operation
    end

    function handle:Import(payload, context)
        if busy or pending then return nil, "Import cannot replace an active transaction." end
        local function failed(reason, incoming)
            rejectedPayload = incoming
            -- Preserve the last carrier, but do not keep using it mechanically
            -- after an incoming actor record could not be accepted.
            if committed then status, diagnostic = "faulted", reason end
            return nil, reason
        end
        local incoming, reason = M.WireSnapshot(payload)
        if not incoming then return failed(reason) end
        local owner = actorOwner or (type(context) == "table" and context.ownerKey)
        local ok
        ok, reason = validContext(context, owner, {save_load = true, chr_import = true})
        if not ok or (incoming.storeSchema == 1 and incoming.ownerKey ~= owner) then
            return failed(reason or "Actor owner mismatch; prior payload retained.", incoming)
        end
        local classification
        classification, reason = validateEnvelope(incoming)
        if not classification then
            -- A first malformed wire-valid record still needs a lossless carrier.
            if not committed then
                committed, status, diagnostic, actorOwner = incoming, "faulted", reason, owner
            end
            return failed(reason, incoming)
        end
        committed, pending, rejectedPayload, actorOwner = incoming, nil, nil, owner
        status = classification == true and "ready" or "opaque"
        diagnostic = classification == true and nil or reason
        return true, status
    end

    function handle:Export(context)
        local owner = actorOwner
        local ok, reason = validContext(context, owner,
            {save = true, chr_export = true, magical_clone = true, preview = true})
        if not ok then return nil, reason end
        if context.reason == "magical_clone" or context.reason == "preview" then
            return {}, "excluded" -- Not an eligible new bank owner.
        end
        return detached(committed) or {}, status
    end

    local function begin(expectedRevision, payload, operation, mode)
        local ok, reason = writable()
        if not ok then return nil, reason end
        if expectedRevision ~= committed.revision or committed.revision == MAX then
            return nil, "Stale or exhausted storage revision."
        end
        local nextPayload
        nextPayload, reason = M.WireSnapshot(payload)
        if not nextPayload then return nil, reason end
        local after = detached(committed)
        after.payload, after.mode, after.revision = nextPayload, mode, committed.revision + 1
        -- Each part may fit separately while the complete carrier does not.
        after, reason = M.WireSnapshot(after)
        if not after then return nil, reason end
        ok, reason = validateEnvelope(after)
        if ok ~= true then return nil, reason or "Proposed state is opaque." end
        ok, reason = invoke("validateTransition", detached(committed), detached(after), operation)
        if ok ~= true then return nil, reason or "Unverified transition." end
        local token = {} -- Capability compared by identity; no trusted fields exposed.
        pending = {token = token, beforeRevision = committed.revision,
            after = after, operation = operation}
        return token
    end

    function handle:Begin(expectedRevision, payload, operation)
        if type(operation) ~= "string" or operation == "" or operation == "release"
            or operation == "begin_recovery" or operation == "disable" then
            return nil, "Use the explicit recovery primitives for this operation."
        end
        if committed and committed.mode ~= "active" then return nil, "Actor is in recovery or disabled." end
        return begin(expectedRevision, payload, operation, "active")
    end
    function handle:BeginRecovery(expectedRevision)
        if not committed or committed.mode ~= "active" then return nil, "Actor must be active to start recovery." end
        return begin(expectedRevision, committed.payload, "begin_recovery", "recovering")
    end
    function handle:BeginRelease(expectedRevision, payload)
        if not committed or committed.mode ~= "recovering" then return nil, "Actor is not in recovery." end
        return begin(expectedRevision, payload, "release", "recovering")
    end
    function handle:BeginDisable(expectedRevision)
        local ok, reason = writable()
        if not ok then return nil, reason end
        if committed.mode ~= "recovering" then return nil, "Actor is not in recovery." end
        ok, reason = invoke("bankEmpty", detached(committed.payload))
        if ok ~= true then return nil, reason or "Unreleased bank remains." end
        return begin(expectedRevision, committed.payload, "disable", "disabled")
    end

    function handle:Commit(token, observed)
        if busy then return nil, "Reentrant storage mutation rejected." end
        if not pending or pending.token ~= token or committed.revision ~= pending.beforeRevision then
            return nil, "Stale or foreign transaction token."
        end
        local receipt, reason = M.WireSnapshot(observed)
        if not receipt then return nil, reason end
        local ok
        ok, reason = invoke("verifyCommit", detached(committed), detached(pending.after),
            pending.operation, receipt)
        if ok ~= true then return nil, reason or "Native observation was not verified." end
        committed, pending, diagnostic = pending.after, nil, nil
        return true
    end
    function handle:Abort(token)
        if busy then return nil, "Reentrant storage mutation rejected." end
        if not pending or pending.token ~= token then return nil, "Stale or foreign transaction token." end
        pending = nil
        return true
    end
    return handle
end

return M
