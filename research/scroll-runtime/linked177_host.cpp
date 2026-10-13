#include "linked177_api.h"
#include "entry_hook_group.hpp"
#include "native_binder.hpp"
#include "decode_profiles.hpp"
#include "linked177_profiles.hpp"
namespace {
cbm::scroll::hooks::Group group;std::array<char,256> error{};
void fail(const char* text)noexcept{const auto n=(std::min)(std::strlen(text),error.size()-1);std::memcpy(error.data(),text,n);error[n]=0;}
CBMS_LinkedFunctions bind(uintptr_t base) {
    using namespace cbm::scroll::binding;std::string detail;(void)cbm::scroll::binding::bind(base,detail);Image image(base);
    const auto stamp=image.object<IMAGE_FILE_HEADER>(image.object<IMAGE_DOS_HEADER>(0).e_lfanew+4).TimeDateStamp;
    const Linked177Profile* profile{};for(const auto& p:linked177_profiles)if(p.timestamp==stamp)profile=&p;
    if(!profile)throw std::runtime_error("opcode177 carrier has no audited native build");
    for(const auto& span:{profile->parent,profile->decoder}) {
        const auto hash=sha256(image.read(span.rva,span.size,true));
        if(!std::equal(hash.begin(),hash.end(),span.sha))throw std::runtime_error("native opcode177/decoder body changed; install before scroll decoder carrier");
    }
    return {reinterpret_cast<CBMS_LinkedApply>(image.address(profile->parent.rva)),reinterpret_cast<CBMS_LinkedDecode>(image.address(profile->decoder.rva)),image.address(profile->call)};
}
int install(const CBMS_LinkedFunctions& functions,CBMS_Runtime* runtime) {
    const unsigned char prefix[]{0x48,0x89,0x5C,0x24,0x18},unwind[]{1,5,2,0,5,0x34,3,0},leaf[]{1,0,0,0};
    std::array<unsigned char,5> call{0xE8};const auto delta=static_cast<int64_t>(reinterpret_cast<uintptr_t>(functions.decode))-static_cast<int64_t>(functions.call_site+5);
    if(delta<INT32_MIN||delta>INT32_MAX)throw std::runtime_error("opcode177 native decoder target exceeds CALL range");
    const auto relative=static_cast<int32_t>(delta);std::memcpy(call.data()+1,&relative,4);
    const std::array<cbm::scroll::hooks::Entry,2> entries{{
        {reinterpret_cast<uintptr_t>(functions.apply),reinterpret_cast<uintptr_t>(CBMS_Linked177Apply),prefix,unwind,false},
        {functions.call_site,reinterpret_cast<uintptr_t>(CBMS_Linked177Decode),call,leaf,false,true}}};
    group.install(entries,[&](std::span<const uintptr_t> trampolines){auto f=functions;f.apply=reinterpret_cast<CBMS_LinkedApply>(trampolines[0]);f.decode=reinterpret_cast<CBMS_LinkedDecode>(trampolines[1]);return CBMS_ConfigureLinked177(runtime,&f)==1;},
        []{return CBMS_DetachLinked177()==1;},[]{return CBMS_Linked177Idle()==1;});error.fill(0);return 1;
}
}
int CBMS_BindLinked177(uintptr_t game,CBMS_LinkedFunctions* out,char* text,uint32_t capacity) {
    if(!out||!text||capacity<2)return 0;
    auto report=[&](const char* value){const auto n=(std::min)(std::strlen(value),std::size_t(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try{const auto f=bind(game);*out=f;report("certified opcode177 parent and its one decoded-child edge");return 1;}
    catch(const std::exception& e){report(e.what());}catch(...){report("unexpected opcode177 binding failure");}return 0;
}
int CBMS_InstallLinked177Hooks(uintptr_t game,CBMS_Runtime* runtime){try{return install(bind(game),runtime);}catch(const std::exception& e){fail(e.what());}catch(...){fail("opcode177 installation failure");}return 0;}
int CBMS_RemoveLinked177Hooks(){try{group.remove();error.fill(0);return 1;}catch(const std::exception& e){fail(e.what());}catch(...){fail("opcode177 removal failure");}return 0;}
const char* CBMS_Linked177HookError(){return error.data();}
extern "C" int CBMS_Linked177HooksPresent(){return group.present()?1:0;}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestInstallLinked177Hooks(const CBMS_LinkedFunctions* f,CBMS_Runtime* runtime){try{if(!f)throw std::invalid_argument("null opcode177 fixture functions");return install(*f,runtime);}catch(const std::exception& e){fail(e.what());}catch(...){fail("opcode177 fixture installation failure");}return 0;}
uintptr_t CBMS_TestLinked177Allocation(){return group.allocation();}
void CBMS_TestLinked177Failure(int point){group.inject_failure(point);}
#endif
