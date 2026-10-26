// Actual pinned SetAtOffset windows, original unwind recipe, synthetic actors.
// DLL branch callback completes before native ProcessEffectList stub is called.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "writer_native.h"
#include "writer_native_windows.inc"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
// One armed allocation fails. The bridge's first allocation is its record insert.
static bool fail_allocation=false;
void* operator new(std::size_t n){
    if(fail_allocation){fail_allocation=false;throw std::bad_alloc();}
    if(void* p=std::malloc(n?n:1))return p;
    throw std::bad_alloc();
}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
namespace{
alignas(16) unsigned char actor[0x6000]{};
using Setter=uint16_t(*)(void*,uint32_t,uint32_t,uint32_t);
Setter current;
bool strip=false,preview=false,journal=false,throw_before=false,throw_complete=false,fail_complete=false,recalc_nested=false,in_recalc=false;
bool retained=false,skip_plan=false; // An uncertain journal kept; a tracked disposition that planned nothing.
int checks=0,prepares=0,completes=0,recalcs=0,uncertains=0,disposition=1;
uint32_t plan_target=0,expected_origin=0,drift=0; // drift: what the before callback itself adds to base XP.
std::function<void()> nested,during_marshal,after_plan; // A setter call inside the callback; work inside a save; after its plan.
void check_impl(bool x,int line){++checks;if(!x)throw std::runtime_error("writer assertion line "+std::to_string(line));}
#define check(x) check_impl((x),__LINE__)
// Lua host doubles for the identity's exported Lua functions.
std::string lua_args[2];std::vector<std::string> lua_pushed;
const char* lua_read(void*,int index,size_t* length){const auto& s=lua_args[index-1];*length=s.size();return s.c_str();}
const char* lua_push(void*,const char* s){lua_pushed.emplace_back(s);return s;}
void lua_bool(void*,int b){lua_pushed.emplace_back(b?"true":"false");}
std::string hex(const void* p){char b[32];std::snprintf(b,sizeof(b),"%llx",static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(p)));return b;}
uint32_t read(size_t at){uint32_t n;std::memcpy(&n,actor+at,4);return n;}
void put(void* p,size_t at,uint32_t n){std::memcpy(static_cast<unsigned char*>(p)+at,&n,4);}
void lifecycle(void*){}
uintptr_t marshal(void*,void*,void*,void*,unsigned char){if(during_marshal)during_marshal();return 0;}
CBMW_View view(){CBMW_View v{};check(CBMW_Query(actor,&v));return v;}
int before(void* a){
    check(a==actor);++prepares;auto v=view();
    check(v.stage==CBMW_PREPARING&&!v.planned&&v.pre_base==read(0x570)&&v.origin==expected_origin);
    if(nested)nested();
    if(disposition!=1){put(actor,0x570,read(0x570)+drift);return disposition;}
    if(skip_plan)return 1;
    journal=true;if(throw_before)throw std::runtime_error("before native store");
    check(CBMW_Plan(actor,plan_target)&&!CBMW_Plan(actor,plan_target+1));
    if(after_plan)after_plan();
    put(actor,0x570,read(0x570)+drift);return 1;
}
int complete(void* a){
    check(a==actor&&journal);++completes;auto v=view();
    check(v.stage==CBMW_COMPLETING&&v.planned&&v.post_base==plan_target&&read(0x570)==plan_target);
    check(!CBMW_Plan(actor,0));
    if(throw_complete)throw std::runtime_error("after native store");
    if(fail_complete)return 0;journal=false;return 1;
}
bool refuse_withdrawal=false;int withdrawals=0;
// As R.UncertainWrite: withdraw an exactly prepared journal no store followed,
// else mark it. Without an identity it finds no boundary (a Lua error, 0).
int uncertain(void* a){
    check(a==actor&&journal);++uncertains;CBMW_View v{};if(!CBMW_Query(actor,&v))return 0;
    if(v.stage==CBMW_WITHDRAWING){
        check(v.post_base==v.pre_base&&v.planned);
        if(refuse_withdrawal)return 0;
        journal=false;++withdrawals;return 1;
    }
    check(v.stage==CBMW_UNCERTAIN);retained=true;return 1;
}
void recalc(void* a,uint32_t force){
    check(a==actor&&force==1&&read(0x4ba4)==1);++recalcs;
    check(!journal||retained); // The recalc runs after the write's window closed.
    if(recalc_nested&&!in_recalc){
        in_recalc=true;expected_origin=0;plan_target=read(0x570)+1;
        check(current(actor,44,1,1)==0xffff);in_recalc=false;
    }
}
uint16_t setter(void* a,uint32_t stat,uint32_t value,uint32_t mode){return current(a,stat,value,mode);}
void fresh(){CBMI_Destruct(actor);CBMI_Construct(actor);journal=false;retained=false;}
// Whether this lifetime holds a replaced-word note; takes it as the runtime does.
bool take_note(){
    lua_args[0]=hex(actor);lua_pushed.clear();
    if(CBMI_LuaQuery(nullptr)!=8)return false; // No identity, no lifetime to note.
    if(lua_pushed[7]!="true")return false;
    CBMI_View v{};check(CBMI_Query(actor,&v));lua_args[1]=std::to_string(v.incarnation);lua_pushed.clear();
    check(CBMI_LuaAckReplaced(nullptr)==1&&lua_pushed[0]=="true");return true;
}
// A refused setter write is never dropped: the game's own store (mode 1 adds,
// any other sets) on the base it saw, counted with its status.
void expect_own(const std::function<void()>& call,uint32_t seen,uint32_t value,uint32_t mode,int why,int callbacks){
    const auto f=CBMW_Fallbacks(nullptr);const int p=prepares;
    call();int last=0;CBMW_Fallbacks(&last);
    check(read(0x570)==(mode==1?seen+value:value)&&CBMW_Fallbacks(nullptr)==f+1&&last==why);
    check(CBMW_LastStatus()==why&&prepares==p+callbacks);
}
// Each setter refusal path (statuses 2, 3, 4, 5, 7, 8, 9, 10) in both windows.
// Each SET there replaced the word and notes it; an ADD of 1000 stays within it.
void setter_outcomes(){
    struct Case{uint32_t value,mode;};
    for(const auto c:{Case{54321,0},Case{1000,1},Case{77,7}}){
        const auto set=[c]{check(current(actor,44,c.value,c.mode)==0xffff);};
        const bool sets=c.mode!=1;
        expected_origin=0;plan_target=123456;
        // 2: another thread. Records stay host-only; the store is the game's own there.
        fresh();put(actor,0x570,600000);
        expect_own([c]{uint16_t r=0;std::thread t([&]{r=current(actor,44,c.value,c.mode);});t.join();check(r==0xffff);},
            600000,c.value,c.mode,2,0);
        check(!take_note()); // The registry is the host thread's: nothing is noted there.
        // 3: an actor the lifetime hooks never saw.
        CBMI_Destruct(actor);put(actor,0x570,600000);expect_own(set,600000,c.value,c.mode,3,0);CBMI_Construct(actor);
        check(!take_note());
        // 9: while the game saves (any actor's marshal scope).
        put(actor,0x570,600000);int scopes=0;
        during_marshal=[&]{++scopes;expect_own(set,600000,c.value,c.mode,9,0);};
        CBMI_Marshal(actor,nullptr,nullptr,nullptr,0);during_marshal=nullptr;check(scopes==1&&take_note()==sets);
        // 5: refused (any Lua error included), an insert that fails, or nothing planned.
        put(actor,0x570,600000);disposition=0;expect_own(set,600000,c.value,c.mode,5,1);disposition=1;
        check(take_note()==sets);
        put(actor,0x570,600000);expect_own([&]{fail_allocation=true;set();},600000,c.value,c.mode,5,0);
        check(!fail_allocation&&!journal&&take_note()==sets);
        put(actor,0x570,600000);skip_plan=true;expect_own(set,600000,c.value,c.mode,5,1);skip_plan=false;
        check(take_note()==sets);
        // 8: changed during an unjournaled callback. No record stays behind it.
        const int quiet=uncertains;put(actor,0x570,600000);disposition=0;drift=7;
        expect_own(set,600007,c.value,c.mode,8,1);disposition=1;drift=0;
        CBMW_View absent{};check(!CBMW_Query(actor,&absent)&&uncertains==quiet&&take_note()==sets);
        put(actor,0x570,600000);check(current(actor,44,123456,0)==0xffff&&read(0x570)==123456&&CBMW_LastStatus()==6);
        check(!take_note()); // A banked write is the bank's own: nothing to take.
        // 8: changed during a journaled callback: no store followed, so its journal is withdrawn.
        fresh();put(actor,0x570,600000);drift=7;const int w=withdrawals;
        expect_own(set,600007,c.value,c.mode,8,1);drift=0;
        check(!journal&&!retained&&withdrawals==w+1&&!CBMW_Query(actor,&absent)&&take_note()==sets);
        // 7: a journal that cannot be withdrawn keeps the plan; the store is still the game's own.
        put(actor,0x570,600000);drift=7;refuse_withdrawal=true;const int u=uncertains;
        expect_own(set,600007,c.value,c.mode,7,1);drift=0;refuse_withdrawal=false;
        check(journal&&retained&&uncertains==u+2&&view().stage==CBMW_UNCERTAIN&&take_note()==sets);
        // 4: behind that uncertain journal, without a callback.
        put(actor,0x570,600000);expect_own(set,600000,c.value,c.mode,4,0);check(view().stage==CBMW_UNCERTAIN);
        check(take_note()==sets);
        // 10: a setter call while a change of this actor is in flight lands as that change closes.
        fresh();put(actor,0x570,600000);const auto f=CBMW_Fallbacks(nullptr);
        nested=[&]{set();check(read(0x570)==600000&&CBMW_LastStatus()==10&&CBMW_Fallbacks(nullptr)==f);};
        check(current(actor,44,123456,0)==0xffff&&CBMW_LastStatus()==6&&!journal);nested=nullptr;
        int last=0;CBMW_Fallbacks(&last);
        check(read(0x570)==(c.mode==1?123456+c.value:c.value)&&CBMW_Fallbacks(nullptr)==f+1&&last==10);
        check(take_note()==sets);
        // An owned SET the bank refuses is the game's own SET; its status reaches the caller.
        fresh();put(actor,0x570,600000);disposition=0;expected_origin=1;uint16_t result=0;
        check(CBMW_ApplyOwnedSet(actor,765432,1,&result)&&result==0xffff&&CBMW_LastStatus()==5&&read(0x570)==765432);
        check(take_note());disposition=1;expected_origin=0;
    }
}
// The preparation ends the actor's lifetime (11): ended, or ended and a new one
// started at that address. Nothing is stored into another lifetime, no callback
// addresses the ended one, and it is no fallback: the game's own store did not
// run. The game's caller still continues with that pointer (its recalc runs).
void setter_lifetime(){
    for(bool recreated:{true,false})for(bool refused:{false,true}){
        fresh();put(actor,0x570,600000);plan_target=123456;expected_origin=0;disposition=refused?0:1;
        const auto f=CBMW_Fallbacks(nullptr);const auto ended=CBMW_Ended();const int u=uncertains,r=recalcs;
        const auto end_lifetime=[recreated]{CBMI_Destruct(actor);if(recreated)CBMI_Construct(actor);journal=false;};
        if(refused)nested=end_lifetime;else after_plan=end_lifetime; // A planned journal goes with the ended actor.
        check(current(actor,44,54321,0)==0xffff);nested=after_plan=nullptr;
        check(read(0x570)==600000&&CBMW_LastStatus()==11&&CBMW_Ended()==ended+1&&CBMW_Fallbacks(nullptr)==f);
        check(uncertains==u&&recalcs==r+1);
        if(!recreated)CBMI_Construct(actor);
        CBMW_View absent{};check(!CBMW_Query(actor,&absent)&&!take_note());disposition=1;
    }
    // A setter write deferred behind a change whose preparation ends the
    // lifetime has nothing to land in: dropped as that change closes, counted.
    for(bool recreated:{true,false}){
        fresh();put(actor,0x570,600000);plan_target=123456;const auto ended=CBMW_Ended();const auto f=CBMW_Fallbacks(nullptr);
        nested=[]{check(current(actor,44,1000,1)==0xffff&&CBMW_LastStatus()==10);};
        after_plan=[recreated]{CBMI_Destruct(actor);if(recreated)CBMI_Construct(actor);journal=false;};
        check(current(actor,44,123456,0)==0xffff);nested=after_plan=nullptr;
        check(read(0x570)==600000&&CBMW_Ended()==ended+2&&CBMW_Fallbacks(nullptr)==f&&!take_note());
        if(!recreated)CBMI_Construct(actor);
    }
}
void relative(unsigned char* mem,size_t at,size_t end,size_t target);
void absolute_thunk(unsigned char* mem,size_t at,const void* target);
// The game's own stat44 store, run from the same pinned window unpatched: mode
// 1 adds and wraps past either end of the word, any other mode sets. A refused
// setter write stores exactly that, and notes it where the word was replaced.
void compare_store(const unsigned char* body,size_t size){
    auto* mem=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x4000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));check(mem!=nullptr);
    std::memcpy(mem,body,size);put(mem,0x2000,0xfffeffff);relative(mem,0x65d,0x661,0x2000);relative(mem,0x669,0x66d,0x2002);
    absolute_thunk(mem,0x2100,reinterpret_cast<const void*>(recalc));relative(mem,0x656,0x65a,0x2100);
    check(mem[0x577]==0x41&&mem[0x57d]==0x44&&mem[0x57e]==0x01); // cmp r9d,1 ... add dword ptr [rcx+0x570], r8d
    DWORD old;check(VirtualProtect(mem,0x4000,PAGE_EXECUTE_READ,&old)!=0);
    check(FlushInstructionCache(GetCurrentProcess(),mem,0x4000)!=0);
    const auto game=reinterpret_cast<Setter>(mem);
    struct Case{uint32_t base,value,mode,stored;bool replaced;};
    for(const auto c:{Case{4294967200u,200000,1,199904,true},Case{600000,1000,1,601000,false}, // ADD past the top, within.
                      Case{4294967295u,4294966296u,1,4294966295u,false},Case{100,4294966296u,1,4294966396u,true}, // Loss 1000.
                      Case{4294967295u,100000,0,100000,true},Case{600000,77,7,77,true}}){ // SET; an unknown mode sets.
        fresh();put(actor,0x570,c.base);const int r=recalcs;
        check(game(actor,44,c.value,c.mode)==0xffff&&read(0x570)==c.stored&&recalcs==r+1&&!take_note());
        put(actor,0x570,c.base);disposition=0;
        check(current(actor,44,c.value,c.mode)==0xffff&&read(0x570)==c.stored&&CBMW_LastStatus()==5);
        check(take_note()==c.replaced);disposition=1;
    }
    check(VirtualFree(mem,0,MEM_RELEASE)!=0);
}
void relative(unsigned char* mem,size_t at,size_t end,size_t target){put(mem,at,static_cast<uint32_t>(target-end));}
void absolute_thunk(unsigned char* mem,size_t at,const void* target){
    mem[at]=0x48;mem[at+1]=0xB8;std::memcpy(mem+at+2,&target,8);mem[at+10]=0xFF;mem[at+11]=0xE0;
}
void exercise(const unsigned char* body,size_t size,const unsigned char* unwind,DWORD end){
    auto* mem=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x4000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));check(mem!=nullptr);
    std::memcpy(mem,body,size);std::memcpy(mem+0x1000,unwind,8);
    put(mem,0x2000,0xfffeffff); // Original success -1 / unsupported-stat -2.
    relative(mem,0x65d,0x661,0x2000);relative(mem,0x669,0x66d,0x2002);
    absolute_thunk(mem,0x2100,reinterpret_cast<const void*>(recalc));relative(mem,0x656,0x65a,0x2100);
    absolute_thunk(mem,0x2120,reinterpret_cast<const void*>(CBMW_Write));
    mem[0x577]=0xE8;relative(mem,0x578,0x57c,0x2120);
    mem[0x57c]=0x48;mem[0x57d]=0x8B;mem[0x57e]=0xC8;mem[0x57f]=0xE9;
    relative(mem,0x580,0x584,0x646);std::memset(mem+0x584,0x90,0x595-0x584);
    DWORD old;check(VirtualProtect(mem,0x4000,PAGE_EXECUTE_READ,&old)!=0);
    check(FlushInstructionCache(GetCurrentProcess(),mem,0x4000)!=0);
    RUNTIME_FUNCTION function{0,end,0x1000};
    check(RtlAddFunctionTable(&function,1,reinterpret_cast<DWORD64>(mem))!=0);
    current=reinterpret_cast<Setter>(mem);
    for(auto mode:{0u,1u,7u})for(auto raw:{0u,250000u,0xffffffe5u}){
        fresh();put(actor,0x570,600000);plan_target=123456;expected_origin=0;
        int old_recalcs=recalcs;
        check(current(actor,44,raw,mode)==0xffff&&!journal&&read(0x570)==123456);
        check(recalcs==old_recalcs+1);CBMW_View absent{};check(!CBMW_Query(actor,&absent));
    }
    // Other stats and unsupported indexes never call the writer callback.
    int old_prepares=prepares;put(actor,0x570,987654);
    check(current(actor,1,15,0)==0xffff);check(read(0x57e)%65536==15&&read(0x570)==987654&&prepares==old_prepares);
    check(current(actor,999,0,0)==0xfffe&&prepares==old_prepares);
    // Unowned native SET/ADD retains exact modulo32 semantics, uncounted. It is
    // the game's own store as it executes: where it replaces the word, noted.
    disposition=2;put(actor,0x570,0xfffffff0);const auto unowned=CBMW_Fallbacks(nullptr);
    check(current(actor,44,32,1)==0xffff&&read(0x570)==16&&take_note());
    check(current(actor,44,4321,4)==0xffff&&read(0x570)==4321&&take_note());
    check(current(actor,44,1000,1)==0xffff&&read(0x570)==5321&&!take_note()&&CBMW_Fallbacks(nullptr)==unowned);
    disposition=1;
    // Scoped source applies to the first exact SET only. Nested recalc writes
    // are unclassified, and happen after the first committed callback.
    for(uint32_t origin:{1u,2u}){
        fresh();expected_origin=origin;plan_target=765432;recalc_nested=true;uint16_t result=0;
        check(CBMW_ApplyOwnedSet(actor,765432,origin,&result)&&result==0xffff);
        check(read(0x570)==765433&&CBMW_LastStatus()==6);recalc_nested=false;
    }
    // Throw through the patched game frame with its actual Windows unwind data.
    fresh();put(actor,0x570,600000);expected_origin=0;plan_target=100000;throw_before=true;
    int before_recalc=recalcs;
    try{current(actor,44,100000,0);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="before native store");}
    check(read(0x570)==600000&&recalcs==before_recalc);throw_before=false;fresh();
    throw_complete=true;
    try{current(actor,44,100000,0);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="after native store");}
    check(read(0x570)==100000&&journal&&view().stage==CBMW_UNCERTAIN&&recalcs==before_recalc);throw_complete=false;fresh();
    fail_complete=true;plan_target=12345;
    check(current(actor,44,12345,0)==0xffff&&journal&&view().stage==CBMW_UNCERTAIN);
    check(read(0x570)==12345);
    // Behind that retained uncertain journal a setter write is the game's own.
    const auto fallbacks_before=CBMW_Fallbacks(nullptr);
    check(current(actor,44,54321,0)==0xffff&&read(0x570)==54321&&CBMW_LastStatus()==4);
    check(CBMW_Fallbacks(nullptr)==fallbacks_before+1&&view().stage==CBMW_UNCERTAIN);
    fail_complete=false;setter_outcomes();setter_lifetime();compare_store(body,size);fresh();
    // Proven scope unwinds after exception; the next ordinary call is unclassified.
    throw_before=true;expected_origin=1;uint16_t ignored=0;
    try{CBMW_ApplyOwnedSet(actor,20000,1,&ignored);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="before native store");}
    throw_before=false;fresh();expected_origin=0;plan_target=44;
    check(current(actor,44,44,0)==0xffff&&read(0x570)==44);
    check(!CBMW_ApplyOwnedSet(actor,5,9,&ignored));
    check(RtlDeleteFunctionTable(&function)!=0);check(VirtualFree(mem,0,MEM_RELEASE)!=0);
}
// Another thread's lifetime event (no resolved path in 2.7.3.0, see
// main-thread-audit-2.7.3.txt) leaves every identity unknown for the rest of the
// process, so each case runs in a process of its own (writer_check.ps1). Inside
// a preparation it proves no lifetime ended (not 11). Cases 0 and 1, Codex's
// round-3 case: an outer SET with a SET queued behind it, an unrelated actor
// constructed on another thread meanwhile. Both are the game's own stores, in
// order: the outer one as a change no journal could be withdrawn from (7, its
// record kept) or as one without a journal (8), the queued one as it closes
// (10). Cases 2 and 3, Codex's round-4 case: the same, but another thread
// destroys the actor and constructs another (B, 10 XP) at its address. Neither
// write lands in what may be B: both are kept, never written (12, CBMW_Kept),
// and neither counts as a fallback. Keeping the outer one allocates nothing (its
// slot was promised before its preparation), and both stay kept once this
// thread proves the old lifetime over and settles that address again.
alignas(16) unsigned char unrelated[0x6000]{};
void foreign_event(){std::thread t([]{CBMI_Construct(unrelated);});t.join();}
void foreign_replacement(){std::thread t([]{CBMI_Destruct(actor);CBMI_Construct(actor);put(actor,0x570,10);});t.join();}
std::string kept(uint64_t* count){char text[256];*count=CBMW_Kept(text,sizeof(text));return text;}
constexpr int FOREIGN_CASES=4;
int foreign_case(int scenario){
    const bool journaled=scenario%2==0,replaced=scenario>=2;
    fresh();put(actor,0x570,600000);plan_target=123456;expected_origin=0;disposition=journaled?1:0;
    CBMI_View id{};check(CBMI_Query(actor,&id));const auto ended=CBMW_Ended();const auto f=CBMW_Fallbacks(nullptr);
    const uint32_t queued=journaled?0u:1u; // A SET (Codex), or an ADD.
    // After a replacement the next allocation fails: keeping the outer write must need none.
    const std::function<void()> event=[replaced]{if(!replaced){foreign_event();return;}foreign_replacement();fail_allocation=true;};
    nested=[journaled,queued,event]{
        check(CBMW_Write(actor,0,54321,queued)==actor&&CBMW_LastStatus()==10&&read(0x570)==600000);
        if(!journaled)event();
    };
    if(journaled)after_plan=event;
    check(CBMW_Write(actor,0,700000,0)==actor);
    const bool unallocated=fail_allocation;fail_allocation=false;nested=after_plan=nullptr;check(unallocated==replaced);
    int last=0;CBMW_Fallbacks(&last);uint64_t count=0;const auto list=kept(&count);
    if(replaced){
        check(read(0x570)==10&&CBMW_Fallbacks(nullptr)==f&&CBMW_LastStatus()==12&&count==2);
        check(list==(journaled?"set 54321, set 700000":"add 54321, set 700000")); // Queued first, kept as they closed.
        check(!journaled||(journal&&uncertains==0)); // Its runtime is not called for it again: the journal stays.
    }else{
        check(read(0x570)==(journaled?54321u:754321u)&&CBMW_Fallbacks(nullptr)==f+2&&last==10);
        check(CBMW_LastStatus()==(journaled?7:8)&&count==0&&list.empty());
        check(!journaled||(journal&&uncertains==2)); // Asked to withdraw, then to mark: both found no identity.
    }
    check(CBMW_Ended()==ended&&CBMW_Holds(actor,id.incarnation)==(journaled?2:0));
    // Every later write is the game's own store: no identity (3).
    const auto xp=read(0x570);check(CBMW_Write(actor,0,1000,1)==actor&&read(0x570)==xp+1000&&CBMW_LastStatus()==3);
    if(replaced){
        check(kept(&count)==list&&count==2); // Kept for good, never applied later,
        // also once this thread ends what is at that address and constructs another
        // there (the old lifetime provably over): its write settles nothing kept.
        CBMI_Destruct(actor);CBMI_Construct(actor);check(CBMI_Lifetime(actor,id.incarnation)<0);
        const auto now=read(0x570);check(CBMW_Write(actor,0,1000,1)==actor&&read(0x570)==now+1000&&CBMW_LastStatus()==3);
        check(kept(&count)==list&&count==2&&CBMW_Ended()==ended);
    }
    std::printf("{\"writer_foreign_case\":%d,\"writer_assertions\":%d,\"game_launched\":false}\n",scenario,checks);
    return 0;
}
}
int main(int argc,char** argv){try{
    CBMI_Config id{1,{1,reinterpret_cast<uintptr_t>(marshal),1,1,reinterpret_cast<uintptr_t>(lifecycle),reinterpret_cast<uintptr_t>(lifecycle)},
        reinterpret_cast<uintptr_t>(lua_read),reinterpret_cast<uintptr_t>(lua_push),reinterpret_cast<uintptr_t>(lua_bool),
        reinterpret_cast<uintptr_t>(&strip),reinterpret_cast<uintptr_t>(&preview)};
    check(CBMI_Configure(&id));CBMI_Construct(actor);
    CBMW_Config cfg{1,reinterpret_cast<uintptr_t>(setter),reinterpret_cast<uintptr_t>(before),reinterpret_cast<uintptr_t>(complete),
        reinterpret_cast<uintptr_t>(uncertain),1,1,1};check(CBMW_Configure(&cfg));
    // writer_native_test foreign N: one case of another thread's lifetime event.
    if(argc==3&&std::strcmp(argv[1],"foreign")==0){
        const int n=std::atoi(argv[2]);return n>=0&&n<FOREIGN_CASES?foreign_case(n):2;
    }
    exercise(writer_body_2_6,sizeof(writer_body_2_6),writer_unwind_2_6,writer_end_2_6);
    exercise(writer_body_2_7,sizeof(writer_body_2_7),writer_unwind_2_7,writer_end_2_7);
    // Per window: an exception after the store and a failed completion (one call
    // each), three withdrawn journals (one) and three that could not be (two).
    check(uncertains==22&&withdrawals==6);
    std::printf("{\"writer_assertions\":%d,\"actual_native_windows\":2,\"windows_unwind_verified\":true,\"game_launched\":false}\n",checks);return 0;
}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
