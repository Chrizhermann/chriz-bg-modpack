#include "decode_hook_host.h"
#include "decode_carrier_api.h"
#include "marshal_carrier_api.h"
#include "lifecycle_carrier_api.h"
#include "lifecycle_binding.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <thread>
#include <vector>
#define NOMINMAX
#include <windows.h>

namespace {
constexpr std::array<unsigned char,7> prefix{0x4C,0x8B,0xDC,0x49,0x89,0x5B,0x10};
constexpr std::array<unsigned char,17> marshal_prefix{0x40,0x53,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x48,0x81,0xEC,0x88,0x01,0x00,0x00};
constexpr std::array<unsigned char,7> life_copy_prefix{0x4C,0x8B,0xDC,0x49,0x89,0x53,0x10};
constexpr std::array<unsigned char,7> life_destroy_prefix{0x4C,0x8B,0xDC,0x49,0x89,0x4B,0x08};
std::array<char,256> error{};
void failure(const char* message) noexcept {
    auto n=std::strlen(message); if(n>=error.size()) n=error.size()-1;
    std::memcpy(error.data(),message,n);error[n]=0;
}
std::vector<unsigned char> read(uintptr_t address,std::size_t size) {
    if (!address || size>UINTPTR_MAX-address) throw std::runtime_error("invalid decode hook range");
    std::vector<unsigned char> bytes(size);SIZE_T copied{};
    if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),bytes.data(),size,&copied)||copied!=size)
        throw std::runtime_error("decode hook site became unreadable");
    return bytes;
}
std::array<unsigned char,14> jump(uintptr_t target) {
    std::array<unsigned char,14> code{0xFF,0x25,0,0,0,0};std::memcpy(code.data()+6,&target,8);return code;
}
struct Patch { uintptr_t at;std::vector<unsigned char> before,after;bool installed{};DWORD original_protection{};bool pending_finalize{}; };
struct Installed {
    std::thread::id owner{std::this_thread::get_id()};
    void* memory{};RUNTIME_FUNCTION* table{};bool registered{},configured{},marshal_configured{};
    void* life_memory{};RUNTIME_FUNCTION* life_table{};bool life_registered{},life_configured{};
    std::vector<Patch> patches;
};
std::unique_ptr<Installed> installed;
#ifdef CBMS_OFFLINE_HARNESS
int test_failure{};
#endif
bool finalize(Patch& patch) {
    DWORD ignored{};
    const bool restored=VirtualProtect(reinterpret_cast<void*>(patch.at),patch.before.size(),patch.original_protection,&ignored)!=0;
    const bool flushed=FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(patch.at),patch.before.size())!=0;
    patch.pending_finalize=!restored||!flushed;
    return !patch.pending_finalize;
}
void write(Patch& patch,bool forward) {
    const auto& expected=forward?patch.before:patch.after;
    const auto& replacement=forward?patch.after:patch.before;
    if(expected.empty()||expected.size()!=replacement.size()) throw std::runtime_error("native hook replacement extent does not match its certified site");
    if(read(patch.at,expected.size())!=expected) throw std::runtime_error("decode hook changed by another owner; refusing overwrite");
    DWORD old{};
    SYSTEM_INFO system{};GetSystemInfo(&system);
    if (patch.at/system.dwPageSize!=(patch.at+replacement.size()-1)/system.dwPageSize)
        throw std::runtime_error("decoder patch crosses a page; protection restoration needs separate regions");
    if(!VirtualProtect(reinterpret_cast<void*>(patch.at),replacement.size(),PAGE_EXECUTE_READWRITE,&old))
        throw std::runtime_error("cannot change decode hook page protection");
    if (!patch.original_protection) patch.original_protection=old;
    // Caller excludes execution/unload/other writers during this transaction.
    patch.pending_finalize=true;
    std::memcpy(reinterpret_cast<void*>(patch.at),replacement.data(),replacement.size());
    patch.installed=forward; // keep allocation alive if later protection/cache operation fails
#ifdef CBMS_OFFLINE_HARNESS
    if(forward&&test_failure==2) {test_failure=0;throw std::runtime_error("injected failure before protection restoration");}
#endif
    if(!finalize(patch)) throw std::runtime_error("decode hook written but protection/cache restoration failed; retain host for rollback");
}
void* allocate_near(uintptr_t entry) {
    SYSTEM_INFO system{};GetSystemInfo(&system);
    const auto granularity=static_cast<uintptr_t>(system.dwAllocationGranularity);
    const auto center=entry&~(granularity-1);
    for(uintptr_t distance=granularity;distance<0x7FFF0000;distance+=granularity) {
        for(int direction:{1,-1}) {
            if(direction<0 && distance>=center) continue;
            if(direction>0 && distance>UINTPTR_MAX-center) continue;
            const auto at=direction>0?center+distance:center-distance;
            MEMORY_BASIC_INFORMATION region{};
            if(VirtualQuery(reinterpret_cast<void*>(at),&region,sizeof region)!=sizeof region || region.State!=MEM_FREE) continue;
            if(auto* memory=VirtualAlloc(reinterpret_cast<void*>(at),0x1000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)) return memory;
        }
    }
    throw std::runtime_error("no free rel32 decoder relay page near native entry");
}
bool cleanup(Installed& state) {
    for(auto& patch:state.patches) if(patch.installed) return false;
    for(auto& patch:state.patches) if(patch.pending_finalize&&!finalize(patch)) return false;
    if(state.life_configured) {
        if(!CBMS_DetachLifecycleCarriers()) return false;
        state.life_configured=false;
    }
    if(state.marshal_configured) {
        if(!CBMS_DetachMarshalCarrier()) return false;
        state.marshal_configured=false;
    }
    if(state.configured) {
        if(!CBMS_DetachDecodeCarrier()) return false;
        state.configured=false;
    }
    if(state.registered) {
        if(!RtlDeleteFunctionTable(state.table)) return false;
        state.registered=false;
    }
    if(state.life_registered) {
        if(!RtlDeleteFunctionTable(state.life_table)) return false;
        state.life_registered=false;
    }
    if(state.life_memory) {
        if(!VirtualFree(state.life_memory,0,MEM_RELEASE)) return false;
        state.life_memory=nullptr;
    }
    if(state.memory) {
        if(!VirtualFree(state.memory,0,MEM_RELEASE)) return false;
        state.memory=nullptr;
    }
    return true;
}
int install(const CBMS_DecodeFunctions& bound,uintptr_t marshal=0,const CBMS_LifecycleFunctions* life=nullptr,const CBMS_BankActorChain* bank=nullptr) {
    if(installed) throw std::runtime_error("decoder hook subsystem already installed or awaiting rollback");
    auto state=std::make_unique<Installed>();
    state->patches.push_back({bound.native_decoder_entry,read(bound.native_decoder_entry,7),{},false});
    // Keep every byte EEex's jump occupies (5-21) so removal restores its exact
    // route; our 14-byte jump replaces the start and leaves any rest as it was.
    const auto window=read(bound.native_unmarshal_entry,cbm::scroll::binding::existing_jump_window);
    const auto route=cbm::scroll::binding::existing_eeex_jump(window,bound.native_unmarshal_entry);
    const auto saved=static_cast<std::ptrdiff_t>((std::max)(route.length,std::size_t{14}));
    state->patches.push_back({bound.native_unmarshal_entry,{window.begin(),window.begin()+saved},{},false});
    if(marshal) {
        state->patches.push_back({marshal,read(marshal,marshal_prefix.size()),{},false});
        if(!std::equal(marshal_prefix.begin(),marshal_prefix.end(),state->patches.back().before.begin()))
            throw std::runtime_error("native Marshal prologue changed since certification");
    }
    if(life) {
        if(!marshal) throw std::runtime_error("lifecycle install requires the complete effect persistence group");
        const std::array<uintptr_t,3> entries{life->copy,life->effect_destroy,life->actor_destroy};
        for(unsigned i=0;i<3;++i) {
            state->patches.push_back({entries[i],read(entries[i],7),{},false});
            const auto& wanted=i?life_destroy_prefix:life_copy_prefix;
            if(i==2&&bank)cbm::scroll::binding::authenticate_bank_actor(*bank,entries[i]);
            else if(!std::equal(wanted.begin(),wanted.end(),state->patches.back().before.begin()))
                throw std::runtime_error("EEex lifecycle prefix changed since certification");
        }
    }
    if(!std::equal(prefix.begin(),prefix.end(),state->patches[0].before.begin())) throw std::runtime_error("decoder prefix changed since certification");
    const auto previous=route.target;
    if(!previous || previous!=bound.previous_eeex_unmarshal) throw std::runtime_error("existing EEex route changed since certification");
    // Publish owner before any fallible registration; no failed path frees a
    // page that remains referenced by an entry or the OS unwind registry.
    installed=std::move(state);auto& live=*installed;
    try {
        live.memory=allocate_near(bound.native_decoder_entry);
        auto* bytes=static_cast<unsigned char*>(live.memory);const auto base=reinterpret_cast<uintptr_t>(bytes);
        const auto relay=jump(reinterpret_cast<uintptr_t>(CBMS_DecodeCarrier));std::memcpy(bytes,relay.data(),relay.size());
        std::memcpy(bytes+0x20,prefix.data(),prefix.size());
        const auto resume=jump(bound.native_decoder_entry+7);std::memcpy(bytes+0x27,resume.data(),resume.size());
        constexpr unsigned char unwind[]{1,7,2,0,7,0x34,2,0};std::memcpy(bytes+0x40,unwind,sizeof unwind);
        live.table=reinterpret_cast<RUNTIME_FUNCTION*>(bytes+0x50);*live.table={0x20,0x2D,0x40};
        if(marshal) {
            const auto wrapper=jump(reinterpret_cast<uintptr_t>(CBMS_MarshalCarrier));std::memcpy(bytes+0x100,wrapper.data(),wrapper.size());
            std::memcpy(bytes+0x120,marshal_prefix.data(),marshal_prefix.size());
            // Branch into active native frame through call-home space. FF25
            // here would be misclassified as an epilogue by RtlVirtualUnwind.
            unsigned char resume_marshal[]{0xC7,0x04,0x24,0,0,0,0,0xC7,0x44,0x24,0x04,0,0,0,0,0xFF,0x64,0x24,0x00};
            const auto target=marshal+marshal_prefix.size();const auto low=static_cast<uint32_t>(target),high=static_cast<uint32_t>(target>>32);
            std::memcpy(resume_marshal+3,&low,4);std::memcpy(resume_marshal+11,&high,4);
            std::memcpy(bytes+0x131,resume_marshal,sizeof resume_marshal);
            constexpr unsigned char marshal_unwind[]{1,17,8,0,17,1,0x31,0,10,0xE0,8,0xD0,6,0xC0,4,0x70,3,0x60,2,0x30};
            std::memcpy(bytes+0x180,marshal_unwind,sizeof marshal_unwind);live.table[1]={0x120,0x144,0x180};
        }
        DWORD old{};
        if(!VirtualProtect(bytes,0x1000,PAGE_EXECUTE_READ,&old) || !FlushInstructionCache(GetCurrentProcess(),bytes,0x1000))
            throw std::runtime_error("cannot finalize decoder code page");
        if(!RtlAddFunctionTable(live.table,marshal?2:1,base)) throw std::runtime_error("cannot register carrier trampoline unwind data");
        live.registered=true;
        if(life) {
            live.life_memory=allocate_near(life->copy);
            auto* life_bytes=static_cast<unsigned char*>(live.life_memory);const auto life_base=reinterpret_cast<uintptr_t>(life_bytes);
            live.life_table=reinterpret_cast<RUNTIME_FUNCTION*>(life_bytes+0x300);
            const std::array<uintptr_t,3> callbacks{reinterpret_cast<uintptr_t>(CBMS_EffectCopyCarrier),reinterpret_cast<uintptr_t>(CBMS_EffectDestroyCarrier),reinterpret_cast<uintptr_t>(CBMS_ActorDestroyCarrier)};
            for(unsigned i=0;i<3;++i) {
                auto& patch=live.patches[3+i];const auto offset=i*0x80u;
                const auto life_relay=jump(callbacks[i]),life_resume=jump(patch.at+7);
                std::memcpy(life_bytes+offset,life_relay.data(),life_relay.size());
                if(i==2&&bank) {
                    // Call the authenticated banking carrier, which owns its
                    // native original. Never relocate its installed E9.
                    const auto bank_tail=jump(bank->handler);std::memcpy(life_bytes+offset+0x20,bank_tail.data(),bank_tail.size());
                    constexpr unsigned char leaf[]{1,0,0,0};std::memcpy(life_bytes+offset+0x40,leaf,sizeof leaf);
                    live.life_table[i]={offset+0x20,offset+0x26,offset+0x40};
                }else{
                    std::memcpy(life_bytes+offset+0x20,patch.before.data(),7);
                    std::memcpy(life_bytes+offset+0x27,life_resume.data(),life_resume.size());
                    constexpr unsigned char leaf_unwind[]{1,7,0,0};std::memcpy(life_bytes+offset+0x40,leaf_unwind,sizeof leaf_unwind);
                    live.life_table[i]={offset+0x20,offset+0x2D,offset+0x40};
                }
                const auto displacement=static_cast<std::int64_t>(life_base+offset)-static_cast<std::int64_t>(patch.at+5);
                if(displacement<INT32_MIN||displacement>INT32_MAX) throw std::runtime_error("EEex lifecycle relay outside rel32 range");
                const auto delta=static_cast<std::int32_t>(displacement);patch.after={0xE9,0,0,0,0,0x90,0x90};std::memcpy(patch.after.data()+1,&delta,4);
            }
            DWORD prior{};
            if(!VirtualProtect(life_bytes,0x1000,PAGE_EXECUTE_READ,&prior)||!FlushInstructionCache(GetCurrentProcess(),life_bytes,0x1000))
                throw std::runtime_error("cannot finalize EEex lifecycle trampoline page");
            if(!RtlAddFunctionTable(live.life_table,3,life_base)) throw std::runtime_error("cannot register EEex lifecycle trampoline unwind data");
            live.life_registered=true;
            if(!CBMS_ConfigureLifecycleCarriers(reinterpret_cast<CBMS_EffectCopyOriginal>(life_bytes+0x20),
                reinterpret_cast<CBMS_DestroyOriginal>(life_bytes+0xA0),bank?reinterpret_cast<CBMS_DestroyOriginal>(bank->handler):reinterpret_cast<CBMS_DestroyOriginal>(life_bytes+0x120)))
                throw std::runtime_error("cannot configure chained EEex lifecycle callbacks");
            live.life_configured=true;
        }
        if(!CBMS_ConfigureDecodeCarrier(reinterpret_cast<CBMS_PreviousUnmarshal>(previous),reinterpret_cast<CBMS_NativeDecoderTrampoline>(bytes+0x20)))
            throw std::runtime_error("cannot configure independent decoder callbacks");
        live.configured=true;
        if(marshal) {
            if(!CBMS_ConfigureMarshalCarrier(reinterpret_cast<CBMS_NativeMarshalTrampoline>(bytes+0x120)))
                throw std::runtime_error("cannot configure independent native Marshal wrapper");
            live.marshal_configured=true;
            const auto displacement=static_cast<std::int64_t>(base+0x100)-static_cast<std::int64_t>(marshal+5);
            if(displacement<INT32_MIN||displacement>INT32_MAX) throw std::runtime_error("Marshal relay outside rel32 range");
            const auto delta=static_cast<std::int32_t>(displacement);auto& patch=live.patches[2];patch.after.assign(marshal_prefix.size(),0x90);
            patch.after[0]=0xE9;std::memcpy(patch.after.data()+1,&delta,4);
        }
        const auto displacement=static_cast<std::int64_t>(base)-static_cast<std::int64_t>(bound.native_decoder_entry+5);
        if(displacement<INT32_MIN||displacement>INT32_MAX) throw std::runtime_error("allocated decoder relay is outside rel32 range");
        const auto delta=static_cast<std::int32_t>(displacement);
        live.patches[0].after={0xE9,0,0,0,0,0x90,0x90};std::memcpy(live.patches[0].after.data()+1,&delta,4);
        const auto wrap=jump(reinterpret_cast<uintptr_t>(CBMS_UnmarshalCarrier));auto& unmarshal=live.patches[1];
        unmarshal.after.assign(wrap.begin(),wrap.end());
        unmarshal.after.insert(unmarshal.after.end(),unmarshal.before.begin()+static_cast<std::ptrdiff_t>(wrap.size()),unmarshal.before.end());
        write(live.patches[0],true);
#ifdef CBMS_OFFLINE_HARNESS
        if(test_failure==1) {test_failure=0;throw std::runtime_error("injected failure before second entry write");}
#endif
        write(live.patches[1],true);
        for(std::size_t i=2;i<live.patches.size();++i) write(live.patches[i],true);
#ifdef CBMS_OFFLINE_HARNESS
        if(test_failure==3) {test_failure=0;throw std::runtime_error("injected failure after all carrier entry writes");}
#endif
        error.fill(0);return 1;
    } catch(...) {
        // Caller has not resumed engine execution. Undo only our exact bytes.
        bool rolled_back=true;
        for(auto it=live.patches.rbegin();it!=live.patches.rend();++it) if(it->installed) {
            try { write(*it,false); } catch(...) { rolled_back=false; }
        }
        if(rolled_back&&cleanup(live)) installed.reset();
        throw;
    }
}
}
int CBMS_InstallDecodeHooks(uintptr_t game,uintptr_t eeex) {
    try {
        CBMS_DecodeFunctions bound{};std::array<char,512> diagnostic{};
        if(!CBMS_BindDecodeModules(game,eeex,&bound,diagnostic.data(),static_cast<uint32_t>(diagnostic.size())))
            throw std::runtime_error(diagnostic.data());
        return install(bound);
    } catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("unexpected independent decoder installation failure");}
    return 0;
}
int CBMS_RemoveDecodeHooks() {
    try {
        if(!installed) throw std::runtime_error("decoder hook subsystem is not installed");
        auto& state=*installed;
        if(state.owner!=std::this_thread::get_id() || (state.configured&&!CBMS_DecodeCarrierIdle()) ||
           (state.marshal_configured&&!CBMS_MarshalCarrierIdle()))
            throw std::runtime_error("decoder hook removal requires the quiescent owner thread");
        if(state.life_configured&&!CBMS_LifecycleCarriersIdle())
            throw std::runtime_error("decoder hook removal requires the quiescent owner thread");
        // Validate every live entry before changing either one.
        for(auto& patch:state.patches) if(patch.installed&&read(patch.at,patch.after.size())!=patch.after)
            throw std::runtime_error("another owner changed decoder hook; retain registration and refuse overwrite");
        for(auto it=state.patches.rbegin();it!=state.patches.rend();++it) if(it->installed) write(*it,false);
        if(!cleanup(state)) throw std::runtime_error("decoder entries restored but registration cleanup still pending");
        installed.reset();error.fill(0);return 1;
    } catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("unexpected independent decoder removal failure");}
    return 0;
}
const char* CBMS_DecodeHookError() {return error.data();}
extern "C" int CBMS_DecodeHooksPresent(){return installed?1:0;}
int CBMS_InstallPersistenceHooks(uintptr_t game,uintptr_t eeex) {
    try {
        CBMS_DecodeFunctions bound{};uintptr_t marshal{};std::array<char,512> diagnostic{};
        if(!CBMS_BindDecodeModules(game,eeex,&bound,diagnostic.data(),static_cast<uint32_t>(diagnostic.size()))||
           !CBMS_BindMarshalModule(game,&marshal,diagnostic.data(),static_cast<uint32_t>(diagnostic.size())))
            throw std::runtime_error(diagnostic.data());
        return install(bound,marshal);
    } catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("unexpected persistence-hook installation failure");}
    return 0;
}
int CBMS_InstallEffectPersistenceHooks(uintptr_t game,uintptr_t eeex) {
    return CBMS_InstallEffectPersistenceHooksChained(game,eeex,nullptr,nullptr);
}
int CBMS_InstallEffectPersistenceHooksChained(uintptr_t game,uintptr_t eeex,CBMS_BankActorQuery query,void* user) {
    try {
        CBMS_DecodeFunctions bound{};CBMS_LifecycleFunctions life{};CBMS_BankActorChain bank{};uintptr_t marshal{};std::array<char,512> diagnostic{};
        if(!CBMS_BindDecodeModules(game,eeex,&bound,diagnostic.data(),static_cast<uint32_t>(diagnostic.size()))||
           !CBMS_BindMarshalModule(game,&marshal,diagnostic.data(),static_cast<uint32_t>(diagnostic.size()))||
           !CBMS_BindLifecycleModulesChained(game,eeex,&life,query,user,&bank,diagnostic.data(),static_cast<uint32_t>(diagnostic.size())))
            throw std::runtime_error(diagnostic.data());
        return install(bound,marshal,&life,bank.schema?&bank:nullptr);
    } catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("unexpected effect-persistence hook installation failure");}
    return 0;
}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestInstallDecodeHooks(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous) {
    try {return install({unmarshal,previous,decoder});}
    catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("private decoder fixture install failed");}
    return 0;
}
uintptr_t CBMS_TestDecodeAllocation() {return installed?reinterpret_cast<uintptr_t>(installed->memory):0;}
void CBMS_TestDecodeFailure(int point) {test_failure=point;}
int CBMS_TestInstallPersistenceHooks(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous,uintptr_t marshal) {
    try {return install({unmarshal,previous,decoder},marshal);}
    catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("private persistence fixture install failed");}
    return 0;
}
int CBMS_TestInstallEffectPersistenceHooks(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous,uintptr_t marshal,uintptr_t copy,uintptr_t effect_destroy,uintptr_t actor_destroy) {
    try {const CBMS_LifecycleFunctions life{copy,effect_destroy,actor_destroy};return install({unmarshal,previous,decoder},marshal,&life);}
    catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("private effect-persistence fixture install failed");}
    return 0;
}
int CBMS_TestInstallEffectPersistenceHooksChained(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous,uintptr_t marshal,uintptr_t copy,uintptr_t effect_destroy,uintptr_t actor_destroy,const CBMS_BankActorChain* bank) {
    try {const CBMS_LifecycleFunctions life{copy,effect_destroy,actor_destroy};return install({unmarshal,previous,decoder},marshal,&life,bank);}
    catch(const std::exception& issue) {failure(issue.what());} catch(...) {failure("private banking chain fixture install failed");}
    return 0;
}
#endif
