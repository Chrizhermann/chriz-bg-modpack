"""Derived-only cap policy and callback guards; native window proof is separate."""
from importlib import import_module
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "research/xp-banking-native/cap_hook.lua"


@pytest.fixture(params=["lua51", "luajit21"])
def model(request):
    lua = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    return lua, lua.execute(SOURCE.read_text(encoding="utf-8"))


def state(lua, **changes):
    fields = dict(eligible=True, policy="bg1_sod", phase="SOD", classKind="single", usableFloor=0)
    fields.update(changes)
    return lua.table_from(fields)


@pytest.mark.parametrize("phase,policy,expected", [
    ("BG1", "bg1_sod", 161000), ("SOD", "bg1_sod", 500000),
    ("SOA", "bg1_sod", 6000000), ("TOB", "bg1_sod_soa", 6000000),
    ("SOA", "bg1_sod_soa", 2950000),
])
def test_campaign_limits_do_not_rewrite_underlying_storage(model, phase, policy, expected):
    lua, m = model
    assert m.Select(state(lua, phase=phase, policy=policy), 8000000, 6000000) == expected


@pytest.mark.parametrize("native,floor,expected", [
    (400000, 0, 400000), (8000000, 600000, 600000),
    (400000, 600000, 400000), (8000000, 0, 500000),
])
def test_native_ceiling_and_adoption_floor(model, native, floor, expected):
    lua, m = model
    assert m.Select(state(lua, usableFloor=floor), native, 900000) == expected


@pytest.mark.parametrize("debit,native_old,expected", [
    (500000, 500000, 0), (500000, 450000, 0),
    (125000, 125000, 375000), (161000, 125000, 339000),
])
def test_shared_dual_cap_uses_owned_old_entitlement(model, debit, native_old, expected):
    lua, m = model
    s = state(lua, classKind="dual", retiredDebit=debit, retiredNativeXP=native_old)
    assert m.Select(s, 8000000, 700000) == expected


def test_ineligible_actor_retains_original_derived_xp(model):
    lua, m = model
    assert m.Select(lua.table_from(dict(eligible=False)), 8000000, 700000) == 700000


@pytest.mark.parametrize("changes", [
    dict(eligible=None), dict(eligible=1), dict(phase="UNKNOWN"), dict(policy="unknown"),
    dict(usableFloor=-1), dict(usableFloor=0.5), dict(classKind="dual"),
    dict(classKind="dual", retiredDebit=100, retiredNativeXP=101),
    dict(classKind="other"), dict(usableFloor=float("inf")),
])
def test_bad_snapshot_is_error_not_silent_empty_bank(model, changes):
    lua, m = model
    value, error = m.Select(state(lua, **changes), 8000000, 700000)
    assert value is None and error


def test_callback_owns_only_derived_xp_and_reports_provider_failure(model):
    lua, m = model
    lua.globals().cap = m
    lua.globals().callbacks = lua.execute(SOURCE.with_name('callback_abi.lua').read_text(encoding='utf-8'))
    lua.execute('''
      -- Match the generated CDerivedStatsTemplate Lua binding, not baseStats.
      -- A proxy rejects unknown reads AND writes, as native userdata does.
      local derived={m_nXP=600000,other=89}
      local stats=setmetatable({}, {
        __index=function(_,key)
          assert(derived[key]~=nil,"CDerivedStats has no member "..key)
          return derived[key]
        end,
        __newindex=function(_,key,value)
          assert(derived[key]~=nil,"CDerivedStats has no member "..key)
          derived[key]=value
        end,
      })
      local sprite={m_derivedStats=stats,m_baseStats={m_xp=600000},bank=17}
      cap.snapshot=function() return {eligible=true,policy="bg1_sod",phase="SOD",classKind="single",usableFloor=0} end
      local reports=0
      cap.report=function() reports=reports+1 end
      cap.BeforeNativeClamp(sprite,8000000)
      assert(sprite.m_derivedStats.m_nXP==500000 and sprite.m_baseStats.m_xp==600000)
      assert(reports==0 and #cap.errors==0)
      assert(sprite.bank==17 and sprite.m_derivedStats.other==89)
      cap.snapshot=function() error("unknown actor ledger") end
      cap.BeforeNativeClamp(sprite,8000000)
      assert(sprite.m_derivedStats.m_nXP==500000 and sprite.m_baseStats.m_xp==600000)
      assert(reports==1 and #cap.errors==1)
      local installed,err=pcall(cap.Install,{researchOnly=true,snapshot=cap.snapshot,
          report=cap.report,callbacks=callbacks})
      assert(not installed and tostring(err):find('EEex required') and cap.installed==nil)
    ''')
