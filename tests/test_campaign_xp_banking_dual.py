"""Immediate dual and class-owned XP checks; no native reset or level-up claim."""
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "research/xp-banking"
MAX = 2**53 - 1


@pytest.fixture(params=["lua51", "luajit21"])
def model(request):
    lua = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    return lua, lua.execute((ROOT / "cbmbank_dual.lua").read_text(encoding="utf-8"))


def unpack(call):
    return call if isinstance(call, tuple) else (call, None)


def ok(call):
    result, reason = unpack(call)
    assert reason is None, reason
    assert result is not None
    return result


def bad(call):
    result, reason = unpack(call)
    assert result is None
    assert isinstance(reason, str) and reason


def snap(obj):
    return {k: snap(v) for k, v in obj.items()} if hasattr(obj, "items") else obj


def start(model, *, usable=500000, bank=50000, threshold=500000,
          phase="SOD", policy="bg1_sod", **extra):
    lua, m = model
    before = lua.table_from(dict(schema=1, classKind="single", policy=policy,
                                 phase=phase, revision=4, usable=usable, bank=bank, **extra))
    metadata = lua.table_from(dict(oldClass=2, newClass=4, oldLevel=10,
                                  retiredThreshold=threshold))
    original = snap(before)
    out = ok(m.Start(before, metadata))
    assert snap(before) == original
    return out


def apply(model, state, op, *args):
    m = model[1]
    before = snap(state)
    plan = ok(m[op](state, *args))
    planned = snap(plan)
    out = ok(m.Apply(state, plan))
    assert snap(state) == before
    assert snap(plan) == planned
    return out, plan


def amounts(state):
    return state.retiredUsable, state.retiredBank, state.usable, state.bank


def test_approved_example_immediate_dual_keeps_each_class_earnings(model):
    s = start(model)
    assert amounts(s) == (500000, 50000, 0, 0)
    assert s.oldLevelAtDual == 10
    s, _ = apply(model, s, "Earn", 200000)
    assert amounts(s) == (500000, 50000, 0, 200000)
    s, _ = apply(model, s, "Advance", "SOA")
    assert amounts(s) == (550000, 0, 200000, 0)
    status = ok(model[1].Status(s))
    assert (status.entitlement, status.usable, status.bank) == (750000, 750000, 0)
    assert s.oldLevelAtDual == 10  # Policy never grants levels by writing a byte.
    again, _ = apply(model, s, "Advance", "SOA")
    assert amounts(again) == amounts(s)


def test_old_bank_uses_exact_baseline_for_installed_nonstandard_threshold(model):
    s = start(model, threshold=450000)
    assert s.retiredThreshold == 450000
    assert (s.retiredUsable, s.nativeDiscarded) == (500000, 0)
    s, _ = apply(model, s, "Earn", 200000)
    s, _ = apply(model, s, "Advance", "SOA")
    assert amounts(s) == (550000, 0, 200000, 0)


def test_zero_bank_dual_keeps_vanilla_retired_threshold_accounting(model):
    s = start(model, usable=80000, bank=0, threshold=64000, phase="BG1")
    assert (s.retiredUsable, s.nativeDiscarded) == (64000, 16000)
    s, _ = apply(model, s, "Earn", 120000)
    assert amounts(s) == (64000, 0, 97000, 23000)
    assert ok(model[1].Status(s)).entitlement + s.nativeDiscarded == 200000


@pytest.mark.parametrize("native,expected", [
    (None, (550000, 0, 200000, 0)),
    (525000, (525000, 25000, 0, 200000)),
    (600000, (550000, 0, 50000, 150000)),
    (100000, (500000, 50000, 0, 200000)),
    (0, (500000, 50000, 0, 200000)),
])
def test_retained_native_ceiling_preserves_uncredited_class_partitions(model, native, expected):
    s = start(model)
    s, _ = apply(model, s, "Earn", 200000)
    s, _ = apply(model, s, "Advance", "SOA", native)
    assert amounts(s) == expected
    assert ok(model[1].Status(s, native)).entitlement == 750000


def test_bg1_to_sod_then_soa_old_awards_release_first(model):
    s = start(model, usable=161000, bank=439000, threshold=125000, phase="BG1")
    s, _ = apply(model, s, "Earn", 200000)
    s, _ = apply(model, s, "Advance", "SOD")
    assert amounts(s) == (500000, 100000, 0, 200000)
    s, _ = apply(model, s, "Advance", "SOA")
    assert amounts(s) == (600000, 0, 200000, 0)


def test_optional_soa_cap_and_skipped_campaign_release(model):
    s = start(model, bank=2600000, policy="bg1_sod_soa")
    s, _ = apply(model, s, "Earn", 200000)
    old = snap(s)
    soa, _ = apply(model, s, "Advance", "SOA")
    assert amounts(soa) == (2950000, 150000, 0, 200000)
    tob, _ = apply(model, soa, "Advance", "TOB")
    skipped, _ = apply(model, s, "Advance", "TOB")
    assert amounts(tob) == amounts(skipped) == (3100000, 0, 200000, 0)
    assert snap(s) == old


def test_new_earnings_never_advance_or_refill_retired_account(model):
    s = start(model)
    s, _ = apply(model, s, "Advance", "SOA")
    before = s.retiredUsable, s.retiredBank
    for amount in [1, 3, 100000, 9000000]:
        s, _ = apply(model, s, "Earn", amount)
        assert (s.retiredUsable, s.retiredBank) == before
    assert s.usable == 9100004


def test_overcap_old_progress_is_retained_and_future_active_earnings_bank(model):
    s = start(model, usable=600000, bank=90000)
    s, _ = apply(model, s, "Earn", 70000)
    assert amounts(s) == (600000, 90000, 0, 70000)


@pytest.mark.parametrize("field,value", [
    ("schema", 2), ("classKind", "multi"), ("usable", None), ("bank", None),
    ("usable", -1), ("bank", -1), ("bank", 0.5), ("bank", float("inf")),
    ("revision", MAX), ("policy", "unknown"), ("phase", "UNKNOWN"),
])
def test_invalid_source_is_reported_without_partial_dual(model, field, value):
    lua, m = model
    source = dict(schema=1, classKind="single", policy="bg1_sod", phase="SOD",
                  revision=0, usable=500000, bank=50000)
    source[field] = value
    bad(m.Start(lua.table_from(source), lua.table_from(dict(
        oldClass=2, newClass=4, oldLevel=10, retiredThreshold=500000))))


@pytest.mark.parametrize("field,value", [
    ("oldClass", 0), ("oldClass", 256), ("newClass", 2), ("newClass", None),
    ("oldLevel", 0), ("oldLevel", 256), ("retiredThreshold", 500001),
    ("retiredThreshold", -1), ("retiredThreshold", None),
])
def test_invalid_installed_metadata_is_reported(model, field, value):
    lua, m = model
    source = lua.table_from(dict(schema=1, classKind="single", policy="bg1_sod",
                                phase="SOD", revision=0, usable=500000, bank=50000))
    meta = dict(oldClass=2, newClass=4, oldLevel=10, retiredThreshold=500000)
    meta[field] = value
    bad(m.Start(source, lua.table_from(meta)))


@pytest.mark.parametrize("amount", [-1, 0.5, "1", True, None, float("inf"), float("nan"), MAX])
def test_invalid_and_overflow_earnings_leave_snapshot_unchanged(model, amount):
    s = start(model)
    before = snap(s)
    bad(model[1].Earn(s, amount))
    assert snap(s) == before


@pytest.mark.parametrize("field", ["retiredUsable", "retiredBank", "usable", "bank",
                                  "oldClass", "newClass", "preResetBank", "nativeDiscarded"])
def test_plan_tampering_cannot_move_or_create_class_xp(model, field):
    s = start(model)
    p = ok(model[1].Earn(s, 123))
    p.after[field] += 1
    bad(model[1].Apply(s, p))
    assert amounts(s) == (500000, 50000, 0, 0)


def test_stale_plan_older_save_and_extensions_are_preserved(model):
    lua, m = model
    ext = lua.table_from({"future": "keep"})
    s = start(model, extra=ext)
    a = ok(m.Earn(s, 7))
    b = ok(m.Earn(s, 13))
    newer = ok(m.Apply(s, a))
    bad(m.Apply(newer, b))
    assert ok(m.Apply(s, b)).bank == 13
    assert newer.extra.future == "keep"
    assert s.bank == 0
    bad(m.Advance(newer, "BG1"))
    for invalid in [-1, 0.5, "500000", True]:
        bad(m.Advance(newer, "SOA", invalid))


def test_same_campaign_notification_does_not_cash_out_changed_ceiling(model):
    s = start(model)
    s, _ = apply(model, s, "Earn", 10000)
    later, _ = apply(model, s, "Advance", "SOD", MAX)
    assert amounts(later) == amounts(s)


def test_sum_near_exact_storage_bound_remains_conserved(model):
    s = start(model, bank=MAX - 500000 - 1)
    s, _ = apply(model, s, "Earn", 1)
    s, _ = apply(model, s, "Advance", "TOB")
    assert ok(model[1].Status(s)).entitlement == MAX
    bad(model[1].Earn(s, 1))


def test_nested_extension_tampering_cannot_rewrite_source_or_applied_state(model):
    lua, m = model
    extra = lua.table_from({"nested": lua.table_from({"sentinel": 17})})
    s = start(model, extra=extra)
    extra.nested.sentinel = 23
    assert s.extra.nested.sentinel == 17
    p = ok(m.Earn(s, 1))
    p.after.extra.nested.sentinel = 999
    assert s.extra.nested.sentinel == 17
    after = ok(m.Apply(s, p))
    assert after.extra.nested.sentinel == 17
    after.extra.nested.sentinel = 41
    assert s.extra.nested.sentinel == 17


def test_missing_native_metadata_cannot_be_supplied_by_old_extensions(model):
    lua, m = model
    source = lua.table_from(dict(schema=1, classKind="single", policy="bg1_sod",
                                phase="SOD", revision=0, usable=500000, bank=50000,
                                newClass=4, oldLevelAtDual=10, oldClass=2))
    for missing in ["newClass", "oldClass", "oldLevel"]:
        meta = dict(oldClass=2, newClass=4, oldLevel=10, retiredThreshold=500000)
        del meta[missing]
        bad(m.Start(source, lua.table_from(meta)))
