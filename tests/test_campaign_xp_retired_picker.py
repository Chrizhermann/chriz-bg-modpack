"""Detached choice and UI binding checks; no native menu render/game execution."""
from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT

SOURCE = Path(__file__).resolve().parents[1] / "research/xp-banking-native"


@pytest.fixture(params=[Lua51, LuaJIT], ids=["Lua51", "LuaJIT"])
def lua(request):
    runtime = request.param(unpack_returned_tuples=True)
    runtime.globals().Module = runtime.execute((SOURCE / "dual_retired_picker.lua").read_text())
    runtime.execute('''
      function prepared()
       return {className="Fighter",oldLevel=10,target=11,profPoints=2,skillPoints=13,
        proficiencies={{stat=101,label="Long sword",value=2,limit=3},
                       {stat=89,label="Bastard sword",value=1,limit=5}},
        skills={{id="locks",label="Open locks",value=250,limit=255},
                {id=7,label="Find traps",value=10,limit=255}}}
      end
      picker=Module.New()
    ''')
    return runtime


def test_choices_detached_and_native_input_order_preserved(lua):
    lua.execute('''
      source=prepared();picker.Begin(source)
      source.proficiencies[1].value=0
      assert(picker.Adjust("proficiencies",1,1))
      assert(picker.Adjust("proficiencies",2,1))
      assert(picker.Adjust("skills",1,5))
      assert(picker.Adjust("skills",2,8))
      assert(picker.CanContinue())
      local c=picker.Choices()
      assert(c.proficiencies[1].stat==101 and c.proficiencies[1].delta==1)
      assert(c.proficiencies[2].stat==89 and c.proficiencies[2].delta==1)
      assert(c.skills[1].id=="locks" and c.skills[1].delta==5)
      assert(c.skills[2].id==7 and c.skills[2].delta==8)
      assert(c.unusedProfPoints==0 and c.unusedSkillPoints==0)
      c.skills[1].delta=200
      local view=picker.View();view.skills[1].value=1
      assert(picker.View().skills[1].value==250 and picker.Choices().skills[1].delta==5)
      assert(source.skills[1].value==250)
    ''')


@pytest.mark.parametrize("kind,index,amount", [
    ("proficiencies", 1, 2), ("proficiencies", 2, 3), ("skills", 1, 6),
    ("skills", 2, 14), ("skills", 0, 1), ("skills", 9, 1),
    ("skills", 1, -1), ("other", 1, 1), ("skills", 1, 0), ("skills", 1.5, 1),
])
def test_illegal_selection_preserves_budget(lua, kind, index, amount):
    lua.execute("picker.Begin(prepared())")
    assert lua.globals().picker.Adjust(kind, index, amount) is False
    view = lua.globals().picker.View()
    assert view.unusedProfPoints == 2 and view.unusedSkillPoints == 13


def test_subtraction_can_only_undo_current_selection_and_cancel_reopens(lua):
    lua.execute('''
      picker.Begin(prepared())
      assert(picker.Adjust("skills",2,10))
      assert(not picker.Adjust("skills",2,-11))
      assert(picker.Adjust("skills",2,-10))
      assert(picker.View().unusedSkillPoints==13)
      assert(not picker.CanContinue())
      assert(not pcall(picker.Begin,prepared()))
      picker.Cancel();assert(not picker.IsOpen() and not picker.CanContinue())
      picker.Begin(prepared());assert(picker.Choices().skills[2].delta==0)
    ''')


def test_caps_do_not_require_old_values_to_match_and_unused_points_reported(lua):
    lua.execute('''
      local p=prepared();p.proficiencies[1].value=5;p.proficiencies[1].limit=3
      p.proficiencies[2].value=5;p.skills={}
      picker.Begin(p)
      assert(picker.CanContinue())
      assert(not picker.CanAdjust("proficiencies",1,1))
      assert(picker.View().proficiencies[1].value==5)
      assert(picker.Choices().unusedProfPoints==2 and picker.Choices().unusedSkillPoints==13)
    ''')


@pytest.mark.parametrize("mutation", [
    "p.proficiencies[2].stat=p.proficiencies[1].stat", "p.skills[2].id=p.skills[1].id",
    "p.proficiencies[4]=p.proficiencies[2]", "p.profPoints=-1", "p.target=p.oldLevel",
    "p.skills[1].limit=256", "p.proficiencies[1].limit=8", "p.skills[1].value=0/0",
])
def test_invalid_native_preparation_does_not_publish_partial_page(lua, mutation):
    lua.execute("local p=prepared();" + mutation + ";assert(not pcall(picker.Begin,p));assert(not picker.IsOpen())")


def test_ui_binding_updates_rows_and_drops_only_detached_choices(lua):
    lua.execute('''
      local popped=0
      local g={Infinity_PopMenu=function(name)assert(name=="CBMD_OLD_PICKER");popped=popped+1 end}
      local binding=Module.Bind(picker,g)
      assert(not g.CBMDOldPickerCanContinue())
      picker.Begin(prepared());binding.ResetSelection()
      assert(g.CBMDOldPickerTitle=="Fighter: level 10 to 11")
      assert(g.CBMDOldPickerCanAdjust("proficiencies",1))
      assert(g.CBMDOldPickerAdjust("proficiencies",1))
      assert(g.CBMDOldPickerProfRows[1].delta==1)
      assert(g.CBMDOldPickerProfBudget=="1 points remaining")
      g.CBMDOldPickerSkillRow=2;assert(g.CBMDOldPickerAdjust("skills",10))
      g.CBMDOldPickerCancel()
      assert(popped==1 and not picker.IsOpen() and #g.CBMDOldPickerProfRows==0)
      g.CBMDOldPickerClosed();assert(popped==1)
      picker.Begin(prepared());g.CBMDOldPickerClosed();assert(not picker.IsOpen())
      assert(not pcall(Module.Bind,picker,g))
    ''')


def test_menu_source_has_external_controls_and_owned_continue():
    source = (SOURCE / "dual_retired_menu.menu").read_text()
    # Structural only. Engine parser/render acceptance remains a separate test.
    assert source.count("list\n") == 3
    assert "CBMDOldPickerContinue()" in source
    assert "CBMDOldPickerClosed()" in source
    assert "MakeDualClass" not in source and "StartEditing" not in source
    for fragment in source.split("list\n")[1:]:
        assert fragment.index("column") < fragment.index("table '")


def test_hla_choices_use_provider_and_preserve_descriptors_and_dependencies(lua):
    lua.execute('''
      local p=prepared();p.profPoints=0;p.skillPoints=0;p.hlaPoints=4
      p.hlas={{id=0,label="First",descriptor={effect="GA_FIRST",maxRank=2}},
              {id=3,label="Dependent",descriptor={effect="AP_NEXT",prerequisite="GA_FIRST"}}}
      p.canChooseHLA=function(id,selected)
       local first,next=0,0
       for _,v in ipairs(selected)do if v==0 then first=first+1 else next=next+1 end end
       selected[#selected+1]=999 -- provider cannot mutate picker sequence
       return id==0 and first<2 or id==3 and first>0 and next<2
      end
      picker.Begin(p);p.hlas[1].descriptor.effect="CHANGED"
      assert(not picker.Adjust("hlas",2,1))
      assert(picker.Adjust("hlas",1,1) and picker.Adjust("hlas",2,1))
      assert(not picker.Adjust("hlas",1,-1)) -- would break prerequisite
      assert(picker.Adjust("hlas",1,1) and picker.Adjust("hlas",2,1))
      assert(picker.CanContinue())
      local choices=picker.Choices()
      assert(#choices.hlas==4 and choices.hlas[1].id==0 and choices.hlas[2].id==3)
      assert(choices.hlas[1].descriptor.effect=="GA_FIRST")
      assert(choices.unusedHlaPoints==0 and picker.View().canChooseHLA==nil)
      choices.hlas[1].descriptor.effect="ALSO_CHANGED"
      assert(picker.Choices().hlas[1].descriptor.effect=="GA_FIRST")
      assert(picker.Adjust("hlas",1,-1)) -- one earlier prerequisite still exists
      assert(not picker.CanContinue() and picker.View().unusedHlaPoints==1)
      picker.Cancel();assert(not picker.IsOpen())
    ''')


def test_hla_budget_over_native_batch_limit_is_retained(lua):
    lua.execute('''
      local p=prepared();p.profPoints=0;p.skillPoints=0;p.hlaPoints=51
      p.hlas={{id=7,label="Repeatable",descriptor={effect="GA_REPEAT"}}}
      p.canChooseHLA=function(id,selected)return id==7 and #selected<51 end
      picker.Begin(p)
      for i=1,51 do assert(picker.Adjust("hlas",1,1))end
      assert(picker.CanContinue() and #picker.Choices().hlas==51)
      assert(not picker.Adjust("hlas",1,1))
      assert(picker.Adjust("hlas",1,-1) and picker.Adjust("hlas",1,1))
    ''')


def test_picker_closes_native_detached_catalog_once(lua):
    lua.execute('''
      local p=prepared();local closed=0
      p.onClose=function()closed=closed+1 end
      picker.Begin(p);assert(picker.View().onClose==nil)
      picker.Cancel();picker.Cancel();assert(closed==1)
      picker.Begin(p);picker.Cancel();assert(closed==2)
    ''')


def test_hla_exhausted_catalog_reports_unused_and_ui_binds(lua):
    lua.execute('''
      local p=prepared();p.profPoints=0;p.skillPoints=0;p.hlaPoints=2
      p.hlas={{id=1,label="Restricted",description="Installed restriction",descriptor={effect="GA_R"}}}
      p.canChooseHLA=function()return false,"Unavailable"end
      local g={};local binding=Module.Bind(picker,g)
      picker.Begin(p);binding.ResetSelection()
      assert(picker.CanContinue() and picker.Choices().unusedHlaPoints==2)
      assert(g.CBMDOldPickerHasHlas and not g.CBMDOldPickerHlaPage)
      assert(g.CBMDOldPickerHlaDetail()=="Installed restriction")
      assert(not g.CBMDOldPickerCanAdjust("hlas",1))
      g.CBMDOldPickerClosed();assert(#g.CBMDOldPickerHlaRows==0)
    ''')


@pytest.mark.parametrize("mutation", [
    "p.hlaPoints=-1", "p.hlaPoints=1;p.canChooseHLA=nil",
    "p.hlas[2]=p.hlas[1]", "p.hlas[3]=p.hlas[1]", "p.hlas[1].descriptor=nil",
])
def test_hla_invalid_preparation_never_publishes(lua, mutation):
    lua.execute('''local p=prepared();p.hlaPoints=1
      p.hlas={{id=1,label="One",descriptor={effect="GA_ONE"}}}
      p.canChooseHLA=function()return true end
    ''' + mutation + ";assert(not pcall(picker.Begin,p));assert(not picker.IsOpen())")
