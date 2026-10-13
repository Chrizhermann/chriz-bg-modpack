"""Actual fixed startup orchestration, with component outcomes injected offline.
The individual native patch groups are tested separately on private pages.
"""
import subprocess
import pytest
from test_scroll_runtime_native import SOURCE, compiler_environment


STUBS = r'''
#include "startup.h"
#include "action_hook_host.h"
#include "cast_hook_host.h"
#include "decode_hook_host.h"
#include "dispatch_hook_host.h"
#include "item_hook_host.h"
#include "linked177_api.h"
#include "conditional_api.h"
#include "eeex_save_bridge.h"
#include <string>
#include <iostream>
#include <cstdlib>
extern "C" int CBMS_TestStart(uintptr_t,uintptr_t,const void*,uint32_t,CBMS_PolicyDigest,void*);
int CBMS_InstallEffectPersistenceHooksChained(uintptr_t game,uintptr_t eeex,CBMS_BankActorQuery,void*){return CBMS_InstallEffectPersistenceHooks(game,eeex);}
std::string events; int failure,rollback_failure; bool present[8]{},attached,destroyed;int(*admit)();
int add(int n){events+=char('0'+n);present[n]=true;return n==failure?0:1;}
int del(int n){events+=char('a'+n-1);if(n==rollback_failure)return 0;present[n]=false;return 1;}
int CBMS_BindModule(uintptr_t,CBMS_NativeFunctions*,char*,uint32_t){events+='B';return failure==9?0:1;}
CBMS_Runtime* CBMS_CreateNative(const CBMS_NativeFunctions*,CBMS_Report,void*){events+='C';return reinterpret_cast<CBMS_Runtime*>(1);}
int CBMS_Destroy(CBMS_Runtime*){events+='D';destroyed=true;return 1;}
void CBMS_ItemAdmission(int(*value)()){admit=value;}
int CBMS_InstallConditionalHooks(uintptr_t,CBMS_Runtime*){return add(2);}
int CBMS_InstallLinked177Hooks(uintptr_t,CBMS_Runtime*){return add(1);}
int CBMS_InstallEffectPersistenceHooks(uintptr_t,uintptr_t){return add(3);}
int CBMS_InstallActionHooks(uintptr_t,CBMS_Runtime*){return add(4);}
int CBMS_InstallDispatchHooks(uintptr_t,CBMS_Runtime*){return add(5);}
int CBMS_InstallCastHooks(uintptr_t,CBMS_Runtime*){return add(6);}
int CBMS_InstallItemHooks(uintptr_t,CBMS_Runtime*,const void*,uint32_t,CBMS_PolicyDigest,void*){return add(7);}
int CBMS_EEexAttachRuntime(CBMS_Runtime*){events+='A';attached=failure!=8;return attached;}
int CBMS_EEexBridgeHealthy(){return attached;}
const char* CBMS_EEexBridgeError(){return "";}
#define GROUP(Name,N) extern "C" int CBMS_##Name##HooksPresent(){return present[N];} \
 int CBMS_Remove##Name##Hooks(){return del(N);} \
 const char* CBMS_##Name##HookError(){return "injected component failure";}
GROUP(Linked177,1) GROUP(Conditional,2) GROUP(Decode,3) GROUP(Action,4) GROUP(Dispatch,5) GROUP(Cast,6) GROUP(Item,7)
const char* CBMS_ItemCarrierError(){return "";}const char* CBMS_CastCarrierError(){return "";}
const char* CBMS_DispatchCarrierError(){return "";}const char* CBMS_ActionCarrierError(){return "";}
const char* CBMS_ConditionalError(){return "";}
const char* CBMS_Linked177Error(){return "";}
int digest(const char*,const char*,unsigned char*,void*){return 1;}
int main(int argc,char** argv){
 if(argc!=3)return 10;failure=std::atoi(argv[1]);rollback_failure=std::atoi(argv[2]);
 const int result=CBMS_TestStart(1,2,"x",1,digest,nullptr);
 if((result==1)!=(failure==0))return 11;
 if(failure==0){if(events!="BC1234567A"||!admit||!admit()||destroyed)return 12;}
 else if(failure==9){if(events!="B"||destroyed)return 13;}
 else {
  const int top=failure>7?7:failure;std::string expected="BC";
  for(int i=1;i<=top;++i)expected+=char('0'+i);if(failure==8)expected+='A';
  for(int i=top;i>0;--i){expected+=char('a'+i-1);if(i==rollback_failure)break;}
  if(!rollback_failure)expected+='D';
  if(events!=expected||destroyed==(rollback_failure!=0))return 14;
  if(rollback_failure&&std::string(CBMS_StartupError()).find("retained")==std::string::npos)return 15;
 }
 auto before=events;if(CBMS_TestStart(1,2,"x",1,digest,nullptr)||events!=before)return 16;
 if(CBMS_StartupHealthy())return 17;std::cout<<events;
}
'''


@pytest.fixture(scope='module')
def startup_exe(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-startup')
    compiler,env,msvc=compiler_environment();assert msvc
    harness=directory/'startup_fixture.cpp';harness.write_text(STUBS)
    exe=directory/'startup.exe'
    result=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/DCBMS_OFFLINE_HARNESS',
        '/I'+str(SOURCE),str(harness),str(SOURCE/'startup.cpp'),'/Fe'+str(exe)],cwd=directory,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return exe


@pytest.mark.parametrize('failure',range(10))
def test_startup_order_and_reverse_partial_rollback(startup_exe,failure):
    result=subprocess.run([str(startup_exe),str(failure),'0'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('retained',range(1,8))
def test_failed_rollback_keeps_earlier_dependencies_and_runtime(startup_exe,retained):
    result=subprocess.run([str(startup_exe),'8',str(retained)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('backend',['lua51','luajit21'])
@pytest.mark.parametrize('scenario',['success','banking','pending-bank','late','missing','refusal','fault','duplicate'])
def test_real_bootstrap_early_only_and_visible_diagnostics(backend,scenario):
    module=__import__('lupa.'+backend,fromlist=['LuaRuntime']);lua=module.LuaRuntime()
    lua.execute('''
      alerts={};loaded={}; listeners={};CBMS_TEST_SCENARIO='''+repr(scenario)+'''
      print=function()end
      EEex_MessageBox=function(s)table.insert(alerts,s)end
      EEex_OpenLuaBindings=function(n)table.insert(loaded,n)end
      EEex_GameState_AddInitializedListener=function(f)table.insert(listeners,f)end
      EEex_Sprite_AddMarshalHandlers=function()end;EEex_Sprite_AddLoadedListener=function()end
      EEex_GetUDAux=function()end;EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled=function()end
      EEex_Resource_Fetch=function()end
      EEex_AIBase_AddScriptingObjectUpdatedListener=function(f)poll=f end
      CBMS_NativeStart=function(bytes,fn,offer) starts=(starts or 0)+1;assert(bytes=='POLICY');assert(type(fn)=='function');assert(offer==(CBMBank_Identity and CBMBank_Identity.ActorDestroyChain));return CBMS_TEST_SCENARIO~='refusal','specific refusal' end
      CBMS_NativeStatus=function()return CBMS_TEST_SCENARIO~='fault','latched carrier failure' end
      dofile=function(path)table.insert(loaded,path);if path:find('policy_resource') then return {Digest=function()end} end end
      io={open=function()return {read=function()return 'POLICY'end,close=function()end}end}
    ''')
    if scenario=='late':lua.globals().EEex_GameState_Private_AlreadyInitialized=True
    if scenario=='missing':lua.globals().EEex_Resource_Fetch=None
    source=(SOURCE/'CBMS_Startup.lua').read_text();lua.execute(source)
    if scenario in ('late','missing'):
        assert len(lua.globals().alerts)==1 and len(lua.globals().listeners)==0
        return
    assert len(lua.globals().listeners)==1
    if scenario=='banking':lua.execute('CBMBank_Identity={ActorDestroyChain=function()end}')
    if scenario=='pending-bank':
        # Banking loads after this registration and starts at initialization; the
        # scroll start must run it first so its authenticated offer exists.
        lua.execute('bankStarts=0;CBMBank_Start=function() bankStarts=bankStarts+1;CBMBank_Identity={ActorDestroyChain=function()end} end')
    lua.globals().listeners[1]()
    if scenario=='duplicate':lua.execute(source)
    if scenario=='fault':lua.globals().poll();lua.globals().poll()
    assert lua.globals().starts==1
    if scenario=='pending-bank':assert lua.globals().bankStarts==1
    assert len(lua.globals().alerts)==(scenario not in ('success','banking','pending-bank'))
