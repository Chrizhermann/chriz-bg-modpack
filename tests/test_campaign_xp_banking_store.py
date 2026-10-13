"""Uninstalled storage contract in Lua 5.1/LuaJIT; no real EEex serialization.

The adapter and observed-credit receipts are deliberately synthetic. Passing
them proves neither native credit/save atomicity nor actor identity detection.
"""
from importlib import import_module
from pathlib import Path
import math

import pytest


SOURCE = (Path(__file__).resolve().parents[1]
          / "research/xp-banking/cbmbank_store.lua")
MAX_EXACT = 2**53 - 1

ADAPTER = """
local function integer(n)
    return type(n) == 'number' and n >= 0 and n <= 9007199254740991 and n % 1 == 0
end
return {
    validatePayload = function(p)
        if p.schema ~= 1 then return 'opaque', 'Unknown policy schema.' end
        if not integer(p.usable) or not integer(p.bank) or not integer(p.revision)
            or type(p.policy) ~= 'string' or type(p.phase) ~= 'string' then
            return nil, 'Malformed policy payload.'
        end
        if p.classKind == 'dual' then
            for _, name in ipairs({'preResetUsable', 'retiredThreshold',
                    'retiredUsable', 'retiredBank', 'nativeDiscarded', 'oldLevelAtDual'}) do
                if not integer(p[name]) then return nil, 'Malformed dual payload.' end
            end
            if type(p.oldClass) ~= 'string' or type(p.newClass) ~= 'string' then
                return nil, 'Missing class identity.'
            end
        elseif p.classKind ~= 'single' and p.classKind ~= 'multi' then
            return nil, 'Unsupported class data.'
        end
        return true
    end,
    validateTransition = function(before, after, operation)
        if before.payload.policy ~= after.payload.policy then
            return nil, 'No implicit policy migration.'
        end
        local kinds = {earn=true, dual=true, advance=true, release=true,
            begin_recovery=true, disable=true}
        if not kinds[operation] then return nil, 'Unsupported operation.' end
        return true
    end,
    verifyCommit = function(before, after, operation, observed)
        -- A bounded observation double, not a native acknowledgement primitive.
        if observed.ownerKey ~= before.ownerKey
            or observed.beforeRevision ~= before.revision
            or observed.afterRevision ~= after.revision
            or observed.operation ~= operation
            or observed.beforeUsable ~= before.payload.usable
            or observed.afterUsable ~= after.payload.usable
            or observed.beforeRetired ~= (before.payload.retiredUsable or 0)
            or observed.afterRetired ~= (after.payload.retiredUsable or 0) then
            return nil, 'Observed actor/revision/XP mismatch.'
        end
        return true
    end,
    bankEmpty = function(p)
        if p.bank ~= 0 or (p.retiredBank or 0) ~= 0 then
            return nil, 'This actor retains an unreleased bank.'
        end
        return true
    end,
}
"""


@pytest.fixture(params=["lua51", "luajit21"])
def model(request):
    lua = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    return lua, lua.execute(SOURCE.read_text(encoding="utf-8")), lua.execute(ADAPTER)


def values(result):
    return result if isinstance(result, tuple) else (result,)


def first(result):
    return values(result)[0]


def call(store, name, *args):
    return getattr(store, name)(store, *args)


def reject(result):
    output = values(result)
    assert output[0] is None
    assert isinstance(output[1], str) and output[1].strip()
    return output[1]


def snapshot(value):
    if hasattr(value, "items"):
        return {key: snapshot(item) for key, item in value.items()}
    if isinstance(value, float) and math.isnan(value):
        return "<nan>"
    return value


def table(model, data):
    return model[0].table_from(data, recursive=True)


def context(model, reason="save_load", owner="run-a:actor-17", verified=True):
    return table(model, {"verified": verified, "reason": reason, "ownerKey": owner})


def envelope(model, *, owner="run-a:actor-17", bank=50000, usable=500000):
    return table(model, {"storeSchema": 1, "ownerKey": owner, "revision": 0,
                         "mode": "active", "payload": {
                             "schema": 1, "classKind": "single", "policy": "bg1_sod",
                             "phase": "SOD", "revision": 0, "usable": usable, "bank": bank},
                         "futureExtension": {"flag": True, "string": "retained", "value": 17}})


def create(model, incoming=None, adapter=None):
    store = first(model[1].New(model[2] if adapter is None else adapter))
    assert store is not None
    incoming = envelope(model) if incoming is None else incoming
    assert call(store, "Import", incoming, context(model, owner=incoming.ownerKey)) == (True, "ready")
    return store


def view(store):
    return values(call(store, "View"))[0]


def export(model, store, reason="save"):
    return first(call(store, "Export", context(model, reason, owner=view(store).ownerKey)))


def receipt(model, before, after, operation):
    return table(model, {"ownerKey": before.ownerKey,
                         "beforeRevision": before.revision, "afterRevision": after.revision,
                         "operation": operation, "beforeUsable": before.payload.usable,
                         "afterUsable": after.payload.usable,
                         "beforeRetired": before.payload.retiredUsable or 0,
                         "afterRetired": after.payload.retiredUsable or 0})


def commit(model, store, token):
    after, operation = call(store, "Pending")
    assert call(store, "Commit", token, receipt(model, view(store), after, operation)) is True


def begin(model, store, payload, operation="earn"):
    token = first(call(store, "Begin", view(store).revision, payload, operation))
    assert token is not None
    return token


def test_import_export_are_deep_detached_snapshots_and_callbacks_do_not_register(model):
    incoming = envelope(model)
    before = snapshot(incoming)
    store = create(model, incoming)
    incoming.payload.bank = 999
    incoming.futureExtension.string = "caller changed"
    assert snapshot(view(store)) == before
    saved = export(model, store)
    saved.payload.bank = 888
    saved.futureExtension.value = 77
    assert snapshot(export(model, store)) == before
    assert snapshot(view(store)) == before
    assert model[0].globals().EEex_Sprite_AddMarshalHandlers is None
    assert model[0].globals().CBM_BankStore is None


@pytest.mark.parametrize("reason", ["save", "chr_export"])
def test_normal_save_and_verified_real_chr_export_keep_all_entitlement(model, reason):
    store = create(model)
    before = snapshot(view(store))
    payload, status = call(store, "Export", context(model, reason))
    assert status == "ready" and snapshot(payload) == before
    assert snapshot(view(store)) == before
    imported = first(model[1].New(model[2]))
    reason = "save_load" if reason == "save" else "chr_import"
    assert call(imported, "Import", payload, context(model, reason)) == (True, "ready")
    assert snapshot(view(imported)) == before


@pytest.mark.parametrize("reason", ["magical_clone", "preview"])
def test_verified_clone_preview_excludes_transfer_without_debiting_owner(model, reason):
    store = create(model)
    before = snapshot(view(store))
    for _ in range(3):
        payload, status = call(store, "Export", context(model, reason))
        assert snapshot(payload) == {} and status == "excluded"
        assert snapshot(view(store)) == before


@pytest.mark.parametrize("reason,verified,owner", [
    ("copy", True, "run-a:actor-17"), ("save", False, "run-a:actor-17"),
    ("IsMarshallingCopy", True, "run-a:actor-17"),
    ("save", True, "run-b:actor-17"), (None, True, "run-a:actor-17"),
])
def test_unclassified_identity_never_silently_drops_or_transfers_payload(model, reason, verified, owner):
    store = create(model)
    before = snapshot(view(store))
    reject(call(store, "Export", context(model, reason, owner, verified)))
    assert snapshot(view(store)) == before
    assert snapshot(export(model, store)) == before


@pytest.mark.parametrize("outer_schema", [2, "future-v9"])
def test_unknown_envelope_schema_can_have_a_different_shape_and_is_preserved_opaquely(model, outer_schema):
    unknown = table(model, {"storeSchema": outer_schema, "vNext": {"bankChunks": "439000",
                                                                  "newOwnerShape": 901}})
    before = snapshot(unknown)
    store = first(model[1].New(model[2]))
    assert call(store, "Import", unknown, context(model)) == (True, "opaque")
    saved, status = call(store, "Export", context(model, "save"))
    assert status == "opaque" and snapshot(saved) == before
    reject(call(store, "Begin", 0, table(model, {}), "earn"))
    assert snapshot(first(call(store, "View"))) == before


def test_unknown_inner_schema_is_retained_without_replacing_it_with_empty_v1(model):
    incoming = envelope(model)
    incoming.payload = table(model, {"schema": 9, "futureBank": "500000:439000"})
    before = snapshot(incoming)
    store = first(model[1].New(model[2]))
    assert call(store, "Import", incoming, context(model)) == (True, "opaque")
    assert snapshot(export(model, store)) == before
    reject(call(store, "BeginRecovery", 0))
    assert snapshot(export(model, store)) == before


@pytest.mark.parametrize("expression", [
    "{x=0/0}", "{x=math.huge}", "{x=-math.huge}", "{x=0.5}",
    "{x=9007199254740992}", "{x=-9007199254740992}",
    "{x='bad'..string.char(0)..'string'}", "{['bad'..string.char(0)]=1}",
    "{x=function() end}", "{[{}]=1}", "{[function() end]=1}",
    "(function() local t={} t.self=t return t end)()",
    "(function() local a,b={},{} a.b=b b.a=a return a end)()",
    "setmetatable({}, {__index=function() error('must not run') end})",
    "{x=coroutine.create(function() end)}",
    "{x=string.rep('a',65536)}",
    "(function() local t,r={},{} t=r for i=1,17 do r.child={} r=r.child end return t end)()",
    "(function() local t={} for i=1,4097 do t[i]=i end return t end)()",
    "(function() local t={} for i=1,5 do t[i]=string.rep('x',65535) end return t end)()",
])
def test_wire_unsafe_import_never_overwrites_previous_committed_bank(model, expression):
    store = create(model)
    before = snapshot(view(store))
    unsafe = model[0].eval(expression)
    reject(model[1].WireSnapshot(unsafe))
    reject(call(store, "Import", unsafe, context(model)))
    assert snapshot(export(model, store)) == before


@pytest.mark.parametrize("value", [-256, -129, -65536, -32769, -4294967296, -2147483649])
def test_negative_values_in_current_eeex_signed_width_gaps_are_not_truncated(model, value):
    reject(model[1].WireSnapshot(table(model, {"extension": value})))


def test_wire_safe_integer_edges_strings_boolean_keys_and_shared_values_survive(model):
    lua = model[0]
    incoming = lua.eval("""(function()
        local shared={bank=439000}
        return { [false]=true, ['']=false, [17]='日本語', a=shared, b=shared,
            values={0, 255, 256, 65535, 65536, 4294967295, 4294967296,
                9007199254740991, -1, -128, -257, -32768, -65537,
                -2147483648, -4294967297, -9007199254740991} }
    end)()""")
    copied = first(model[1].WireSnapshot(incoming))
    assert snapshot(copied) == snapshot(incoming)
    copied.a.bank = 1
    assert copied.b.bank == 439000 and incoming.a.bank == 439000


def test_malformed_known_import_retains_previous_state_and_rejected_evidence(model):
    store = create(model)
    before = snapshot(view(store))
    invalid = envelope(model, bank=-1)
    reject(call(store, "Import", invalid, context(model)))
    assert snapshot(export(model, store)) == before
    assert values(call(store, "View"))[1] == "faulted"
    reject(call(store, "Begin", 0, envelope(model).payload, "earn"))
    assert snapshot(call(store, "Rejected")) == snapshot(invalid)
    invalid.payload.bank = 0
    assert call(store, "Rejected").payload.bank == -1
    first_import = first(model[1].New(model[2]))
    invalid.payload.bank = -1
    reject(call(first_import, "Import", invalid, context(model)))
    preserved, status = call(first_import, "Export", context(model, "save"))
    assert status == "faulted" and snapshot(preserved) == snapshot(invalid)
    reject(call(first_import, "Begin", 0, envelope(model).payload, "earn"))
    assert call(store, "Import", envelope(model), context(model)) == (True, "ready")
    assert snapshot(view(store)) == before


def test_combined_envelope_budget_cannot_publish_an_unexportable_transaction(model):
    incoming = envelope(model)
    incoming.futureExtension.padding = "x" * 65000
    incoming.futureExtension.morePadding = "y" * 65000
    store = create(model, incoming)
    before = snapshot(view(store))
    proposed = view(store).payload
    proposed.padding = "z" * 65000
    proposed.morePadding = "a" * 65000
    proposed.thirdPadding = "b" * 65000
    assert first(model[1].WireSnapshot(proposed)) is not None
    assert "budget" in reject(call(store, "Begin", 0, proposed, "earn"))
    assert call(store, "Pending") is None
    assert snapshot(export(model, store)) == before


def test_disabled_import_with_nonempty_bank_is_quarantined_not_silently_accepted(model):
    store = create(model)
    before = snapshot(view(store))
    incoming = envelope(model)
    incoming.mode = "disabled"
    reject(call(store, "Import", incoming, context(model)))
    assert snapshot(view(store)) == before
    assert snapshot(call(store, "Rejected")) == snapshot(incoming)


def test_save_loading_older_snapshot_has_no_cross_actor_or_process_high_water_mark(model):
    store = create(model)
    older = export(model, store)
    next_payload = view(store).payload
    next_payload.bank = 250000
    next_payload.revision = 1
    commit(model, store, begin(model, store, next_payload))
    assert view(store).payload.bank == 250000
    assert call(store, "Import", older, context(model)) == (True, "ready")
    assert snapshot(view(store)) == snapshot(older)
    other = create(model, envelope(model, owner="run-b:actor-17", bank=0, usable=7))
    assert view(other).payload.bank == 0 and view(store).payload.bank == 50000
    reject(call(store, "Import", export(model, other), context(model, owner="run-b:actor-17")))
    assert snapshot(view(store)) == snapshot(older)


def test_begin_exports_only_committed_snapshot_and_freezes_candidate_until_verified_commit(model):
    store = create(model)
    before = snapshot(view(store))
    next_payload = view(store).payload
    next_payload.bank = 50123
    next_payload.revision = 1
    token = begin(model, store, next_payload)
    next_payload.bank = 999999
    pending, operation = call(store, "Pending")
    assert pending.payload.bank == 50123 and operation == "earn"
    pending.payload.bank = 888888
    assert snapshot(export(model, store)) == before
    reject(call(store, "Begin", 0, next_payload, "earn"))
    reject(call(store, "Import", envelope(model), context(model)))
    commit(model, store, token)
    assert view(store).payload.bank == 50123 and view(store).revision == 1
    assert snapshot(view(store).futureExtension) == before["futureExtension"]


@pytest.mark.parametrize("field,value", [
    ("ownerKey", "wrong-owner"), ("beforeRevision", 9), ("afterRevision", 9),
    ("operation", "release"), ("beforeUsable", 3), ("afterUsable", 4),
    ("beforeRetired", 5), ("afterRetired", 6),
])
def test_failed_observation_keeps_both_committed_bank_and_pending_transaction(model, field, value):
    store = create(model)
    before = snapshot(view(store))
    payload = view(store).payload
    payload.usable, payload.bank = 510000, 40000
    token = begin(model, store, payload, "advance")
    after, operation = call(store, "Pending")
    observed = receipt(model, view(store), after, operation)
    observed[field] = value
    reject(call(store, "Commit", token, observed))
    assert snapshot(view(store)) == before
    assert snapshot(first(call(store, "Pending"))) == snapshot(after)
    commit(model, store, token)
    assert (view(store).payload.usable, view(store).payload.bank) == (510000, 40000)


def test_boolean_is_not_credit_proof_and_aborted_stale_foreign_tokens_cannot_commit(model):
    store = create(model)
    payload = view(store).payload
    payload.bank += 7
    token = begin(model, store, payload)
    before = snapshot(view(store))
    reject(call(store, "Commit", token, True))
    reject(call(store, "Commit", table(model, {}), table(model, {})))
    assert call(store, "Abort", token) is True
    assert snapshot(view(store)) == before
    reject(call(store, "Commit", token, table(model, {})))
    reject(call(store, "Abort", token))
    fresh = begin(model, store, payload)
    reject(call(store, "Commit", token, table(model, {})))
    commit(model, store, fresh)
    reject(call(store, "Commit", fresh, table(model, {})))
    assert view(store).payload.bank == 50007


def test_stale_and_exhausted_revisions_cannot_stage_new_state(model):
    store = create(model)
    reject(call(store, "Begin", 1, view(store).payload, "earn"))
    exhausted = envelope(model)
    exhausted.revision = MAX_EXACT
    assert call(store, "Import", exhausted, context(model)) == (True, "ready")
    reject(call(store, "Begin", MAX_EXACT, exhausted.payload, "earn"))
    assert view(store).revision == MAX_EXACT


def test_policy_errors_and_callback_mutations_do_not_change_owned_snapshots(model):
    lua, _, adapter = model
    adapter.validateTransition = lua.eval("""function(before, after)
        before.payload.bank=0 after.payload.bank=0 error('synthetic validator failure') end""")
    store = create(model)
    before = snapshot(view(store))
    assert "synthetic validator failure" in reject(call(store, "Begin", 0, view(store).payload, "earn"))
    assert snapshot(view(store)) == before and call(store, "Pending") is None
    # New handles capture callbacks; later changing the adapter table cannot
    # silently replace the validation policy of an already-owned actor.
    adapter.validateTransition = lua.eval("function() return true end")
    reject(call(store, "Begin", 0, view(store).payload, "earn"))
    assert snapshot(view(store)) == before


def test_verifier_exception_retains_pending_data_and_cannot_publish_callback_mutations(model):
    lua, _, adapter = model
    lua.globals().failSyntheticCommit = True
    original = adapter.verifyCommit
    lua.globals().originalVerifier = original
    adapter.verifyCommit = lua.eval("""function(before, after, operation, observed)
        if failSyntheticCommit then
            before.payload.bank=0 after.payload.bank=0 observed.afterUsable=-1
            error('synthetic commit interruption')
        end
        local ok, reason = originalVerifier(before, after, operation, observed)
        before.payload.bank=0 after.payload.bank=0
        return ok, reason
    end""")
    store = create(model)
    before = snapshot(view(store))
    payload = view(store).payload
    payload.bank += 123
    token = begin(model, store, payload)
    after, operation = call(store, "Pending")
    observed = receipt(model, view(store), after, operation)
    observation_before = snapshot(observed)
    assert "synthetic commit interruption" in reject(call(store, "Commit", token, observed))
    assert snapshot(observed) == observation_before
    assert snapshot(view(store)) == before
    assert first(call(store, "Pending")).payload.bank == 50123
    lua.globals().failSyntheticCommit = False
    assert call(store, "Commit", token, observed) is True
    assert view(store).payload.bank == 50123


def test_missing_policy_validator_preserves_incoming_wire_record_as_faulted(model):
    model[2].validatePayload = None
    store = first(model[1].New(model[2]))
    incoming = envelope(model)
    assert "validatePayload" in reject(call(store, "Import", incoming, context(model)))
    saved, status = call(store, "Export", context(model, "save"))
    assert status == "faulted" and snapshot(saved) == snapshot(incoming)


def test_reentrant_mutation_from_verifier_is_rejected_while_export_remains_pure(model):
    lua, _, adapter = model
    original = adapter.verifyCommit
    lua.globals().originalVerifier = original
    adapter.verifyCommit = lua.eval("""function(before, after, operation, observed)
        local ok, reason = ownedStore:Abort(currentToken)
        assert(ok == nil and reason:find('Reentrant'))
        local candidate, err = ownedStore:Import(before,
            {verified=true,reason='save_load',ownerKey=before.ownerKey})
        assert(candidate == nil and err)
        local exported = ownedStore:Export({verified=true,reason='save',ownerKey=before.ownerKey})
        assert(exported.payload.bank == before.payload.bank)
        return originalVerifier(before,after,operation,observed)
    end""")
    store = create(model)
    lua.globals().ownedStore = store
    payload = view(store).payload
    payload.bank += 11
    token = begin(model, store, payload)
    lua.globals().currentToken = token
    commit(model, store, token)
    assert view(store).payload.bank == 50011


def dual_payload(model):
    # Approved ownership example, represented as policy-owned data. The storage
    # test does not pretend vanilla can apply deferred retired-class progression.
    return table(model, {"schema": 1, "classKind": "dual", "policy": "bg1_sod",
                         "phase": "SOD", "revision": 1, "oldClass": "FIGHTER",
                         "newClass": "THIEF", "oldLevelAtDual": 9,
                         "preResetUsable": 500000, "retiredThreshold": 250000,
                         "retiredUsable": 500000, "retiredBank": 50000,
                         "usable": 0, "bank": 0, "nativeDiscarded": 0,
                         "extension": {"manualChoiceRequired": True}})


def test_immediate_dual_retains_old_bank_and_postdual_new_bank_in_distinct_fields(model):
    store = create(model)
    commit(model, store, begin(model, store, dual_payload(model), "dual"))
    active = view(store).payload
    assert (active.retiredUsable, active.retiredBank, active.usable, active.bank) == (500000, 50000, 0, 0)
    active.bank, active.revision = 200000, 2
    commit(model, store, begin(model, store, active))
    saved = export(model, store)
    reloaded = create(model, saved)
    active = view(reloaded).payload
    assert (active.retiredBank, active.bank) == (50000, 200000)
    assert (active.oldClass, active.newClass, active.preResetUsable, active.retiredThreshold) == (
        "FIGHTER", "THIEF", 500000, 250000)
    active.retiredUsable, active.retiredBank = 550000, 0
    active.usable, active.bank, active.phase, active.revision = 200000, 0, "SOA", 3
    commit(model, reloaded, begin(model, reloaded, active, "advance"))
    final = view(reloaded).payload
    assert (final.retiredUsable, final.usable) == (550000, 200000)
    assert final.extension.manualChoiceRequired is True
    assert (view(store).payload.retiredBank, view(store).payload.bank) == (50000, 200000)


def test_recovery_keeps_uncredited_remainders_and_disable_is_actor_local(model):
    store = create(model)
    other = create(model, envelope(model, owner="run-a:dismissed-owner", bank=9))
    assert "recovery" in reject(call(store, "BeginDisable", 0)).lower()
    token = first(call(store, "BeginRecovery", 0))
    commit(model, store, token)
    reject(call(store, "Begin", 1, view(store).payload, "earn"))
    assert "unreleased" in reject(call(store, "BeginDisable", 1)).lower()
    partially_credited = view(store).payload
    partially_credited.usable, partially_credited.bank = 510000, 40000
    token = first(call(store, "BeginRelease", 1, partially_credited))
    commit(model, store, token)
    assert (view(store).payload.usable, view(store).payload.bank) == (510000, 40000)
    reject(call(store, "BeginDisable", 2))
    remaining = view(store).payload
    remaining.usable, remaining.bank = 550000, 0
    token = first(call(store, "BeginRelease", 2, remaining))
    commit(model, store, token)
    token = first(call(store, "BeginDisable", 3))
    commit(model, store, token)
    assert view(store).mode == "disabled"
    reject(call(store, "BeginRecovery", 4))
    reject(call(store, "Begin", 4, view(store).payload, "earn"))
    disabled = create(model, export(model, store))
    reject(call(disabled, "BeginRecovery", 4))
    assert view(other).payload.bank == 9 and view(other).mode == "active"


def test_disable_checks_retired_bank_too(model):
    store = create(model)
    commit(model, store, begin(model, store, dual_payload(model), "dual"))
    token = first(call(store, "BeginRecovery", 1))
    commit(model, store, token)
    assert view(store).payload.bank == 0 and view(store).payload.retiredBank == 50000
    reject(call(store, "BeginDisable", 2))


@pytest.mark.parametrize("missing", ["validateTransition", "verifyCommit", "bankEmpty"])
def test_missing_adapter_capability_stops_operation_without_losing_existing_data(model, missing):
    model[2][missing] = None
    store = create(model)
    before = snapshot(view(store))
    if missing == "validateTransition":
        assert missing in reject(call(store, "Begin", 0, view(store).payload, "earn"))
    elif missing == "verifyCommit":
        token = begin(model, store, view(store).payload)
        assert missing in reject(call(store, "Commit", token, table(model, {})))
    else:
        token = first(call(store, "BeginRecovery", 0))
        commit(model, store, token)
        before = snapshot(view(store))
        assert missing in reject(call(store, "BeginDisable", 1))
    assert snapshot(view(store)) == before
