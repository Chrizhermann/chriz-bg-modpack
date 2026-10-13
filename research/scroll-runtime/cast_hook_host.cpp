#include "cast_hook_host.h"
#include "cast_binding.hpp"
#include "cast_hook_code.hpp"
#include "selection_hook_group.hpp"
namespace {
cbm::scroll::hooks::Group entries;
cbm::scroll::hooks::SelectionGroup selectors;
bool have_entries{};std::array<char,256> error{};
void fail(const char* text)noexcept{const auto n=(std::min)(std::strlen(text),error.size()-1);std::memcpy(error.data(),text,n);error[n]=0;}
int install(const CBMS_CastFunctions& original,CBMS_Runtime* runtime) {
    if(have_entries||selectors.present())throw std::runtime_error("cast group already installed or rollback pending");
    const std::array<uintptr_t,8> native{reinterpret_cast<uintptr_t>(original.effect_fire),reinterpret_cast<uintptr_t>(original.fire),reinterpret_cast<uintptr_t>(original.fire_point),reinterpret_cast<uintptr_t>(original.force),reinterpret_cast<uintptr_t>(original.force_point),reinterpret_cast<uintptr_t>(original.spell),reinterpret_cast<uintptr_t>(original.spell_point),reinterpret_cast<uintptr_t>(original.child)};
    const std::array<uintptr_t,8> callbacks{reinterpret_cast<uintptr_t>(CBMS_EffectFireCarrier),reinterpret_cast<uintptr_t>(CBMS_FireCarrier),reinterpret_cast<uintptr_t>(CBMS_FirePointCarrier),reinterpret_cast<uintptr_t>(CBMS_ForceCarrier),reinterpret_cast<uintptr_t>(CBMS_ForcePointCarrier),reinterpret_cast<uintptr_t>(CBMS_SpellCarrier),reinterpret_cast<uintptr_t>(CBMS_SpellPointCarrier),reinterpret_cast<uintptr_t>(CBMS_SpellEffectCarrier)};
    std::vector<cbm::scroll::hooks::Entry> recipes;
    for(unsigned i=0;i<8;++i){const auto& c=cbms_cast_hook_code[i];recipes.push_back({native[i],callbacks[i],{c.prefix,c.prefix_size},{c.unwind,c.unwind_size},c.frame});}
    try {
        entries.install(recipes,[&](std::span<const uintptr_t> trampolines){
            auto f=original;f.effect_fire=reinterpret_cast<CBMS_EffectFireOriginal>(trampolines[0]);
            f.fire=reinterpret_cast<CBMS_FireOriginal>(trampolines[1]);f.fire_point=reinterpret_cast<CBMS_FireOriginal>(trampolines[2]);
            f.force=reinterpret_cast<CBMS_CastTargetOriginal>(trampolines[3]);f.force_point=reinterpret_cast<CBMS_CastPointOriginal>(trampolines[4]);
            f.spell=reinterpret_cast<CBMS_CastTargetOriginal>(trampolines[5]);f.spell_point=reinterpret_cast<CBMS_CastPointOriginal>(trampolines[6]);
            f.child=reinterpret_cast<CBMS_SpellEffectOriginal>(trampolines[7]);return CBMS_ConfigureCastCarriers(runtime,&f)==1;
        },[]{return CBMS_DetachCastCarriers()==1;},[]{return CBMS_CastCarriersIdle()==1;});
        have_entries=true;selectors.install(original);error.fill(0);return 1;
    }catch(...) {
        // If a CALL still reaches our selector, preserve the entry wrapper and
        // its runtime configuration. Never free reachable executable memory.
        if(have_entries&&!selectors.present()){try{entries.remove();have_entries=false;}catch(...){}}
        throw;
    }
}
}
int CBMS_BindCastModule(uintptr_t base,CBMS_CastFunctions* out,char* text,uint32_t capacity) {
    if(!out||!text||capacity<2)return 0;
    auto report=[&](const char* value){const auto n=(std::min)(std::strlen(value),std::size_t(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try{std::string detail;const auto result=cbm::scroll::binding::bind_cast(base,detail);*out=result;report(detail.c_str());return 1;}
    catch(const std::exception& issue){report(issue.what());}catch(...){report("unexpected native cast binding failure");}return 0;
}
int CBMS_InstallCastHooks(uintptr_t game,CBMS_Runtime* runtime) {
    try{std::string detail;return install(cbm::scroll::binding::bind_cast(game,detail),runtime);}
    catch(const std::exception& issue){fail(issue.what());}catch(...){fail("unexpected native cast hook installation failure");}return 0;
}
int CBMS_RemoveCastHooks() {
    try{entries.ready_remove();if(selectors.present())selectors.ready_remove();if(selectors.present())selectors.remove();entries.remove();have_entries=false;error.fill(0);return 1;}
    catch(const std::exception& issue){fail(issue.what());}catch(...){fail("unexpected native cast hook removal failure");}return 0;
}
const char* CBMS_CastHookError(){return error.data();}
extern "C" int CBMS_CastHooksPresent(){return entries.present()||selectors.present()?1:0;}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestInstallCastHooks(const CBMS_CastFunctions* functions,CBMS_Runtime* runtime) {
    try{if(!functions)throw std::invalid_argument("null private cast functions");return install(*functions,runtime);}
    catch(const std::exception& issue){fail(issue.what());}catch(...){fail("private cast hook installation failure");}return 0;
}
uintptr_t CBMS_TestCastHookAllocation(uint32_t selection){return selection?selectors.allocation():entries.allocation();}
void CBMS_TestCastHookFailure(uint32_t selection,int point){if(selection)selectors.inject_failure(point);else entries.inject_failure(point);}
#endif
