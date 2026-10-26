"""Actual fixed startup orchestration, with component outcomes injected offline.
The individual native patch groups are tested separately on private pages.
"""
import ctypes
import shutil
import subprocess
import pytest
from test_scroll_runtime_native import SOURCE, EngineStrings, compiler_environment
from test_scroll_runtime_native import native_api, native_scroll_build  # noqa: F401


STUBS = r'''
#include "startup.h"
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
#include <thread>
extern "C" int CBMS_TestStart(uintptr_t,uintptr_t,const void*,uint32_t,CBMS_PolicyDigest,void*);
int CBMS_InstallEffectPersistenceHooksChained(uintptr_t game,uintptr_t eeex,CBMS_BankActorQuery,void*){return CBMS_InstallEffectPersistenceHooks(game,eeex);}
std::string events; int failure,rollback_failure; bool present[8]{},attached,destroyed,foreign,disabled;int(*admit)();
void CBMS_ForeignEntry(){foreign=true;}
int CBMS_ForeignEntrySeen(){return foreign;}
int CBMS_OverridesDisabled(CBMS_Runtime*){return disabled;}
void CBMS_DisableOverrides(CBMS_Runtime* runtime){if(runtime)disabled=true;}
bool reports(const char* text){return std::string(CBMS_StartupError()).find(text)!=std::string::npos;}
int add(int n){events+=char('0'+n);present[n]=true;return n==failure?0:1;}
int del(int n){events+=char('a'+n-1);if(n==rollback_failure)return 0;present[n]=false;return 1;}
int CBMS_BindModule(uintptr_t,CBMS_NativeFunctions*,char*,uint32_t){events+='B';return failure==8?0:1;}
CBMS_Runtime* CBMS_CreateNative(const CBMS_NativeFunctions*,CBMS_Report,void*){events+='C';return reinterpret_cast<CBMS_Runtime*>(1);}
int CBMS_Destroy(CBMS_Runtime*){events+='D';destroyed=true;return 1;}
void CBMS_ItemAdmission(int(*value)()){admit=value;}
int CBMS_InstallConditionalHooks(uintptr_t,CBMS_Runtime*){return add(2);}
int CBMS_InstallLinked177Hooks(uintptr_t,CBMS_Runtime*){return add(1);}
int CBMS_InstallEffectPersistenceHooks(uintptr_t,uintptr_t){return add(3);}
int CBMS_InstallDispatchHooks(uintptr_t,CBMS_Runtime*){return add(4);}
int CBMS_InstallCastHooks(uintptr_t,CBMS_Runtime*){return add(5);}
int CBMS_InstallItemHooks(uintptr_t,CBMS_Runtime*,const void*,uint32_t,CBMS_PolicyDigest,void*){return add(6);}
int CBMS_EEexAttachRuntime(CBMS_Runtime*){events+='A';attached=failure!=7;return attached;}
int CBMS_EEexBridgeHealthy(){return attached;}
const char* CBMS_EEexBridgeError(){return "";}
#define GROUP(Name,N) extern "C" int CBMS_##Name##HooksPresent(){return present[N];} \
 int CBMS_Remove##Name##Hooks(){return del(N);} \
 const char* CBMS_##Name##HookError(){return "injected component failure";}
GROUP(Linked177,1) GROUP(Conditional,2) GROUP(Decode,3) GROUP(Dispatch,4) GROUP(Cast,5) GROUP(Item,6)
const char* CBMS_ItemCarrierError(){return "";}const char* CBMS_CastCarrierError(){return "";}
const char* CBMS_DispatchCarrierError(){return "";}
const char* CBMS_ConditionalError(){return "";}
const char* CBMS_Linked177Error(){return "";}
int digest(const char*,const char*,unsigned char*,void*){return 1;}
int main(int argc,char** argv){
 if(argc!=3&&argc!=4)return 10;failure=std::atoi(argv[1]);rollback_failure=std::atoi(argv[2]);
 // Before any attempt nothing is kept, and the read latches nothing.
 if(CBMS_StartupRetained()||foreign)return 24;
 const int result=CBMS_TestStart(1,2,"x",1,digest,nullptr);
 if((result==1)!=(failure==0))return 11;
 if(failure==0){if(events!="BC123456A"||!admit||!admit()||destroyed||CBMS_StartupRetained())return 12;}
 else if(failure==8){if(events!="B"||destroyed||CBMS_StartupRetained())return 13;}
 else {
  const int top=failure>6?6:failure;std::string expected="BC";
  for(int i=1;i<=top;++i)expected+=char('0'+i);if(failure==7)expected+='A';
  for(int i=top;i>0;--i){expected+=char('a'+i-1);if(i==rollback_failure)break;}
  if(!rollback_failure)expected+='D';
  if(events!=expected||destroyed==(rollback_failure!=0))return 14;
  if(rollback_failure&&std::string(CBMS_StartupError()).find("retained")==std::string::npos)return 15;
  // Only a rollback that could not remove every hook reports a kept runtime.
  if(CBMS_StartupRetained()!=(rollback_failure!=0))return 25;
  if(rollback_failure){
   // Another thread reads 0 and only latches, as for the health check.
   int seen=-1;std::thread([&]{seen=CBMS_StartupRetained();}).join();
   if(seen||!foreign||!CBMS_StartupRetained())return 26;
  }
 }
 if(argc==4){
  // Neither latch writes a carrier diagnostic; startup still reports it, and
  // a caller on another thread only latches.
  const std::string latch=argv[3];
  if(failure)return 18;
  if(latch=="thread"){
   int healthy=-1,again=-1;const auto before=events;
   std::thread([&]{healthy=CBMS_StartupHealthy();again=CBMS_TestStart(1,2,"x",1,digest,nullptr);}).join();
   if(healthy||again||!foreign||events!=before)return 19;
  }else if(latch=="foreign")foreign=true;
  else if(latch=="disabled")disabled=true;
  else return 20;
  if(CBMS_StartupHealthy()||admit())return 21;
  if(!reports(latch=="disabled"?"disabled after an earlier native fault":"thread other than the engine thread"))return 22;
 }
 const int kept=CBMS_StartupRetained();
 auto before=events;if(CBMS_TestStart(1,2,"x",1,digest,nullptr)||events!=before)return 16;
 if(CBMS_StartupHealthy())return 17;
 // A refused second attempt also disables the overrides of the started runtime,
 // without counting as a kept one.
 if(failure==0&&!disabled)return 23;
 if(CBMS_StartupRetained()!=kept)return 27;
 std::cout<<events;
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


@pytest.mark.parametrize('failure',range(9))
def test_startup_order_and_reverse_partial_rollback(startup_exe,failure):
    result=subprocess.run([str(startup_exe),str(failure),'0'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('retained',range(1,7))
def test_failed_rollback_keeps_earlier_dependencies_and_runtime(startup_exe,retained):
    result=subprocess.run([str(startup_exe),'7',str(retained)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('latch',['disabled','foreign','thread'])
def test_latched_override_faults_report_unhealthy(startup_exe,latch):
    result=subprocess.run([str(startup_exe),'0','0',latch],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


LOG='[CBM scroll] '
VERIFIED=LOG+'Native carrier groups and installed resources verified.'
DUPLICATE=LOG+'Duplicate startup refused; restart this process.'
SINGLE='scroll startup is single-attempt; restart the process after refusal'
RETAINED_CAUSE=('Scroll startup rollback could not safely remove every hook. Exit this process; '
    'do not load or save a game. The native runtime was retained to avoid dangling code.')
# The one box: a failed start that kept its hooks, once per process.
BOX=("chriz-bg-modpack: scrolls at the reader's level could not start cleanly. "
     'Please quit and restart the game before you load or save a game.')


def fallback(cause):
    # A fallback is two loader-log lines. Only a start that kept its hooks adds
    # the box, after them.
    return [LOG+"Scrolls at the reader's level (Modpack 430) are turned off for this session, "
            'so scrolls cast at their normal level. Your saves stay usable.',LOG+'Cause: '+cause]


def lines(table):
    return [table[i] for i in range(1,len(table)+1)]


@pytest.mark.parametrize('backend',['lua51','luajit21'])
@pytest.mark.parametrize('scenario',['success','banking','pending-bank','late','missing','missing-action',
    'missing-retained','refusal','retained','fault','fault-action','status-error','duplicate',
    'duplicate-early','duplicate-refused'])
def test_real_bootstrap_early_only_and_logged_diagnostics(backend,scenario):
    module=__import__('lupa.'+backend,fromlist=['LuaRuntime']);lua=module.LuaRuntime()
    lua.execute('''
      alerts={};shown={};loaded={}; listeners={};printed={};CBMS_TEST_SCENARIO='''+repr(scenario)+'''
      print=function(s)table.insert(printed,s)end
      EEex_MessageBox=function(s)table.insert(alerts,s);boxAfter=#printed end
      Infinity_DisplayString=function(s)table.insert(shown,s)end
      EEex_OpenLuaBindings=function(n)table.insert(loaded,n)end
      EEex_GameState_AddInitializedListener=function(f)table.insert(listeners,f)end
      EEex_Sprite_AddMarshalHandlers=function()end;EEex_Sprite_AddLoadedListener=function()end
      EEex_GetUDAux=function()end;EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled=function()end
      EEex_Resource_Fetch=function()end
      EEex_AIBase_AddScriptingObjectUpdatedListener=function(f)poll=f end
      EEex_Action_AddSpriteStartedActionListener=function(f)started=f end
      -- As the native start: one attempt per process. Each later one is refused
      -- before its arguments are read and turns a started runtime off.
      native={}
      CBMS_NativeStart=function(bytes,fn,offer)
        starts=(starts or 0)+1
        if native.attempted then
          native.error=native.error or 'scroll startup is single-attempt; restart the process after refusal'
          return false,native.error
        end
        native.attempted=true
        assert(bytes=='POLICY');assert(type(fn)=='function');assert(offer==(CBMBank_Identity and CBMBank_Identity.ActorDestroyChain))
        if CBMS_TEST_SCENARIO=='refusal' or CBMS_TEST_SCENARIO=='duplicate-refused' then
          native.error='specific refusal';return false,native.error
        end
        if CBMS_TEST_SCENARIO=='retained' then
          -- The rollback could not remove every hook and kept the runtime.
          native.error=CBMS_TEST_RETAINED;native.retained=true;return false,native.error
        end
        native.ready=true;return true,''
      end
      CBMS_NativeRetained=function()
        retainedReads=(retainedReads or 0)+1
        return native.retained==true
      end
      CBMS_NativeStatus=function()
        checks=(checks or 0)+1
        if CBMS_TEST_SCENARIO=='status-error' then error('status binding broke') end
        if CBMS_TEST_SCENARIO=='fault' or CBMS_TEST_SCENARIO=='fault-action' then
          native.error=native.error or 'latched carrier failure'
        end
        return native.ready==true and not native.error,native.error or ''
      end
      dofile=function(path)table.insert(loaded,path);if path:find('policy_resource') then return {Digest=function()end} end end
      io={open=function()return {read=function()return 'POLICY'end,close=function()end}end}
    ''')
    lua.globals().CBMS_TEST_RETAINED=RETAINED_CAUSE
    if scenario=='late':lua.globals().EEex_GameState_Private_AlreadyInitialized=True
    if scenario=='missing':lua.globals().EEex_Resource_Fetch=None
    if scenario=='missing-action':lua.globals().EEex_Action_AddSpriteStartedActionListener=None
    if scenario=='missing-retained':lua.globals().CBMS_NativeRetained=None
    source=(SOURCE/'CBMS_Startup.lua').read_text();lua.execute(source)
    g=lua.globals()
    early={'late':'Late activation refused. Start a fresh process before loading a game.',
           'missing':'Required EEex API missing: EEex_Resource_Fetch',
           'missing-action':'Required EEex API missing: EEex_Action_AddSpriteStartedActionListener'}
    if scenario in early:
        assert len(g.listeners)==0 and lines(g.printed)==fallback(early[scenario])
        assert len(g.alerts)==0 and len(g.shown)==0
        return
    if scenario=='missing-retained':
        # Without the kept-hooks query the start would not know when to warn, so
        # it never runs. The assertion's message carries its source position.
        printed=lines(g.printed)
        assert len(g.listeners)==0 and len(printed)==2 and printed[0]==fallback('')[0]
        assert printed[1].startswith(LOG+'Cause: ')
        assert printed[1].endswith('Native scroll startup bindings are unavailable')
        assert len(g.alerts)==0 and len(g.shown)==0 and g.retainedReads is None
        return
    assert len(g.listeners)==1
    if scenario=='duplicate-early':
        # A second load before initialization leaves the first load's start alone.
        lua.execute(source)
        assert g.starts is None and len(g.listeners)==1 and lines(g.printed)==[DUPLICATE]
    if scenario=='banking':lua.execute('CBMBank_Identity={ActorDestroyChain=function()end}')
    if scenario=='pending-bank':
        # Banking loads after this registration and starts at initialization; the
        # scroll start must run it first so its authenticated offer exists.
        lua.execute('bankStarts=0;CBMBank_Start=function() bankStarts=bankStarts+1;CBMBank_Identity={ActorDestroyChain=function()end} end')
    g.listeners[1]()
    assert g.starts==1
    if scenario=='pending-bank':assert g.bankStarts==1
    if scenario in ('refusal','retained','duplicate-refused'):
        assert g.poll is None and g.started is None
    else:
        # Both engine events poll the same check once a start succeeded.
        assert g.poll is not None and g.started is not None
    if scenario=='fault':
        g.poll();g.poll();g.started()
    if scenario=='fault-action':
        # A latched fault, then an ordinary action start logs the fallback once; a
        # second action start and a later scripting-object update log nothing
        # and stop asking the runtime.
        lua.execute('started({},{})');assert lines(g.printed)==[VERIFIED]+fallback('latched carrier failure')
        checks=g.checks
        lua.execute('started({},{})');g.poll()
        assert g.checks==checks
    if scenario in ('success','banking','pending-bank'):
        for _ in range(3):lua.execute('started({},{})');g.poll()
        assert g.checks==6
    if scenario=='status-error':
        # A failing check stays inside the listener and is logged once.
        lua.execute('started({},{})');lua.execute('started({},{})');g.poll()
        failures=[line for line in lines(g.printed) if 'Health check failed' in str(line)]
        assert len(failures)==1 and 'status binding broke' in failures[0]
        assert g.checks==1
    if scenario=='duplicate':
        # The second load's refused start turned the started runtime off; the
        # first load's next poll logs that once.
        lua.execute(source)
        assert g.starts==2 and lines(g.printed)==[VERIFIED,DUPLICATE]
        lua.execute('started({},{})');g.poll();lua.execute('started({},{})')
    if scenario=='duplicate-early':
        for _ in range(2):lua.execute('started({},{})');g.poll()
    if scenario=='duplicate-refused':
        # Nothing started, so the second load has nothing to turn off.
        lua.execute(source);assert g.starts==1
    if scenario=='retained':
        # Both log lines come first, then the one box.
        assert lines(g.printed)==fallback(RETAINED_CAUSE) and lines(g.alerts)==[BOX] and g.boxAfter==2
        # A second load stays log-only and starts nothing.
        lua.execute(source);assert g.starts==1 and len(g.alerts)==1
        # Once per process, even if initialization were reported again.
        g.listeners[1]()
    expected={'success':[VERIFIED],'banking':[VERIFIED],'pending-bank':[VERIFIED],
              'refusal':fallback('specific refusal'),
              'retained':fallback(RETAINED_CAUSE)+[DUPLICATE]+fallback(RETAINED_CAUSE),
              'fault':[VERIFIED]+fallback('latched carrier failure'),
              'fault-action':[VERIFIED]+fallback('latched carrier failure'),
              'duplicate':[VERIFIED,DUPLICATE]+fallback(SINGLE),
              'duplicate-early':[DUPLICATE,VERIFIED],
              'duplicate-refused':fallback('specific refusal')+[DUPLICATE]}
    if scenario in expected:assert lines(g.printed)==expected[scenario]
    # Only a refused start asks whether its rollback kept hooks; the flag, not
    # the cause text, decides the box.
    assert g.retainedReads==({'refusal':1,'retained':1,'duplicate-refused':1}.get(scenario))
    # The box only for kept hooks; never an in-game message.
    assert lines(g.alerts)==([BOX] if scenario=='retained' else []) and len(g.shown)==0


BRIDGE = r'''
#include "startup.h"
#include "cast_hook_host.h"
#include "decode_hook_host.h"
#include "dispatch_hook_host.h"
#include "item_hook_host.h"
#include "linked177_api.h"
#include "conditional_api.h"
#include "eeex_save_bridge.h"
// The real startup transaction over the real core runtime, whose entries the
// test passes in from the compiled core library. Only the module binding and
// the patch groups are injected, as in the startup fixture; a test may make one
// group fail to install and one fail to come off again.
struct Core{CBMS_Runtime*(*create)(CBMS_Resolve,CBMS_Report,void*);int(*destroy)(CBMS_Runtime*);
 void(*disable)(CBMS_Runtime*);int(*disabled)(CBMS_Runtime*);void(*foreign)();int(*seen)();CBMS_Resolve resolve;}core;
CBMS_Runtime* created;bool present[7]{},attached;int(*admit)();int install_failure,removal_failure;
extern "C" CBMS_EXPORT void CBMS_TestFailure(int install,int removal){install_failure=install;removal_failure=removal;}
extern "C" int CBMS_TestStart(uintptr_t,uintptr_t,const void*,uint32_t,CBMS_PolicyDigest,void*);
template<class T>void load(T& slot,uintptr_t address){slot=reinterpret_cast<T>(address);}
extern "C" CBMS_EXPORT void CBMS_TestCore(uintptr_t create,uintptr_t destroy,uintptr_t disable,uintptr_t disabled,
 uintptr_t foreign,uintptr_t seen,uintptr_t resolve){
 load(core.create,create);load(core.destroy,destroy);load(core.disable,disable);load(core.disabled,disabled);
 load(core.foreign,foreign);load(core.seen,seen);load(core.resolve,resolve);}
int digest(const char*,const char*,unsigned char*,void*){return 1;}
// The startup binding's call with the policy string and its verifier.
extern "C" CBMS_EXPORT int CBMS_TestStartPolicy(const char* policy,uint32_t size){return CBMS_TestStart(1,2,policy,size,digest,nullptr);}
extern "C" CBMS_EXPORT CBMS_Runtime* CBMS_TestRuntime(){return created;}
extern "C" CBMS_EXPORT int CBMS_TestAdmission(){return admit&&admit()?1:0;}
int CBMS_InstallEffectPersistenceHooksChained(uintptr_t game,uintptr_t eeex,CBMS_BankActorQuery,void*){return CBMS_InstallEffectPersistenceHooks(game,eeex);}
void CBMS_ForeignEntry(){core.foreign();}
int CBMS_ForeignEntrySeen(){return core.seen();}
int CBMS_OverridesDisabled(CBMS_Runtime* runtime){return core.disabled(runtime);}
void CBMS_DisableOverrides(CBMS_Runtime* runtime){core.disable(runtime);}
int CBMS_BindModule(uintptr_t,CBMS_NativeFunctions*,char*,uint32_t){return 1;}
CBMS_Runtime* CBMS_CreateNative(const CBMS_NativeFunctions*,CBMS_Report report,void* user){return created=core.create(core.resolve,report,user);}
int CBMS_Destroy(CBMS_Runtime* runtime){return core.destroy(runtime);}
void CBMS_ItemAdmission(int(*value)()){admit=value;}
int add(int n){present[n]=true;return n==install_failure?0:1;}
int CBMS_InstallLinked177Hooks(uintptr_t,CBMS_Runtime*){return add(1);}
int CBMS_InstallConditionalHooks(uintptr_t,CBMS_Runtime*){return add(2);}
int CBMS_InstallEffectPersistenceHooks(uintptr_t,uintptr_t){return add(3);}
int CBMS_InstallDispatchHooks(uintptr_t,CBMS_Runtime*){return add(4);}
int CBMS_InstallCastHooks(uintptr_t,CBMS_Runtime*){return add(5);}
int CBMS_InstallItemHooks(uintptr_t,CBMS_Runtime*,const void*,uint32_t,CBMS_PolicyDigest,void*){return add(6);}
int CBMS_EEexAttachRuntime(CBMS_Runtime*){attached=true;return 1;}
int CBMS_EEexBridgeHealthy(){return attached;}
const char* CBMS_EEexBridgeError(){return "";}
#define GROUP(Name,N) extern "C" int CBMS_##Name##HooksPresent(){return present[N];} \
 int CBMS_Remove##Name##Hooks(){if(N==removal_failure)return 0;present[N]=false;return 1;} \
 const char* CBMS_##Name##HookError(){return N==install_failure?"injected component failure":"";}
GROUP(Linked177,1) GROUP(Conditional,2) GROUP(Decode,3) GROUP(Dispatch,4) GROUP(Cast,5) GROUP(Item,6)
const char* CBMS_ItemCarrierError(){return "";}const char* CBMS_CastCarrierError(){return "";}
const char* CBMS_DispatchCarrierError(){return "";}
const char* CBMS_ConditionalError(){return "";}
const char* CBMS_Linked177Error(){return "";}
'''


@pytest.fixture(scope='module')
def startup_bridge(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-startup-bridge')
    compiler,env,msvc=compiler_environment();assert msvc
    harness=directory/'startup_bridge.cpp';harness.write_text(BRIDGE)
    library=directory/'startup_bridge.dll'
    result=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/DCBMS_OFFLINE_HARNESS','/LD',
        '/I'+str(SOURCE),str(harness),str(SOURCE/'startup.cpp'),'/Fe'+str(library)],cwd=directory,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return library


# A started runtime keeps its resolver for the rest of the process.
RETAINED=[]


def bridge_session(backend,startup_bridge,native_api,tmp_path,name):
    """A fresh startup module over the real core, and a Lua state whose bindings
    behave as startup_lua.cpp's."""
    api,resolver_type,_=native_api
    # Startup is single-attempt per loaded module, so each session gets its own copy.
    copy=tmp_path/('startup_bridge_'+name+'.dll');shutil.copyfile(startup_bridge,copy)
    bridge=ctypes.CDLL(str(copy))
    bridge.CBMS_TestCore.argtypes=[ctypes.c_size_t]*7
    bridge.CBMS_TestStartPolicy.argtypes=[ctypes.c_char_p,ctypes.c_uint32]
    bridge.CBMS_TestFailure.argtypes=[ctypes.c_int]*2
    bridge.CBMS_StartupError.restype=ctypes.c_char_p
    bridge.CBMS_TestRuntime.restype=ctypes.c_void_p
    queried=[]

    @resolver_type
    def resolve(reader,_generation,_spell,_type,output,_):
        queried.append(reader)
        output.contents.count=1;output.contents.level[0]=16;output.contents.active[0]=1
        output.contents.arcane_state=output.contents.divine_state=0
        return 1
    RETAINED.append(resolve)
    address=lambda function:ctypes.cast(function,ctypes.c_void_p).value
    bridge.CBMS_TestCore(*[address(getattr(api,'CBMS_'+name)) for name in
        ('Create','Destroy','DisableOverrides','OverridesDisabled','ForeignEntry','ForeignEntrySeen')],address(resolve))
    module=__import__('lupa.'+backend,fromlist=['LuaRuntime']);lua=module.LuaRuntime()
    g=lua.globals()
    g.native_start=lambda policy:bridge.CBMS_TestStartPolicy(policy.encode(),len(policy.encode()))
    g.native_healthy=lambda:bridge.CBMS_StartupHealthy()
    g.native_error=lambda:bridge.CBMS_StartupError().decode()
    g.native_retained=lambda:bridge.CBMS_StartupRetained()
    lua.execute('''
      alerts={};shown={};printed={};listeners={}
      print=function(s)table.insert(printed,s)end
      EEex_MessageBox=function(s)table.insert(alerts,s);boxAfter=#printed end
      Infinity_DisplayString=function(s)table.insert(shown,s)end
      EEex_OpenLuaBindings=function()
        -- startup_lua.cpp: only a string with a function reaches the native
        -- start, and a refusal returns the startup diagnostic.
        CBMS_NativeStart=function(bytes,verify)
          local ok=type(bytes)=='string' and type(verify)=='function' and native_start(bytes)==1
          return ok,ok and '' or native_error()
        end
        CBMS_NativeStatus=function() return native_healthy()==1,native_error() end
        CBMS_NativeRetained=function() return native_retained()==1 end
      end
      EEex_GameState_AddInitializedListener=function(f)table.insert(listeners,f)end
      EEex_Sprite_AddMarshalHandlers=function()end;EEex_Sprite_AddLoadedListener=function()end
      EEex_GetUDAux=function()end;EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled=function()end
      EEex_Resource_Fetch=function()end
      EEex_AIBase_AddScriptingObjectUpdatedListener=function(f)poll=f end
      EEex_Action_AddSpriteStartedActionListener=function(f)started=f end
      dofile=function(path)if path:find('policy_resource') then return {Digest=function()end} end end
      io={open=function()return {read=function()return 'POLICY'end,close=function()end}end}
    ''')
    return api,bridge,lua,queried


@pytest.mark.parametrize('backend',['lua51','luajit21'])
def test_duplicate_bootstrap_turns_the_started_runtime_off(backend,startup_bridge,native_api,tmp_path):
    api,bridge,lua,queried=bridge_session(backend,startup_bridge,native_api,tmp_path,backend)
    g=lua.globals()
    source=(SOURCE/'CBMS_Startup.lua').read_text();lua.execute(source)
    g.listeners[1]()
    runtime=bridge.CBMS_TestRuntime()
    assert runtime and api.CBMS_OverridesDisabled(runtime)==0 and bridge.CBMS_TestAdmission()==1
    assert tuple(lua.eval('CBMS_NativeStatus()'))==(True,'') and bridge.CBMS_StartupRetained()==0
    strings=EngineStrings();fields=[ctypes.c_size_t(strings.empty) for _ in range(2)]
    for kind,pointer in [(0,0x1000),(1,0x2000)]:
        assert api.CBMS_Construct(runtime,kind,pointer)==1
    use=ctypes.c_uint64()
    assert api.CBMS_ItemBegin(runtime,0x1000,b'SCROLL',0,0,ctypes.byref(use))==1
    assert api.CBMS_ItemChild(runtime,use,0x2000,0)==1
    assert api.CBMS_ItemEnd(runtime,use)==1
    carriers=[]
    for field in fields:
        # The owned 146 mode0 queues two casts, each carrying its witness.
        assert api.CBMS_StampActionWitness(runtime,0x2000,146,0,0,ctypes.addressof(field),strings.empty)==1
        carrier=ctypes.c_size_t()
        assert api.CBMS_ActionWitnessCarrier(runtime,field.value,ctypes.byref(carrier))==1
        carriers.append(carrier.value)

    def cast(carrier):
        frame,level=ctypes.c_uint64(),ctypes.c_uint32(99)
        assert api.CBMS_BeginCast(runtime,3,carrier,3,0xD000,b'SPELL',0,1,2,3,4,ctypes.byref(frame))==1
        selected=api.CBMS_Select(runtime,frame,3,0xD000,ctypes.byref(level))
        assert api.CBMS_EndCast(runtime,frame)==1
        return selected,level.value
    # Healthy: the first queued cast takes half its reader's active level.
    assert cast(carriers[0])==(1,8) and queried==[0x1000]
    lua.execute('started({},{})');g.poll()
    assert lines(g.printed)==[VERIFIED]
    lua.execute(source)
    assert api.CBMS_OverridesDisabled(runtime)==1 and bridge.CBMS_TestAdmission()==0
    assert tuple(lua.eval('CBMS_NativeStatus()'))==(False,SINGLE)
    lua.execute('started({},{})');g.poll();lua.execute('started({},{})')
    assert lines(g.printed)==[VERIFIED,DUPLICATE]+fallback(SINGLE)
    # Turning a started runtime off is no failed rollback, so it stays log-only.
    assert bridge.CBMS_StartupRetained()==0 and len(g.alerts)==0 and len(g.shown)==0
    # The other queued cast keeps its native level, even through the carrier it
    # resolved before the second load, and its reader is not asked again.
    assert api.CBMS_ActionWitnessCarrier(runtime,fields[1].value,ctypes.byref(ctypes.c_size_t()))==0
    assert cast(carriers[1])==(0,99) and queried==[0x1000]
    # Cleanup keeps working while overrides are off.
    for field in fields:strings.release(ctypes.addressof(field))
    assert api.CBMS_SweepActionWitnesses(runtime)==0
    assert not set(carriers)&set(strings.freed)
    assert api.CBMS_Destruct(runtime,1,0x2000)==1 and api.CBMS_Quiescent(runtime)==1


@pytest.mark.parametrize('backend',['lua51','luajit21'])
@pytest.mark.parametrize('removal',[0,2])
def test_only_a_start_that_kept_its_hooks_shows_the_box(backend,removal,startup_bridge,native_api,tmp_path):
    # The dispatch group fails to install. Its rollback either removes every
    # group again (0), or the conditional group refuses to come off (2) and the
    # real startup keeps the runtime and the groups it did not remove.
    _,bridge,lua,queried=bridge_session(backend,startup_bridge,native_api,tmp_path,
        'failed_'+backend+'_'+str(removal))
    bridge.CBMS_TestFailure(4,removal)
    g=lua.globals()
    source=(SOURCE/'CBMS_Startup.lua').read_text();lua.execute(source)
    g.listeners[1]()
    kept=removal!=0
    cause=RETAINED_CAUSE if kept else 'injected component failure'
    assert bridge.CBMS_StartupRetained()==int(kept) and bridge.CBMS_StartupHealthy()==0
    assert g.poll is None and g.started is None
    # The log keeps both lines either way; the box follows them only for kept hooks.
    assert lines(g.printed)==fallback(cause)
    assert lines(g.alerts)==([BOX] if kept else []) and g.boxAfter==(2 if kept else None)
    # A second load stays log-only and starts nothing.
    lua.execute(source)
    assert lines(g.printed)==fallback(cause)+[DUPLICATE]
    assert lines(g.alerts)==([BOX] if kept else []) and len(g.shown)==0
    assert bridge.CBMS_StartupRetained()==int(kept) and queried==[]
