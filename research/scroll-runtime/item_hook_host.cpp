#include "item_hook_host.h"
#include "item_hook_code.hpp"
#include <algorithm>
#include <array>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <thread>
#include <vector>
#define NOMINMAX
#include <windows.h>
namespace {
std::array<char,256> diagnostic{};
void fail(const char* text) noexcept {
    const auto n=(std::min)(std::strlen(text),diagnostic.size()-1);
    std::memcpy(diagnostic.data(),text,n);diagnostic[n]=0;
}
std::vector<unsigned char> read(uintptr_t address,std::size_t size) {
    if(!address||size>UINTPTR_MAX-address)throw std::runtime_error("invalid item hook range");
    std::vector<unsigned char> result(size);SIZE_T got{};
    if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),result.data(),size,&got)||got!=size)
        throw std::runtime_error("native item entry is no longer readable");
    return result;
}
struct Patch {uintptr_t at{};std::vector<unsigned char> before,after;bool installed{},pending{};DWORD protection{};};
struct State {
    std::thread::id owner{std::this_thread::get_id()};
    void* memory{};RUNTIME_FUNCTION* table{};bool registered{},configured{};
    std::array<Patch,5> patches;
};
std::unique_ptr<State> active;
#ifdef CBMS_OFFLINE_HARNESS
int failure_point{};
#endif
bool finalize(Patch& p) {
    DWORD ignored{};
    const auto protection=VirtualProtect(reinterpret_cast<void*>(p.at),p.before.size(),p.protection,&ignored)!=0;
    const auto cache=FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(p.at),p.before.size())!=0;
    p.pending=!protection||!cache;return !p.pending;
}
void write(Patch& p,bool forward) {
    const auto& expected=forward?p.before:p.after;
    const auto& replacement=forward?p.after:p.before;
    if(expected.empty()||expected.size()!=replacement.size()||read(p.at,expected.size())!=expected)
        throw std::runtime_error("another owner changed item hook bytes; refusing overwrite");
    SYSTEM_INFO system{};GetSystemInfo(&system);
    if(p.at/system.dwPageSize!=(p.at+expected.size()-1)/system.dwPageSize)
        throw std::runtime_error("item hook crosses page boundary; cannot restore one protection");
    DWORD old{};
    if(!VirtualProtect(reinterpret_cast<void*>(p.at),expected.size(),PAGE_EXECUTE_READWRITE,&old))
        throw std::runtime_error("cannot change item entry protection");
    if(!p.protection)p.protection=old;
    p.pending=true;std::memcpy(reinterpret_cast<void*>(p.at),replacement.data(),replacement.size());p.installed=forward;
#ifdef CBMS_OFFLINE_HARNESS
    if(forward&&failure_point==6){failure_point=0;throw std::runtime_error("injected item hook protection-finalization failure");}
#endif
    if(!finalize(p))throw std::runtime_error("item hook written but protection/cache restoration pending; retain allocation");
}
void* allocate_near(uintptr_t address) {
    SYSTEM_INFO system{};GetSystemInfo(&system);
    const auto step=static_cast<uintptr_t>(system.dwAllocationGranularity),center=address&~(step-1);
    for(uintptr_t distance=step;distance<0x7FFF0000;distance+=step)for(int direction:{1,-1}) {
        if((direction<0&&distance>=center)||(direction>0&&distance>UINTPTR_MAX-center))continue;
        const auto at=direction>0?center+distance:center-distance;
        MEMORY_BASIC_INFORMATION info{};
        if(VirtualQuery(reinterpret_cast<void*>(at),&info,sizeof info)!=sizeof info||info.State!=MEM_FREE)continue;
        if(auto* out=VirtualAlloc(reinterpret_cast<void*>(at),0x1000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE))return out;
    }
    throw std::runtime_error("cannot allocate item relay page within rel32 distance");
}
void absolute_jump(unsigned char* out,uintptr_t target) {
    const unsigned char opcode[]{0xFF,0x25,0,0,0,0};std::memcpy(out,opcode,6);std::memcpy(out+6,&target,8);
}
bool cleanup(State& state) {
    for(auto& p:state.patches)if(p.installed)return false;
    for(auto& p:state.patches)if(p.pending&&!finalize(p))return false;
    if(state.configured){if(!CBMS_DetachItemCarriers())return false;state.configured=false;}
    if(state.registered){if(!RtlDeleteFunctionTable(state.table))return false;state.registered=false;}
    if(state.memory){if(!VirtualFree(state.memory,0,MEM_RELEASE))return false;state.memory=nullptr;}
    return true;
}
int install(const CBMS_ItemFunctions& bound,CBMS_Runtime* runtime,const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user) {
    if(active)throw std::runtime_error("item hooks already installed or rollback pending");
    auto next=std::make_unique<State>();
    const std::array<uintptr_t,5> entries{reinterpret_cast<uintptr_t>(bound.use),reinterpret_cast<uintptr_t>(bound.use_point),reinterpret_cast<uintptr_t>(bound.fire),reinterpret_cast<uintptr_t>(bound.fire_point),reinterpret_cast<uintptr_t>(bound.effect)};
    const std::array<uintptr_t,5> wrappers{reinterpret_cast<uintptr_t>(CBMS_UseItemCarrier),reinterpret_cast<uintptr_t>(CBMS_UsePointCarrier),reinterpret_cast<uintptr_t>(CBMS_FireItemCarrier),reinterpret_cast<uintptr_t>(CBMS_FireItemPointCarrier),reinterpret_cast<uintptr_t>(CBMS_ItemEffectCarrier)};
    for(unsigned i=0;i<5;++i) {
        const auto& code=cbms_item_hook_code[i];auto& p=next->patches[i];p.at=entries[i];p.before=read(p.at,code.prefix_size);
        if(!std::equal(p.before.begin(),p.before.end(),code.prefix))throw std::runtime_error("native item prefix changed after certification");
        for(unsigned j=0;j<i;++j)if(p.at<entries[j]+cbms_item_hook_code[j].prefix_size&&entries[j]<p.at+p.before.size())
            throw std::runtime_error("native item hook entries overlap");
    }
    active=std::move(next);auto& state=*active;
    try {
        state.memory=allocate_near(entries[0]);const auto base=reinterpret_cast<uintptr_t>(state.memory);
        auto* memory=static_cast<unsigned char*>(state.memory);state.table=reinterpret_cast<RUNTIME_FUNCTION*>(memory+0x600);
        std::array<uintptr_t,5> trampolines{};
        for(unsigned i=0;i<5;++i) {
            const auto offset=i*0x100u;const auto& code=cbms_item_hook_code[i];auto& p=state.patches[i];
            const auto relay=base+offset,trampoline=relay+0x20,resume=p.at+code.prefix_size;
            trampolines[i]=trampoline;absolute_jump(memory+offset,wrappers[i]);
            std::memcpy(memory+offset+0x20,code.prefix,code.prefix_size);
            auto* tail=memory+offset+0x20+code.prefix_size;
            if(code.frame) {
                const unsigned char first[]{0xC7,0x04,0x24},second[]{0xC7,0x44,0x24,0x04},branch[]{0xFF,0x64,0x24,0x00};
                const auto low=static_cast<uint32_t>(resume),high=static_cast<uint32_t>(resume>>32);
                std::memcpy(tail,first,3);std::memcpy(tail+3,&low,4);std::memcpy(tail+7,second,4);std::memcpy(tail+11,&high,4);std::memcpy(tail+15,branch,4);
            } else absolute_jump(tail,resume);
            std::memcpy(memory+offset+0x80,code.unwind,code.unwind_size);
            state.table[i]={offset+0x20,offset+0x20+code.prefix_size+(code.frame?19u:6u),offset+0x80};
            const auto delta=static_cast<int64_t>(relay)-static_cast<int64_t>(p.at+5);
            if(delta<INT32_MIN||delta>INT32_MAX)throw std::runtime_error("item hook group exceeds relay's rel32 reach");
            const auto rel=static_cast<int32_t>(delta);p.after.assign(code.prefix_size,0x90);p.after[0]=0xE9;std::memcpy(p.after.data()+1,&rel,4);
        }
        DWORD old{};
        if(!VirtualProtect(state.memory,0x1000,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),state.memory,0x1000))
            throw std::runtime_error("cannot finalize item trampoline page");
        if(!RtlAddFunctionTable(state.table,5,base))throw std::runtime_error("cannot register item trampoline unwind table");
        state.registered=true;
        auto functions=bound;
        functions.use=reinterpret_cast<CBMS_UseItemOriginal>(trampolines[0]);functions.use_point=reinterpret_cast<CBMS_UsePointOriginal>(trampolines[1]);
        functions.fire=reinterpret_cast<CBMS_FireItemOriginal>(trampolines[2]);functions.fire_point=reinterpret_cast<CBMS_FireItemOriginal>(trampolines[3]);
        functions.effect=reinterpret_cast<CBMS_ItemEffectOriginal>(trampolines[4]);
        if(!CBMS_ConfigureItemCarriers(runtime,&functions,policy,size,digest,user))throw std::runtime_error(CBMS_ItemCarrierError());
        state.configured=true;
        for(unsigned i=0;i<5;++i) {
            write(state.patches[i],true);
#ifdef CBMS_OFFLINE_HARNESS
            if(failure_point==static_cast<int>(i+1)){failure_point=0;throw std::runtime_error("injected partial item hook failure");}
#endif
        }
        diagnostic.fill(0);return 1;
    }catch(...) {
        bool restored=true;
        for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->installed) {
            try{write(*it,false);}catch(...){restored=false;}
        }
        if(restored&&cleanup(state))active.reset();
        throw;
    }
}
}
int CBMS_InstallItemHooks(uintptr_t game,CBMS_Runtime* runtime,const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user) {
    try {
        CBMS_ItemFunctions functions{};std::array<char,512> detail{};
        if(!CBMS_BindItemModule(game,&functions,detail.data(),static_cast<uint32_t>(detail.size())))throw std::runtime_error(detail.data());
        return install(functions,runtime,policy,size,digest,user);
    }catch(const std::exception& error){fail(error.what());}catch(...){fail("unexpected native item installation failure");}return 0;
}
int CBMS_RemoveItemHooks() {
    try {
        if(!active)throw std::runtime_error("item hook group is not installed");
        auto& state=*active;
        if(state.owner!=std::this_thread::get_id()||(state.configured&&!CBMS_ItemCarriersIdle()))
            throw std::runtime_error("item hook removal requires quiescent owner thread");
        for(const auto& p:state.patches)if(p.installed&&read(p.at,p.after.size())!=p.after)
            throw std::runtime_error("another owner changed an item entry; retain all hooks and refuse overwrite");
        for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->installed)write(*it,false);
        if(!cleanup(state))throw std::runtime_error("item entries restored but safe registration cleanup is pending");
        active.reset();diagnostic.fill(0);return 1;
    }catch(const std::exception& error){fail(error.what());}catch(...){fail("unexpected item hook removal failure");}return 0;
}
const char* CBMS_ItemHookError(){return diagnostic.data();}
extern "C" int CBMS_ItemHooksPresent(){return active?1:0;}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestInstallItemHooks(const CBMS_ItemFunctions* functions,CBMS_Runtime* runtime,const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user) {
    try {if(!functions)throw std::runtime_error("null fixture item functions");return install(*functions,runtime,policy,size,digest,user);}
    catch(const std::exception& error){fail(error.what());}catch(...){fail("private item installation failed");}return 0;
}
uintptr_t CBMS_TestItemHookAllocation(){return active?reinterpret_cast<uintptr_t>(active->memory):0;}
void CBMS_TestItemHookFailure(int value){failure_point=value;}
#endif
