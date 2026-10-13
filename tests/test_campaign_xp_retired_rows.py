"""Installed table/provider contracts for retired rows; no engine execution."""
from pathlib import Path
import pytest
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
SOURCE=Path(__file__).resolve().parents[1]/'research/xp-banking-native'

@pytest.fixture(params=[Lua51,LuaJIT],ids=['Lua51','LuaJIT'])
def lua(request):
    r=request.param(unpack_returned_tuples=True)
    r.globals().Rows=r.execute((SOURCE/'dual_retired_rows.lua').read_text())
    r.execute('''
      freed=0;closed=0;skillReads=0
      tables={
       CLASTEXT={{label='EXTRA',CLASSID='1',KITID='16384',MIXED='21'},
                 {label='THIEF',CLASSID='4',KITID='0x4000',MIXED='22'}},
       WEAPPROF={{label='EXTRA',ID='44',NAME_REF='1'},
                 {label='SECOND',ID='101',NAME_REF='31'},
                 {label='FIRST',ID='89',NAME_REF='32'},
                 {label='ALIAS',ID='101',NAME_REF='33'}}}
      function EEex_Resource_Load2DA(name)
       local rows=tables[name];if not rows then return nil end
       return {getDimensions=function()return 5,#rows end,
        getRowLabel=function(_,i)return rows[i+1].label end,
        getAtLabels=function(_,column,label)
         for _,row in ipairs(rows)do if row.label==label then return row[column]or'*'end end
         return '*'
        end,free=function()freed=freed+1 end}
      end
      function Infinity_FetchString(n)return 'translated '..n end
      account={oldLevel=10,oldClass=4,oldKit=0x4000}
      rules={Plan=function()return {oldLevel=10,target=11,profPoints=2,skillPoints=25}end,
       Cap=function(_,_,stat)return stat==101 and 2 or 5 end}
      manual={ReadSkills=function()return {10,20,30,40,50,60,70}end,
       ReadOld=function(_,stat)return stat==101 and 4 or 1 end}
      nativeRows={};for i=0,6 do nativeRows[i+1]={id=i,nameStrref=40+i,value=(i+1)*10,
       display=(i+1)*10+25,limit=225,percentage=i==6 and 0 or 100}end
      skills={Read=function()skillReads=skillReads+1;return nativeRows end}
      hlas={Open=function()return {points=2,rows={{id=0,descriptor={effect='GA_A',nameStrref=100}}},
       CanChoose=function()return true end,Close=function()closed=closed+1;return true end}end}
      builder=Rows.New(skills,hlas)
    ''')
    return r

def test_installed_order_aliases_disabled_skills_and_above_cap_preservation(lua):
    lua.execute('''
      local model,before=builder.Build({},account,11,rules,manual)
      assert(model.className=='translated 22' and freed==2)
      assert(#model.proficiencies==2 and model.proficiencies[1].stat==101)
      assert(model.proficiencies[1].value==4 and model.proficiencies[1].limit==2)
      assert(#model.skills==6 and model.skills[6].id==5 and model.skills[1].limit==225)
      assert(#before==7 and before[7]==70)
      assert(model.hlaPoints==2 and model.hlas[1].label=='translated 100')
      model.onClose();assert(closed==1)
    ''')

def test_cosmetic_name_missing_is_not_installation_gate(lua):
    lua.execute('''tables.CLASTEXT=nil
      local model=builder.Build({},account,11,rules,manual)
      assert(model.className=='Thief');model.onClose()
    ''')

def test_zero_budgets_need_no_unrelated_skill_or_proficiency_queries(lua):
    lua.execute('''
      tables.WEAPPROF=nil
      rules.Plan=function()return {oldLevel=10,target=11,profPoints=0,skillPoints=0}end
      local model=builder.Build({},account,11,rules,manual)
      assert(#model.proficiencies==0 and #model.skills==0 and skillReads==0)
      model.onClose()
    ''')

def test_hla_bad_descriptor_frees_detached_native_catalog(lua):
    lua.execute('''
      hlas.Open=function()return {points=1,rows={{id=0}},CanChoose=function()return true end,
       Close=function()closed=closed+1;return true end}end
      assert(not pcall(builder.Build,{},account,11,rules,manual));assert(closed==1)
    ''')


def test_nonthrowing_uncertain_native_cleanup_is_propagated(lua):
    lua.execute('''
      hlas.Open=function()return {points=0,rows={},CanChoose=function()return false end,
       Close=function()closed=closed+1;return nil,'native cleanup uncertain'end}end
      local model=builder.Build({},account,11,rules,manual)
      local ok,why=pcall(model.onClose)
      assert(not ok and tostring(why):find('native cleanup uncertain')and closed==1)
    ''')

def test_skill_revalidation_uses_current_caps_and_rejects_disabled_choice(lua):
    lua.execute('''
      local before=manual.ReadSkills();local choices={skills={{id=0,delta=10}}}
      assert(builder.ValidateSkills({},account,choices,before))
      nativeRows[1].limit=15
      assert(not pcall(builder.ValidateSkills,{},account,choices,before))
      nativeRows[1].limit=225;nativeRows[1].percentage=0
      assert(not pcall(builder.ValidateSkills,{},account,choices,before))
      nativeRows[1].percentage=100;nativeRows[1].value=11
      assert(not pcall(builder.ValidateSkills,{},account,choices,before))
    ''')
