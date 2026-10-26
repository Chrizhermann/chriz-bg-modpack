#include "linked177_api.h"
#include "carrier_gate.hpp"
#include <algorithm>
#include <array>
#include <cstring>
#include <stdexcept>
#include <intrin.h>
namespace {
CBMS_Runtime* runtime{};CBMS_LinkedFunctions native{};cbm::scroll::CarrierGate gate;unsigned busy{};std::array<char,256> fault{};
using Outside=cbm::scroll::CarrierGate::Outside;
void fail(const char* value)noexcept{CBMS_DisableOverrides(runtime);if(fault[0])return;if(!value)value="unknown linked scroll failure";const auto n=(std::min)(std::strlen(value),fault.size()-1);std::memcpy(fault.data(),value,n);fault[n]=0;}
bool check(int value)noexcept{if(value>=0)return true;fail(CBMS_LastError(runtime));return false;}
// Checked before any carrier state: see carrier_gate.hpp.
bool admitted()noexcept{return gate.owner()&&runtime;}
struct Guard{Guard(){++busy;}~Guard(){--busy;}};
struct Applying;Applying* current{};
struct Applying {
    Guard guard;Applying* parent{current};void* effect;bool owned{};
    explicit Applying(void* value):effect(value){
        current=this;
        if(!fault[0]){const auto result=CBMS_CarrierIsOwned(runtime,1,reinterpret_cast<uintptr_t>(effect));if(check(result))owned=result==1;}
        if(owned){uint32_t opcode{};std::memcpy(&opcode,static_cast<unsigned char*>(effect)+0x10,4);if(opcode!=177){owned=false;fail("owned linked effect disagrees with native opcode177 class");}}
    }
    ~Applying(){current=parent;}
};
void* decode(uintptr_t caller,const void* raw) {
    if(!admitted()){Outside outside(gate);return native.decode(raw);}
    Guard guard;auto* parent=current;
    const bool attributed=parent&&parent->owned&&caller==native.call_site+5;
    auto* result=native.decode(raw);
    if(!fault[0]&&attributed&&result){
        if(current!=parent)fail("linked decoder returned across a broken parent scope");
        else{uint32_t level{};const auto status=CBMS_Linked177Observed(runtime,reinterpret_cast<uintptr_t>(parent->effect),reinterpret_cast<uintptr_t>(result),&level);
            if(check(status)&&status==1)std::memcpy(static_cast<unsigned char*>(result)+0xC8,&level,4);}
    }
    return result;
}
}
int CBMS_ConfigureLinked177(CBMS_Runtime* value,const CBMS_LinkedFunctions* f){
    if(runtime||!value||!f||!f->apply||!f->decode||!f->call_site||f->apply==CBMS_Linked177Apply||f->decode==CBMS_Linked177Decode)return 0;
    runtime=value;native=*f;gate.configure();fault.fill(0);return 1;
}
int CBMS_Linked177Idle(){return admitted()&&!busy&&!current&&gate.quiet()?1:0;}
int CBMS_DetachLinked177(){if(!CBMS_Linked177Idle())return 0;runtime=nullptr;native={};return 1;}
const char* CBMS_Linked177Error(){return fault.data();}
int CBMS_Linked177Apply(void* effect,void* target)noexcept(false){
    if(!admitted()){Outside outside(gate);return native.apply(effect,target);}
    Applying scope(effect);return native.apply(effect,target);
}
void* CBMS_Linked177Decode(const void* raw)noexcept(false){return decode(reinterpret_cast<uintptr_t>(_ReturnAddress()),raw);}
#ifdef CBMS_OFFLINE_HARNESS
void* CBMS_TestLinked177Decode(uintptr_t pc,const void* raw)noexcept(false){return decode(pc,raw);}
#endif
