"""Pure banking-policy evidence, not native award-hook or save acceptance.

The authored party entitlements below are already distributed inputs. They do
not assert how any engine build rounds party awards or distributes class XP.
Nothing here installs, bootstraps, writes native XP, or serializes a real save.
"""
from importlib import import_module
from pathlib import Path
import math

import pytest


SOURCE = (Path(__file__).resolve().parents[1]
          / "research/xp-banking/cbmbank_policy.lua")
MAX_EXACT = 2**53 - 1


def test_nested_extension_is_detached_between_immutable_snapshots(model):
    lua, policy = model
    state = adopt(model)
    state.extra = lua.table_from({"nested": lua.table_from({"sentinel": 17})})
    newer, _ = apply(model, state, "Earn", 1)
    newer.extra.nested.sentinel = 99
    assert state.extra.nested.sentinel == 17


@pytest.fixture(params=["lua51", "luajit21"])
def model(request):
    lua = import_module("lupa." + request.param).LuaRuntime(
        unpack_returned_tuples=True)
    policy = lua.execute(SOURCE.read_text(encoding="utf-8"))
    return lua, policy


def result(function, *args):
    value = function(*args)
    return value if isinstance(value, tuple) else (value, None)


def success(function, *args):
    value, reason = result(function, *args)
    assert reason is None, reason
    assert value is not None
    return value


def rejected(function, *args):
    value, reason = result(function, *args)
    assert value is None
    assert isinstance(reason, str) and reason.strip()
    return reason


def snapshot(value):
    if hasattr(value, "items"):
        return {key: snapshot(item) for key, item in value.items()}
    if isinstance(value, float) and math.isnan(value):
        return "<nan>"
    return value


def adopt(model, usable=0, phase="BG1", policy="bg1_sod", kind="single"):
    return success(model[1].Adopt, policy, phase, usable, kind)


def apply(model, state, operation, *args):
    """Every planner and application must leave its input snapshots untouched."""
    policy = model[1]
    before = snapshot(state)
    proposed = success(policy[operation], state, *args)
    assert snapshot(state) == before
    proposal_before = snapshot(proposed)
    updated = success(policy.Apply, state, proposed)
    assert snapshot(state) == before
    assert snapshot(proposed) == proposal_before
    return updated, proposed


@pytest.mark.parametrize("policy,phase,expected", [
    ("bg1_sod", "BG1", 161000), ("bg1_sod", "SOD", 500000),
    ("bg1_sod", "SOA", None), ("bg1_sod", "TOB", None),
    ("bg1_sod_soa", "BG1", 161000),
    ("bg1_sod_soa", "SOD", 500000),
    ("bg1_sod_soa", "SOA", 2950000),
    ("bg1_sod_soa", "TOB", None),
])
def test_only_selected_campaigns_have_caps(model, policy, phase, expected):
    state = adopt(model, policy=policy, phase=phase)
    assert result(model[1].Cap, state) == (expected, None)


@pytest.mark.parametrize("current,ending,tob,saved,expected", [
    ("BG1", 0, 0, None, "BG1"),
    ("BG1", 1, 0, None, "BG1"),  # Endless BG1 is still BG1.
    ("SOD", 1, 0, None, "SOD"),
    ("SOA", 2, 0, None, "SOA"),
    ("TOB", 0, 1, None, "TOB"),
    ("BG1", 2, 0, None, "SOA"),
    ("SOD", 2, 0, "SOD", "SOA"),
    ("SOA", 2, 1, "SOA", "TOB"),
    ("BG1", 1, 0, "SOD", "SOD"),
    ("BG1", 0, 0, "SOA", "SOA"),
    ("SOD", 1, 0, "TOB", "TOB"),
])
def test_campaign_needs_confirmed_flags_and_uses_only_save_owned_progress(
        model, current, ending, tob, saved, expected):
    assert success(model[1].Campaign, current, ending, tob, saved) == expected


@pytest.mark.parametrize("current,ending,tob", [
    ("SOD", 0, 0), ("SOA", 0, 0), ("SOA", 1, 0),
    ("TOB", 0, 0), ("TOB", 2, 0),
])
def test_direct_start_waits_for_initialization_without_guessing(model, current, ending, tob):
    assert "Waiting" in rejected(model[1].Campaign, current, ending, tob, None)
    ending, tob = {"SOD": (1, 0), "SOA": (2, 0), "TOB": (2, 1)}[current]
    assert success(model[1].Campaign, current, ending, tob, None) == current


def test_loading_older_save_and_independent_run_have_no_process_high_water_mark(model):
    policy = model[1]
    old = adopt(model)
    old, _ = apply(model, old, "Earn", 600000)
    saved_old = snapshot(old)
    future, _ = apply(model, old, "Advance", "TOB")
    future, _ = apply(model, future, "Earn", 9000000)
    assert success(policy.Campaign, "TOB", 2, 1, future.phase) == "TOB"
    assert success(policy.Campaign, "BG1", 1, 0, old.phase) == "BG1"
    assert snapshot(old) == saved_old
    assert (old.usable, old.bank) == (161000, 439000)
    independent = adopt(model)
    independent, _ = apply(model, independent, "Earn", 17)
    assert (independent.usable, independent.bank) == (17, 0)
    assert (future.usable, future.bank) == (9600000, 0)


@pytest.mark.parametrize("current", [None, "", "BP1", "BP2", "TUT", "UNKNOWN"])
def test_unsupported_campaign_stays_unsupported_even_with_later_flags(model, current):
    rejected(model[1].Campaign, current, 2, 1, None)


@pytest.mark.parametrize("ending,tob,saved", [
    (-1, 0, None), (3, 0, None), (0.5, 0, None), (None, 0, None),
    ("2", 0, None), (True, 0, None), (float("nan"), 0, None),
    (0, -1, None), (0, 2, None), (0, 0.5, None), (0, None, None),
    (0, "1", None), (0, True, None), (0, float("inf"), None),
    (2, 1, "UNKNOWN"), (2, 1, False),
])
def test_invalid_campaign_inputs_are_reported(model, ending, tob, saved):
    rejected(model[1].Campaign, "BG1", ending, tob, saved)


def test_six_hundred_thousand_example_and_repeat_transitions_conserve_exactly(model):
    state = adopt(model)
    state, earned = apply(model, state, "Earn", 600000)
    assert (state.usable, state.bank) == (161000, 439000)
    assert earned.usableDelta + earned.bankDelta == 600000
    for phase, expected in [
        ("BG1", (161000, 439000)), ("SOD", (500000, 100000)),
        ("SOD", (500000, 100000)), ("SOA", (600000, 0)),
        ("SOA", (600000, 0)), ("TOB", (600000, 0)),
    ]:
        state, transition = apply(model, state, "Advance", phase)
        assert (state.usable, state.bank) == expected
        assert transition.usableDelta + transition.bankDelta == 0


@pytest.mark.parametrize("with_soa", [False, True])
def test_skipped_sod_and_optional_soa_limit_do_not_add_tob_cap(model, with_soa):
    state = adopt(model, policy="bg1_sod_soa" if with_soa else "bg1_sod")
    state, _ = apply(model, state, "Earn", 8000000)
    state, _ = apply(model, state, "Advance", "SOA")
    assert (state.usable, state.bank) == (
        (2950000, 5050000) if with_soa else (8000000, 0))
    state, _ = apply(model, state, "Advance", "TOB")
    state, _ = apply(model, state, "Earn", 12345)
    assert (state.usable, state.bank) == (8012345, 0)


@pytest.mark.parametrize("policy,phase,cap", [
    ("bg1_sod", "BG1", 161000), ("bg1_sod", "SOD", 500000),
    ("bg1_sod_soa", "SOA", 2950000),
])
def test_boundary_and_consecutive_awards_preserve_each_entitlement(model, policy, phase, cap):
    for initial in (0, cap - 1, cap, cap + 1):
        state = adopt(model, initial, phase, policy)
        total = initial
        for amount in (0, 1, 1, cap - 1, cap, cap + 1, 2**40 + 7):
            before_usable, before_bank = state.usable, state.bank
            state, proposed = apply(model, state, "Earn", amount)
            total += amount
            assert state.usable == before_usable + min(amount, max(0, cap - before_usable))
            assert state.usable + state.bank == total
            assert (state.usable - before_usable) + (state.bank - before_bank) == amount
            assert proposed.usableDelta + proposed.bankDelta == amount


@pytest.mark.parametrize("entitlements", [
    (1001,), (334, 334, 333), (167, 167, 167, 167, 167, 166),
])
def test_party_inputs_are_already_split_and_odd_entitlements_are_not_divided_again(
        model, entitlements):
    # Deliberately authored, unequal per-recipient allocations total 1001.
    # This tests the boundary contract, not native rounding or party dispatch.
    increases = []
    for index, entitlement in enumerate(entitlements):
        initial = 160999 - index
        state = adopt(model, initial)
        state, proposed = apply(model, state, "Earn", entitlement)
        assert proposed.usableDelta + proposed.bankDelta == entitlement
        assert state.usable == 161000
        increases.append(state.usable + state.bank - initial)
    assert increases == list(entitlements)
    assert sum(increases) == 1001


def test_multiclass_uses_one_character_cap_and_preserves_class_extensions(model):
    lua, _ = model
    state = adopt(model, 160997, kind="multi")
    state.classDistribution = lua.table_from({"fighter": 80500, "mage": 80497})
    before = snapshot(state.classDistribution)
    state, proposed = apply(model, state, "Earn", 101)
    assert (state.usable, state.bank) == (161000, 98)
    assert proposed.usableDelta == 3
    assert snapshot(state.classDistribution) == before
    state, _ = apply(model, state, "Advance", "SOD")
    assert (state.usable, state.bank) == (161098, 0)
    assert snapshot(state.classDistribution) == before


def test_overcap_adoption_keeps_progress_and_banks_only_future_earned_xp(model):
    state = adopt(model, 700000)
    assert (state.usable, state.bank) == (700000, 0)
    state, _ = apply(model, state, "Earn", 100000)
    assert (state.usable, state.bank) == (700000, 100000)
    state, _ = apply(model, state, "Advance", "SOD")
    assert (state.usable, state.bank) == (700000, 100000)
    state, _ = apply(model, state, "Advance", "SOA")
    assert (state.usable, state.bank) == (800000, 0)


def test_catchup_compares_usable_plus_bank_and_never_creates_repeated_hidden_delta(model):
    state = adopt(model)
    state, _ = apply(model, state, "Earn", 600000)
    for target, total in [(500000, 600000), (750000, 750000),
                          (750000, 750000), (1250000, 1250000), (0, 1250000)]:
        state, proposed = apply(model, state, "CatchUp", target)
        assert state.usable == 161000
        assert state.usable + state.bank == total
        assert proposed.operation == "catch_up"
    state, _ = apply(model, state, "Advance", "SOA")
    state, proposed = apply(model, state, "CatchUp", 1250000)
    assert (state.usable, state.bank) == (1250000, 0)
    assert proposed.usableDelta == proposed.bankDelta == 0


def test_reentrant_plans_are_pure_and_stale_plan_cannot_double_credit(model):
    policy = model[1]
    state = adopt(model, 160999)
    original = snapshot(state)
    first = success(policy.Earn, state, 100)
    concurrent = success(policy.Earn, state, 100)
    assert snapshot(state) == original
    updated = success(policy.Apply, state, first)
    updated_before = snapshot(updated)
    assert "Stale" in rejected(policy.Apply, updated, first)
    rejected(policy.Apply, updated, concurrent)
    assert snapshot(updated) == updated_before
    assert snapshot(state) == original
    updated, _ = apply(model, updated, "Earn", 100)
    assert (updated.usable, updated.bank) == (161000, 199)


def test_extensions_and_bound_policy_are_preserved_without_inplace_mutation(model):
    lua, policy = model
    state = adopt(model)
    state.extension = lua.table_from({"owner": "another-system", "balance": 7123})
    original = snapshot(state)
    proposed = success(policy.Earn, state, 600000)
    proposed.policy = "bg1_sod_soa"
    rejected(policy.Apply, state, proposed)
    assert snapshot(state) == original
    updated, _ = apply(model, state, "Earn", 600000)
    assert snapshot(updated.extension) == original["extension"]
    assert updated.policy == "bg1_sod"


@pytest.mark.parametrize("field,value", [
    ("schema", 2), ("schema", "1"), ("schema", None),
    ("policy", "stricter-new-mode"), ("phase", "UNKNOWN"),
    ("usable", -1), ("usable", 0.5), ("usable", "161000"),
    ("bank", None), ("bank", True), ("bank", float("nan")),
    ("bank", float("inf")), ("bank", 2**53),
    ("revision", -1), ("revision", 0.5), ("revision", False),
])
def test_invalid_or_newer_state_payload_is_not_rewritten(model, field, value):
    lua, policy = model
    state = adopt(model, 123)
    state.extension = lua.table_from({"unknownFutureValue": 98765})
    proposal = success(policy.Earn, state, 7)
    state[field] = value
    before = snapshot(state)
    for operation, args in [
        (policy.Cap, ()), (policy.Earn, (1,)), (policy.Advance, ("SOD",)),
        (policy.CatchUp, (500000,)), (policy.Apply, (proposal,)),
    ]:
        rejected(operation, state, *args)
        assert snapshot(state) == before


@pytest.mark.parametrize("value", [-1, 0.5, None, True, "100", float("nan"),
                                   float("inf"), 2**53])
def test_malformed_entitlements_and_catchup_targets_leave_state_intact(model, value):
    state = adopt(model, 123)
    before = snapshot(state)
    rejected(model[1].Earn, state, value)
    rejected(model[1].CatchUp, state, value)
    assert snapshot(state) == before


def test_dual_class_is_explicitly_unsupported_without_touching_retired_xp_or_bank(model):
    lua, policy = model
    assert "Dual" in rejected(policy.Adopt, "bg1_sod", "BG1", 123, "dual")
    state = lua.table_from({"schema": 1, "policy": "bg1_sod", "phase": "BG1",
                            "classKind": "dual", "usable": 5000, "bank": 439000,
                            "revision": 4, "retiredClassXP": 161000})
    before = snapshot(state)
    for operation, args in [(policy.Earn, (100,)), (policy.Advance, ("SOD",)),
                            (policy.CatchUp, (750000,))]:
        assert "Dual" in rejected(operation, state, *args)
        assert snapshot(state) == before


def test_exact_integer_limit_and_exhausted_revision_fail_without_data_loss(model):
    state = adopt(model)
    state, _ = apply(model, state, "Earn", MAX_EXACT)
    assert (state.usable, state.bank) == (161000, MAX_EXACT - 161000)
    before = snapshot(state)
    rejected(model[1].Earn, state, 1)
    assert snapshot(state) == before
    state, _ = apply(model, state, "Advance", "TOB")
    assert (state.usable, state.bank) == (MAX_EXACT, 0)
    state.revision = MAX_EXACT
    before = snapshot(state)
    rejected(model[1].Earn, state, 0)
    rejected(model[1].Advance, state, "TOB")
    assert snapshot(state) == before


def test_campaign_regression_requires_the_older_snapshot(model):
    state = adopt(model, phase="SOA")
    before = snapshot(state)
    assert "save" in rejected(model[1].Advance, state, "BG1").lower()
    rejected(model[1].Advance, state, "UNKNOWN")
    assert snapshot(state) == before


@pytest.mark.parametrize("field,value", [
    ("schema", 2), ("operation", "unsupported-set"),
    ("bank", 124), ("usable", 1), ("phase", "TOB"),
    ("bankDelta", 124), ("usableDelta", 1),
    ("revision", 99), ("expectedRevision", 99),
])
def test_malformed_plan_cannot_silently_change_entitlement_or_policy(model, field, value):
    policy = model[1]
    state = adopt(model, 161000)
    proposed = success(policy.Earn, state, 123)
    proposed[field] = value
    before, plan_before = snapshot(state), snapshot(proposed)
    rejected(policy.Apply, state, proposed)
    assert snapshot(state) == before
    assert snapshot(proposed) == plan_before


CHAPTER_CAPS = [
    ("CH1", 16000), ("CH2", 16000), ("CH3", 20000), ("CH4", 32000),
    ("CH5", 64000), ("CH6", 85000), ("CH7", 161000),
    ("CH8", 200000), ("CH9", 250000), ("CH10", 350000), ("CH11", 420000),
    ("CH12", 500000), ("CH13", 500000), ("CH14", 1000000), ("CH15", 2500000),
    ("CH16", 2900000), ("CH17", 3250000), ("CH18", 3500000), ("CH19", 3500000),
    ("CH20", 5000000), ("CH21", 8000000), ("CH22", 8900000),
]


@pytest.mark.parametrize("phase,expected", CHAPTER_CAPS)
def test_chapter_caps_policy_returns_exact_chapter_limits(model, phase, expected):
    state = adopt(model, policy="chapter_caps", phase=phase)
    assert result(model[1].Cap, state) == (expected, None)


@pytest.mark.parametrize("current,ending,tob,chapter,saved,standalone,expected", [
    # EET chapters 1..22
    ("BG1", 0, 0, 1, None, False, "CH1"),
    ("BG1", 0, 0, 2, "CH1", False, "CH2"),
    ("BG1", 0, 0, 7, "CH6", False, "CH7"),
    ("SOD", 1, 0, 7, "CH7", False, "CH7"),
    ("SOD", 1, 0, 8, "CH7", False, "CH8"),
    ("SOD", 1, 0, 12, "CH11", False, "CH12"),
    ("SOD", 1, 0, 13, "CH12", False, "CH13"),
    ("SOA", 2, 0, 13, "CH12", False, "CH13"),
    ("SOA", 2, 0, 14, "CH13", False, "CH14"),
    ("SOA", 2, 0, 15, "CH14", False, "CH15"),
    ("SOA", 2, 0, 19, "CH18", False, "CH19"),
    ("TOB", 2, 1, 20, "CH19", False, "CH20"),
    ("TOB", 2, 1, 21, "CH20", False, "CH21"),
    ("TOB", 2, 1, 22, "CH21", False, "CH22"),
    # EET intermediate transition frame: ENDOFBG1=2 or INTOB=1 before Chapter updates
    ("SOA", 2, 0, 7, "CH7", False, "CH7"),
    ("SOA", 2, 0, 12, "CH12", False, "CH12"),
    ("TOB", 2, 1, 19, "CH19", False, "CH19"),
    # Standalone chapters (BG1 1..7, SOD 7..13, SOA 1..7 -> CH13..CH19, TOB 8..10 -> CH20..CH22)
    ("BG1", 0, 0, 1, None, True, "CH1"),
    ("BG1", 0, 0, 5, "CH4", True, "CH5"),
    ("SOD", 0, 0, 7, None, True, "CH7"),
    ("SOD", 0, 0, 12, "CH11", True, "CH12"),
    ("SOA", 0, 0, 1, None, True, "CH13"),
    ("SOA", 0, 0, 2, "CH13", True, "CH14"),
    ("SOA", 0, 0, 3, "CH14", True, "CH15"),
    ("SOA", 0, 0, 7, "CH18", True, "CH19"),
    ("TOB", 0, 1, 8, None, True, "CH20"),
    ("TOB", 0, 1, 9, "CH20", True, "CH21"),
    ("TOB", 0, 1, 10, "CH21", True, "CH22"),
    # Save-owned high-water mark prevents chapter regression within a run
    ("SOA", 2, 0, 14, "CH16", False, "CH16"),
    ("SOA", 0, 0, 2, "CH15", True, "CH15"),
])
def test_chapter_phase_resolves_eet_and_standalone_without_collision(
        model, current, ending, tob, chapter, saved, standalone, expected):
    assert success(
        model[1].ChapterPhase, current, ending, tob, chapter, saved, standalone
    ) == expected


@pytest.mark.parametrize("current,ending,tob,chapter,saved,standalone", [
    ("BG1", 0, 0, 0, None, False),
    ("SOD", 1, 0, 1, None, False),
    ("SOA", 2, 0, 1, None, False),
    ("TOB", 2, 1, 13, None, False),
    ("SOA", 0, 0, 0, None, True),
    ("TOB", 0, 1, 2, None, True),
    ("BG1", 0, 0, 8, None, False),
    ("SOD", 1, 0, 14, None, False),
    ("SOA", 2, 0, 20, None, False),
    ("TOB", 2, 1, 23, None, False),
    ("SOA", 0, 0, 8, None, True),
    ("TOB", 0, 1, 11, None, True),
    ("BG1", 0, 0, 1, "BG1", False),
])
def test_chapter_phase_rejects_uninitialized_or_out_of_range_chapters(
        model, current, ending, tob, chapter, saved, standalone):
    rejected(model[1].ChapterPhase, current, ending, tob, chapter, saved, standalone)


def test_chapter_caps_earn_and_advance_step_by_step(model):
    state = adopt(model, usable=0, phase="CH1", policy="chapter_caps")
    state, _ = apply(model, state, "Earn", 50000)
    assert (state.usable, state.bank, state.phase) == (16000, 34000, "CH1")
    state, plan_ch2 = apply(model, state, "Advance", "CH2")
    assert (state.usable, state.bank, plan_ch2.usableDelta) == (16000, 34000, 0)
    state, plan_ch3 = apply(model, state, "Advance", "CH3")
    assert (state.usable, state.bank, plan_ch3.usableDelta) == (20000, 30000, 4000)
    state, plan_ch4 = apply(model, state, "Advance", "CH4")
    assert (state.usable, state.bank, plan_ch4.usableDelta) == (32000, 18000, 12000)
    state, plan_ch5 = apply(model, state, "Advance", "CH5")
    assert (state.usable, state.bank, plan_ch5.usableDelta) == (50000, 0, 18000)
    rejected(model[1].Advance, state, "CH4")

