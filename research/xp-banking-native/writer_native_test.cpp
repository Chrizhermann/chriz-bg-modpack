// Actual pinned SetAtOffset windows, original unwind recipe, synthetic actors.
// DLL branch callback completes before native ProcessEffectList stub is called.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "writer_native.h"
#include "writer_native_windows.inc"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
namespace{
alignas(16) unsigned char actor[0x6000]{};
using Setter=uint16_t(*)(void*,uint32_t,uint32_t,uint32_t);
Setter current;
bool strip=false,preview=false,journal=false,throw_before=false,throw_complete=false,fail_complete=false,recalc_nested=false,in_recalc=false;
int checks=0,prepares=0,completes=0,recalcs=0,uncertains=0,disposition=1;
uint32_t plan_target=0,expected_origin=0;
void check_impl(bool x,int line){++checks;if(!x)throw std::runtime_error("writer assertion line "+std::to_string(line));}
#define check(x) check_impl((x),__LINE__)
uint32_t read(size_t at){uint32_t n;std::memcpy(&n,actor+at,4);return n;}
void put(void* p,size_t at,uint32_t n){std::memcpy(static_cast<unsigned char*>(p)+at,&n,4);}
void lifecycle(void*){}
CBMW_View view(){CBMW_View v{};check(CBMW_Query(actor,&v));return v;}
int before(void* a){
    check(a==actor);++prepares;auto v=view();
    check(v.stage==CBMW_PREPARING&&!v.planned&&v.pre_base==read(0x570)&&v.origin==expected_origin);
    if(disposition!=1)return disposition;
    journal=true;if(throw_before)throw std::runtime_error("before native store");
    check(CBMW_Plan(actor,plan_target)&&!CBMW_Plan(actor,plan_target+1));return 1;
}
int complete(void* a){
    check(a==actor&&journal);++completes;auto v=view();
    check(v.stage==CBMW_COMPLETING&&v.planned&&v.post_base==plan_target&&read(0x570)==plan_target);
    check(!CBMW_Plan(actor,0));
    if(throw_complete)throw std::runtime_error("after native store");
    if(fail_complete)return 0;journal=false;return 1;
}
int uncertain(void* a){check(a==actor&&journal&&view().stage==CBMW_UNCERTAIN);++uncertains;return 1;}
void recalc(void* a,uint32_t force){
    check(a==actor&&force==1&&read(0x4ba4)==1);++recalcs;
    check(!journal||fail_complete);
    if(recalc_nested&&!in_recalc){
        in_recalc=true;expected_origin=0;plan_target=read(0x570)+1;
        check(current(actor,44,1,1)==0xffff);in_recalc=false;
    }
}
uint16_t setter(void* a,uint32_t stat,uint32_t value,uint32_t mode){return current(a,stat,value,mode);}
void fresh(){CBMI_Destruct(actor);CBMI_Construct(actor);journal=false;}
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
    // Unowned native SET/ADD retains exact modulo32 semantics.
    disposition=2;put(actor,0x570,0xfffffff0);check(current(actor,44,32,1)==0xffff&&read(0x570)==16);
    check(current(actor,44,4321,4)==0xffff&&read(0x570)==4321);disposition=1;
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
    check(read(0x570)==12345);fail_complete=false;fresh();
    // Proven scope unwinds after exception; the next ordinary call is unclassified.
    throw_before=true;expected_origin=1;uint16_t ignored=0;
    try{CBMW_ApplyOwnedSet(actor,20000,1,&ignored);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="before native store");}
    throw_before=false;fresh();expected_origin=0;plan_target=44;
    check(current(actor,44,44,0)==0xffff&&read(0x570)==44);
    check(!CBMW_ApplyOwnedSet(actor,5,9,&ignored));
    check(RtlDeleteFunctionTable(&function)!=0);check(VirtualFree(mem,0,MEM_RELEASE)!=0);
}
}
int main(){try{
    CBMI_Config id{1,{1,1,1,1,reinterpret_cast<uintptr_t>(lifecycle),reinterpret_cast<uintptr_t>(lifecycle)},
        1,1,1,reinterpret_cast<uintptr_t>(&strip),reinterpret_cast<uintptr_t>(&preview)};
    check(CBMI_Configure(&id));CBMI_Construct(actor);
    CBMW_Config cfg{1,reinterpret_cast<uintptr_t>(setter),reinterpret_cast<uintptr_t>(before),reinterpret_cast<uintptr_t>(complete),
        reinterpret_cast<uintptr_t>(uncertain),1,1,1};check(CBMW_Configure(&cfg));
    exercise(writer_body_2_6,sizeof(writer_body_2_6),writer_unwind_2_6,writer_end_2_6);
    exercise(writer_body_2_7,sizeof(writer_body_2_7),writer_unwind_2_7,writer_end_2_7);
    check(uncertains==4);
    std::printf("{\"writer_assertions\":%d,\"actual_native_windows\":2,\"windows_unwind_verified\":true,\"game_launched\":false}\n",checks);return 0;
}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
