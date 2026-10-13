"""Read-only facade contracts on Lua 5.1/LuaJIT; native PE proof is separate."""
from importlib import import_module
from pathlib import Path
import pytest

ROOT=Path(__file__).parent

@pytest.fixture(params=["lua51","luajit21"])
def runtime(request):
    lua=import_module("lupa."+request.param).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().H=lua.execute((ROOT/"dual_old_hla.lua").read_text())
    lua.execute('''
      profile={gameTimestamp=77,gameSize=88,functions={},listVtable=100,listDestructor=120,constants={first_level=1,rate=2,change_level=3,new_rate=4}}
      for _,name in ipairs({'num_abilities','set_level','class_string','get_at','scan','cstring_destroy',
       'get_abilities','complete_abilities','ability_construct','cstring_construct_chars','cstring_assign_chars',
       'resref_construct_cstring','check_enabled','get_ai_type','allocate','array_construct','array_grow','release'})do
       profile.functions[name]={rva=10,bytes='aa',name=name}
      end
      function EEex_GetImageBase()return 4096 end
      function EEex_ReadU16(p)if p==4096 then return 0x5a4d end return 0x8664 end
      function EEex_ReadU32(p)
       if p==4096+0x3c then return 256 elseif p==4352 then return 0x4550
       elseif p==4360 then return 77 elseif p==4352+0x50 then return 88 end error('bad read')
      end
      function EEex_ReadU8()return 0xaa end
      function EEex_Read64()return 4096+120 end
      function EEex_LoadLibrary()return 20 end
      function EEex_GetProcAddressInternal(_,name)return name end
      function EEex_TryLabel()return 300 end
      function EEex_Malloc()return 600 end
      function EEex_Free()end
      function EEex_Write64()end
      function EEex_JITNearAsLuaFunction(name,assembly)_G[name]=function()return true end end
      function EEex_UDToPtr(o)return o.pointer end
      EngineGlobals={g_pBaldurChitin={m_pObjectGame={m_ruleTables={pointer=42}}}}
      actor={pointer=4660,incarnation='123456789abcdef0'}
      identity={Query=function(a)return {incarnation=a.incarnation}end}
      calls={close=0,choose=0,pending=0};zero=false;badRow=false
      exports={
       CBMDHLA_LuaOpen=function(address,cls,kit,before,after)
        assert(address=='1234'and cls=='2'and kit=='16384'and before=='19'and after=='70')
        return '1','abcdef0123456789',zero and '0'or'51','24',zero and'0'or'2','1'
       end,
       CBMDHLA_LuaRow=function(handle,index)
        assert(handle=='abcdef0123456789')
        if badRow then return '0'end
        return '1','ICON','1234','1','99','200',index=='0'and'GA_A'or'AP_B','GA_A','*','ALL_GOOD'
       end,
       CBMDHLA_LuaChoose=function(handle,address,index,chosen,pending)
        assert(handle=='abcdef0123456789'and address=='1234')
        calls.choose=calls.choose+1;calls.chosen=chosen;calls.pendingWire=pending
        return index=='1'and'0'or'1'
       end,
       CBMDHLA_LuaClose=function(handle)assert(handle=='abcdef0123456789');calls.close=calls.close+1;return closeFailure and'-1'or'1'end,
       CBMDHLA_LuaDeliver=function(address,cls,owner,wire)calls.delivery=wire;return '1','51','0'end,
       CBMDHLA_LuaPrepareManual=function(address,owner,wire)calls.manual=wire;return '1','f0123456789abcde'end,
       CBMDHLA_LuaClearManual=function(token)assert(token=='f0123456789abcde');return '1'end
      }
      function EEex_ExposeToLua(export,name)_G[name]=exports[export]end
      H.Install{researchOnly=true,dllPath='synthetic',manualModule=1,profiles={profile},identity=identity,
       pending=function(a)assert(a==actor);calls.pending=calls.pending+1;return {{descriptor={schema=1,effect='GA_PRIOR'}}}end}
      account={oldClass=2,oldKit=16384,oldLevel=19,ownerKey='1234567890abcdef1234567890abcdef'}
    ''')
    return lua

def test_detached_rows_pending_and_uncapped_choices(runtime):
    runtime.execute('''
      local view=assert(H.Open(actor,account,70))
      assert(view.points==51 and #view.rows==2 and view.rows[1].id==0)
      local d=view.rows[1].descriptor
      assert(d.schema==1 and d.nameStrref==1234 and d.effect=='GA_A'and d.alignment=='ALL_GOOD')
      assert(view.CanChoose(0,{0,0}))
      assert(calls.chosen=='1:01:0'and calls.pendingWire=='8:GA_PRIOR'and calls.pending==1)
      local no,why=view.CanChoose(1,{0});assert(not no and why:find('requirements'))
      assert(view.Close()and view.Close()and calls.close==1)
      assert(d.effect=='GA_A'and not view.CanChoose(0,{}))
    ''')

def test_native_lifetime_change_prevents_pointer_query(runtime):
    runtime.execute('''
      local view=assert(H.Open(actor,account,70));actor.incarnation='different'
      local ok,why=view.CanChoose(0,{})
      assert(not ok and why:find('lifetime')and calls.choose==0)
      assert(view.Close()and calls.close==1)
    ''')

def test_zero_interval_and_catalog_failure_cleanup(runtime):
    runtime.execute('''
      zero=true;local view=assert(H.Open(actor,account,70));assert(view.points==0 and #view.rows==0)
      assert(not view.CanChoose(0,{}));view.Close()
      zero=false;badRow=true;local missing,why=H.Open(actor,account,70)
      assert(missing==nil and why:find('row unavailable')and calls.close==2)
    ''')

def test_cleanup_uncertainty_is_not_retried(runtime):
    runtime.execute('''
      local view=assert(H.Open(actor,account,70));closeFailure=true
      local ok,why=view.Close();assert(not ok and why:find('uncertain'))
      view.Close();assert(calls.close==1 and not view.CanChoose(0,{}))
    ''')

def test_explicit_pending_list_is_detached_and_inputs_not_rewritten(runtime):
    runtime.execute('''
      local prior={{descriptor={schema=1,effect='AP_COLON:A'}}}
      local view=assert(H.Open(actor,account,70,prior));prior[1].descriptor.effect='REWRITTEN'
      view.rows[1].descriptor.effect='UI edit does not mutate native catalog'
      assert(view.CanChoose(0,{}));assert(calls.pendingWire=='10:AP_COLON:A'and calls.pending==0)
      assert(not view.CanChoose(99,{}));view.Close()
    ''')

def test_projection_and_delivery_transport(runtime):
    runtime.execute('''
      local view=assert(H.Open(actor,account,70));local d=view.rows[1].descriptor
      d.minLevel=4294967167 -- signed -129; serializer-safe unsigned bits
      local choices={hlas={{id=0,descriptor=d}}}
      local token=H.PrepareManual(actor,account,70,choices)
      assert(calls.manual=='8:GA_PRIOR4:GA_A'and H.ClearManual(token))
      local status,batches,uncertain=H.Deliver(actor,2,account.ownerKey,choices.hlas)
      assert(status==1 and batches==3 and not uncertain and calls.delivery:find('10:4294967167',1,true))
      view.Close()
    ''')

@pytest.mark.parametrize("engine",["lua51","luajit21"])
@pytest.mark.parametrize("mode",["success","mismatch","write_failure","restore_failure"])
def test_exact_scoped_hook_preflight_and_rollback(engine,mode):
    lua=import_module("lupa."+engine).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().hooks=lua.execute((ROOT/"dual_old_hla_hooks.lua").read_text())
    lua.globals().mode=mode
    lua.execute('''
      local memory={[4096+10]=0xaa,[4196]=0xe8,[4296]=0xe8}
      local displacements={[4197]=17,[4297]=27};local writes=0;local protected=true
      function EEex_ReadU8(p)return memory[p]end
      function EEex_Read64()return 4400 end
      function EEex_Read32(p)return displacements[p]end
      function EEex_JITNear(a)assert(a[1]=='jmp 'and a[2]==777);return 4500 end
      function EEex_DisableCodeProtection()protected=false end
      function EEex_EnableCodeProtection()protected=true end
      function EEex_Write32(p,value)
       assert(not protected and value==math.floor(value) and value>=-2147483648 and value<=2147483647,
        'EEex_Write32 takes a signed 32-bit integer');writes=writes+1
       if(mode=='write_failure'or mode=='restore_failure')and writes==2 then error('second write failure')end
       if mode=='restore_failure'and writes==3 then error('restore failure')end
       displacements[p]=value
      end
      local profile={gameTimestamp=1,gameSize=2,functions={{rva=10,bytes='aa'}},listVtable=20,listDestructor=304,
       activeCalls={{rva=100,bytes='e8',contextRva=100,contextBytes='e8'},
                    {rva=200,bytes='e8',contextRva=200,contextBytes='e8'}}}
      if mode=='mismatch'then memory[4296]=0x90 end
      local good,pre=pcall(hooks.Preflight,{profiles={profile}},4096,1,2)
      if mode=='mismatch'then assert(not good and writes==0 and protected);return end
      assert(good and #pre.sites==2 and pre.sites[1].address==4196)
      local ok,result=pcall(hooks.Install,{prepared=pre,predicate=777})
      assert(protected)
      if mode=='success'then
       assert(ok and result.installed and #result.patches==2 and displacements[4197]==299 and displacements[4297]==199)
      elseif mode=='write_failure'then
       assert(not ok and result:find('rolled back')and displacements[4197]==17 and displacements[4297]==27)
      else assert(not ok and result:find('uncertain'))end
    ''')
