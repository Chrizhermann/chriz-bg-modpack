#include "dispatch_hook_host.h"
#include "dispatch_hook_code.hpp"
#include "entry_hook_group.hpp"
namespace {
cbm::scroll::hooks::Group group;
std::array<char,256> error{};
void fail(const char* text)noexcept{const auto n=(std::min)(std::strlen(text),error.size()-1);std::memcpy(error.data(),text,n);error[n]=0;}
int install(const CBMS_DispatchFunctions& original,CBMS_Runtime* runtime) {
    const std::array<uintptr_t,6> addresses{reinterpret_cast<uintptr_t>(original.apply146),reinterpret_cast<uintptr_t>(original.apply148),reinterpret_cast<uintptr_t>(original.action_default),reinterpret_cast<uintptr_t>(original.add_message),reinterpret_cast<uintptr_t>(original.fire_run),reinterpret_cast<uintptr_t>(original.fire_destroy)};
    const std::array<uintptr_t,6> callbacks{reinterpret_cast<uintptr_t>(CBMS_Apply146Carrier),reinterpret_cast<uintptr_t>(CBMS_Apply148Carrier),reinterpret_cast<uintptr_t>(CBMS_ActionDefaultCarrier),reinterpret_cast<uintptr_t>(CBMS_AddMessageCarrier),reinterpret_cast<uintptr_t>(CBMS_FireMessageRunCarrier),reinterpret_cast<uintptr_t>(CBMS_FireMessageDestroyCarrier)};
    std::vector<cbm::scroll::hooks::Entry> entries;
    for(unsigned i=0;i<6;++i){const auto& c=cbms_dispatch_hook_code[i];entries.push_back({addresses[i],callbacks[i],{c.prefix,c.prefix_size},{c.unwind,c.unwind_size},c.frame});}
    group.install(entries,[&](std::span<const uintptr_t> trampolines){
        auto bound=original;
        bound.apply146=reinterpret_cast<CBMS_ApplyOriginal>(trampolines[0]);bound.apply148=reinterpret_cast<CBMS_ApplyOriginal>(trampolines[1]);
        bound.action_default=reinterpret_cast<CBMS_ActionDefaultOriginal>(trampolines[2]);bound.add_message=reinterpret_cast<CBMS_AddMessageOriginal>(trampolines[3]);
        bound.fire_run=reinterpret_cast<CBMS_MessageRunOriginal>(trampolines[4]);bound.fire_destroy=reinterpret_cast<CBMS_MessageDestroyOriginal>(trampolines[5]);
        return CBMS_ConfigureDispatchCarriers(runtime,&bound)==1;
    },[]{return CBMS_DetachDispatchCarriers()==1;},[]{return CBMS_DispatchCarriersIdle()==1;});
    error.fill(0);return 1;
}
}
int CBMS_InstallDispatchHooks(uintptr_t game,CBMS_Runtime* runtime) {
    try {
        CBMS_DispatchFunctions functions{};std::array<char,512> diagnostic{};
        if(!CBMS_BindDispatchModule(game,&functions,diagnostic.data(),static_cast<uint32_t>(diagnostic.size())))throw std::runtime_error(diagnostic.data());
        return install(functions,runtime);
    }catch(const std::exception& issue){fail(issue.what());}catch(...){fail("unexpected native dispatch hook installation failure");}return 0;
}
int CBMS_RemoveDispatchHooks(){try{group.remove();error.fill(0);return 1;}catch(const std::exception& issue){fail(issue.what());}catch(...){fail("unexpected dispatch hook removal failure");}return 0;}
const char* CBMS_DispatchHookError(){return error.data();}
extern "C" int CBMS_DispatchHooksPresent(){return group.present()?1:0;}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestInstallDispatchHooks(const CBMS_DispatchFunctions* functions,CBMS_Runtime* runtime){
    try{if(!functions)throw std::invalid_argument("null private dispatch functions");return install(*functions,runtime);}
    catch(const std::exception& issue){fail(issue.what());}catch(...){fail("private dispatch hook installation failure");}return 0;
}
uintptr_t CBMS_TestDispatchHookAllocation(){return group.allocation();}
void CBMS_TestDispatchHookFailure(int point){group.inject_failure(point);}
#endif
