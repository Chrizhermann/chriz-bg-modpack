// Runs the actual audited native opcode104 bytes on synthetic buffers only.
// The original dispatch can inject faults around that leaf for recovery tests.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "award_native.h"
#include "writer_native.h"
#include "award_native_leaf.inc"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>
#include <limits>
namespace {
alignas(16) unsigned char actor[0x6000]{},effect[0x200]{},other[0x200]{};
using Apply=int(*)(void*,void*);
Apply leaf;
bool strip=false,preview=false,journal=false,fail_complete=false,throw_native=false,corrupt_result=false,reenter=false;
int disposition=1,checks=0,calls=0,prepares=0,uncertains=0;
uint64_t overflow=0;
int write_disposition=2,write_prepares=0,write_completes=0,write_uncertains=0;
uint32_t write_target=0,expected_effect_mode=0,expected_raw=0;
bool write_journal=false,write_fail_complete=false,write_reenter=false;
void check_impl(bool result,int line){++checks;if(!result)throw std::runtime_error("award assertion line "+std::to_string(line));}
#define check(x) check_impl((x),__LINE__)
uint32_t read(const void* p,size_t n){uint32_t x;std::memcpy(&x,static_cast<const unsigned char*>(p)+n,4);return x;}
void write(void* p,size_t n,uint32_t x){std::memcpy(static_cast<unsigned char*>(p)+n,&x,4);}
void lifecycle(void*){}
void* copy_actor(void*,int,int,int,int){CBMI_Construct(actor);return actor;}
CBMA_View view(){CBMA_View r{};check(CBMA_Query(actor,effect,&r));return r;}
int before(void* a,void* e){
    ++prepares;check(a==actor&&e==effect);
    auto r=view();check(r.stage==CBMA_PREPARING&&r.pre_base==read(actor,0x570));
    check(r.amount==read(effect,0x1c)&&r.amount==r.applied+r.remainder);
    check(!CBMA_Query(actor,other,&r));
    if(reenter){check(CBMA_ApplyEffect(effect,actor)==0);check(read(actor,0x570)==r.pre_base);}
    if(disposition==1)journal=true;
    return disposition;
}
int complete(void* a,void* e){
    check(a==actor&&e==effect&&journal);
    auto r=view();check(r.stage==CBMA_COMPLETING&&r.native_result==1);
    check(r.post_base==read(actor,0x570)&&r.post_base==r.pre_base+r.applied);
    check(read(effect,0x1c)==r.amount&&read(effect,0x114)==1&&read(effect,0x118)==1);
    if(fail_complete)return 0;
    overflow+=r.remainder;journal=false;return 1;
}
int uncertain(void* a,void* e){
    check(a==actor&&e==effect&&journal);auto r=view();
    check(r.stage==CBMA_UNCERTAIN&&read(effect,0x1c)==r.amount);++uncertains;return 1;
}
int dispatch(void* e,void* a){
    ++calls;
    int result=leaf(e,a);
    if(throw_native)throw std::runtime_error("injected after native store");
    return corrupt_result?0:result;
}
void setup(uint32_t xp,uint32_t amount,uint32_t mode=0,uint32_t timing=1){
    std::memset(effect,0,sizeof(effect));write(effect,0x10,104);write(effect,0x1c,amount);
    write(effect,0x20,mode);write(effect,0x24,timing);write(actor,0x570,xp);
    write(actor,0x1180,4321);write(actor,0x2ad0,1234);
}
void new_lifetime(){CBMI_Destruct(actor);CBMI_Construct(actor);journal=false;}
CBMW_View writer_view(){CBMW_View v{};check(CBMW_Query(actor,&v));return v;}
int write_before(void* a){
    check(a==actor);++write_prepares;auto v=writer_view();
    check(v.source==1&&v.effect==effect&&v.stage==CBMW_PREPARING&&v.origin==0);
    check(v.raw_value==read(effect,0x1c)&&v.effect_mode==read(effect,0x20)&&v.pre_base==read(actor,0x570));
    check(v.mode==(v.effect_mode==0?1u:v.effect_mode==1?0u:2u));
    if(write_disposition!=1)return write_disposition;
    if(write_reenter){check(CBMA_ApplyEffect(effect,actor)==0);check(read(actor,0x570)==v.pre_base);}
    write_journal=true;check(CBMW_Plan(actor,write_target));return 1;
}
int write_complete(void* a){
    check(a==actor&&write_journal);++write_completes;auto v=writer_view();
    check(v.stage==CBMW_COMPLETING&&v.native_result==1&&v.post_base==write_target);
    check(read(effect,0x1c)==expected_raw&&read(effect,0x20)==expected_effect_mode);
    check(read(effect,0x114)==1&&read(effect,0x118)==1);
    if(write_fail_complete)return 0;write_journal=false;return 1;
}
int write_uncertain(void* a){
    check(a==actor&&write_journal&&writer_view().stage==CBMW_UNCERTAIN);++write_uncertains;
    check(read(effect,0x1c)==expected_raw&&read(effect,0x20)==expected_effect_mode);return 1;
}
}
int run(){
    void* executable=VirtualAlloc(nullptr,sizeof(native_leaf),MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    check(executable!=nullptr);std::memcpy(executable,native_leaf,sizeof(native_leaf));
    DWORD old;check(VirtualProtect(executable,sizeof(native_leaf),PAGE_EXECUTE_READ,&old)!=0);
    check(FlushInstructionCache(GetCurrentProcess(),executable,sizeof(native_leaf))!=0);
    leaf=reinterpret_cast<Apply>(executable);
    CBMI_Config id{1,{reinterpret_cast<uintptr_t>(copy_actor),1,1,1,reinterpret_cast<uintptr_t>(lifecycle),reinterpret_cast<uintptr_t>(lifecycle)},
        1,1,1,reinterpret_cast<uintptr_t>(&strip),reinterpret_cast<uintptr_t>(&preview)};
    check(CBMI_Configure(&id));CBMI_Construct(actor);
    CBMA_Config cfg{1,reinterpret_cast<uintptr_t>(dispatch),reinterpret_cast<uintptr_t>(before),
        reinterpret_cast<uintptr_t>(complete),reinterpret_cast<uintptr_t>(uncertain),1,1};
    check(!CBMA_Configure(nullptr)&&CBMA_Configure(&cfg)&&!CBMA_Configure(&cfg));
    CBMW_Config writer{1,1,reinterpret_cast<uintptr_t>(write_before),reinterpret_cast<uintptr_t>(write_complete),
        reinterpret_cast<uintptr_t>(write_uncertain),1,1,1};check(CBMW_Configure(&writer));
    for(auto xp:{0u,160999u,499999u,0x7fffffffu,0xfffffffeu,0xffffffffu}){
        for(auto amount:{1u,2u,17u,0x7fffffffu}){
            setup(xp,amount);uint64_t old_overflow=overflow;
            check(CBMA_ApplyEffect(effect,actor)==1&&!journal);
            check(static_cast<uint64_t>(xp)+amount==read(actor,0x570)+overflow-old_overflow);
            check(read(effect,0x1c)==amount&&read(actor,0x1180)==4321&&read(actor,0x2ad0)==1234);
            CBMA_View absent{};check(!CBMA_Query(actor,effect,&absent));
        }
    }
    // Consecutive awards after saturation add only each after-split entitlement.
    setup(0xfffffff0,17);uint64_t old_overflow=overflow;
    check(CBMA_ApplyEffect(effect,actor)==1);write(effect,0x1c,27);
    check(CBMA_ApplyEffect(effect,actor)==1);
    check(read(actor,0x570)==0xffffffff&&overflow-old_overflow==29);
    // Compare untouched non-earned paths against independent original leaf runs.
    for(auto mode:{0u,1u,2u,9u})for(auto timing:{0u,1u})for(auto amount:{0u,27u,0xffffffe5u}){
        if(mode==0&&timing==1&&amount==27)continue;
        setup(1000,amount,mode,timing);
        alignas(16) unsigned char baseline_actor[sizeof(actor)],baseline_effect[sizeof(effect)];
        std::memcpy(baseline_actor,actor,sizeof(actor));std::memcpy(baseline_effect,effect,sizeof(effect));
        int expected=leaf(baseline_effect,baseline_actor);int old_prepares=prepares;
        check(CBMA_ApplyEffect(effect,actor)==expected&&prepares==old_prepares);
        check(std::memcmp(actor,baseline_actor,sizeof(actor))==0&&std::memcmp(effect,baseline_effect,sizeof(effect))==0);
    }
    disposition=2;setup(0xfffffff0,32);old_overflow=overflow;
    check(CBMA_ApplyEffect(effect,actor)==1&&read(actor,0x570)==16&&overflow==old_overflow);
    throw_native=true;setup(1000,1);
    try{CBMA_ApplyEffect(effect,actor);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="injected after native store");}
    check(read(actor,0x570)==1001&&!journal);throw_native=false;
    disposition=0;setup(500000,32);int old_calls=calls;
    check(CBMA_ApplyEffect(effect,actor)==0&&read(actor,0x570)==500000&&calls==old_calls);
    disposition=1;reenter=true;setup(0xfffffff0,32);
    check(CBMA_ApplyEffect(effect,actor)==1&&calls==old_calls+1);reenter=false;
    fail_complete=true;setup(0xfffffff0,32);
    check(CBMA_ApplyEffect(effect,actor)==1&&journal&&view().stage==CBMA_UNCERTAIN);
    old_calls=calls;check(CBMA_ApplyEffect(effect,actor)==0&&calls==old_calls);
    check(read(effect,0x1c)==32&&read(actor,0x570)==0xffffffff);fail_complete=false;
    new_lifetime();setup(0xfffffff0,32);throw_native=true;
    try{CBMA_ApplyEffect(effect,actor);check(false);}catch(const std::runtime_error& e){check(std::string(e.what())=="injected after native store");}
    check(journal&&view().stage==CBMA_UNCERTAIN&&read(effect,0x1c)==32&&view().post_base==0xffffffff);
    throw_native=false;new_lifetime();setup(0xfffffff0,32);corrupt_result=true;
    check(CBMA_ApplyEffect(effect,actor)==0&&journal&&view().stage==CBMA_UNCERTAIN);
    check(uncertains==3);corrupt_result=false;new_lifetime();setup(1000,1);
    old_calls=calls;int foreign=-1;std::thread thread([&]{foreign=CBMA_ApplyEffect(effect,actor);});thread.join();
    check(foreign==0&&calls==old_calls&&read(actor,0x570)==1000);
    check(CBMA_ApplyEffect(effect,actor)==1&&read(actor,0x570)==1001);
    // Real permanent effect routes execute the actual leaf's SET branch after
    // a planned account operation, then restore all original effect parameters.
    write_disposition=1;
    struct Case{uint32_t xp,raw,mode,target;};
    for(const auto c:{Case{1000,0xffffffe5,0,973},Case{0xffffffff,0xffffff38,0,0xffffff9b},
                      Case{600000,1234,1,1234},Case{1000,50,2,500},Case{0x80000000,100,2,0},Case{1000,0,0,1000}}){
        new_lifetime();setup(c.xp,c.raw,c.mode);write_target=c.target;expected_raw=c.raw;expected_effect_mode=c.mode;
        alignas(16) unsigned char expected_actor[sizeof(actor)],expected_effect[sizeof(effect)];
        std::memcpy(expected_actor,actor,sizeof(actor));std::memcpy(expected_effect,effect,sizeof(effect));
        write(expected_effect,0x1c,c.target);write(expected_effect,0x20,1);check(leaf(expected_effect,expected_actor)==1);
        write(expected_effect,0x1c,c.raw);write(expected_effect,0x20,c.mode);
        write_reenter=true;check(CBMA_ApplyEffect(effect,actor)==1&&!write_journal&&CBMW_LastStatus()==6);write_reenter=false;
        check(std::memcmp(actor,expected_actor,sizeof(actor))==0&&std::memcmp(effect,expected_effect,sizeof(effect))==0);
    }
    new_lifetime();setup(600000,50,2);write_disposition=0;int saved_calls=calls;
    check(CBMA_ApplyEffect(effect,actor)==0&&calls==saved_calls&&read(actor,0x570)==600000&&read(effect,0x114)==0);
    write_disposition=1;expected_effect_mode=2;expected_raw=50;write_target=300000;write_fail_complete=true;
    check(CBMA_ApplyEffect(effect,actor)==1&&write_journal&&writer_view().stage==CBMW_UNCERTAIN);
    saved_calls=calls;check(CBMA_ApplyEffect(effect,actor)==0&&calls==saved_calls);write_fail_complete=false;
    new_lifetime();write_journal=false;setup(1000,17,1);expected_effect_mode=1;expected_raw=17;write_target=17;throw_native=true;
    try{CBMA_ApplyEffect(effect,actor);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="injected after native store");}
    check(write_journal&&writer_view().post_base==17&&read(effect,0x1c)==17&&read(effect,0x20)==1);
    check(write_uncertains==2&&write_completes==7);throw_native=false;new_lifetime();write_journal=false;
    CBMI_Destruct(actor);setup(1000,1);check(CBMA_ApplyEffect(effect,actor)==0&&CBMA_LastStatus()==3);
    check(CBMI_Copy(other,0,0,0,0)==actor);setup(0xfffffff0,32);int old_prepares=prepares;
    check(CBMA_ApplyEffect(effect,actor)==1&&prepares==old_prepares&&read(actor,0x570)==16);
    check(VirtualFree(executable,0,MEM_RELEASE)!=0);
    std::printf("{\"award_assertions\":%d,\"actual_native_leaf_executed\":true,\"game_launched\":false}\n",checks);
    return 0;
}
int main(){try{return run();}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
