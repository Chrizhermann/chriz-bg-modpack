#include "marshal_carrier_api.h"
#include "eeex_save_bridge.h"
#include "carrier_gate.hpp"
#include <limits>
#include <stdexcept>

namespace {
CBMS_NativeMarshalTrampoline original{};
cbm::scroll::CarrierGate gate;
unsigned busy{};
using Outside=cbm::scroll::CarrierGate::Outside;
// Checked before any carrier state: see carrier_gate.hpp.
bool admitted() noexcept {return gate.owner()&&original;}
struct Scope {
    void* list;void** output;uint8_t version;int permanent,skip;
    void* actor{};Scope* parent{};
};
Scope* top{};
struct Stack {
    Scope value;
    Stack(void* list,void** output,uint8_t version,int permanent,int skip):value{list,output,version,permanent,skip,nullptr,top} {
        top=&value;++busy;
    }
    ~Stack() {top=value.parent;--busy;}
};
}
int CBMS_ConfigureMarshalCarrier(CBMS_NativeMarshalTrampoline function) {
    if(original||!function||function==CBMS_MarshalCarrier) return 0;
    original=function;gate.configure();return 1;
}
int CBMS_MarshalCarrierIdle() {return admitted()&&!busy&&gate.quiet() ? 1:0;}
int CBMS_DetachMarshalCarrier() {
    if(!CBMS_MarshalCarrierIdle()) return 0;
    original=nullptr;return 1;
}
int CBMS_ClaimMarshalActor(void* actor) {
    if(!gate.owner()) {
        // Nothing here may be touched from another thread, not even the bridge.
        if(original) CBMS_ForeignEntry();
        return original?-1:0;
    }
    if(!original) return 0;
    if(!top) return 0;
    const auto address=reinterpret_cast<uintptr_t>(actor);
    // Both supported native CRE Marshal bodies pass this exact timed-effect
    // member. The actual exporter supplies actor; this only checks the pairing.
    if(!actor||address>UINTPTR_MAX-0x4A00||reinterpret_cast<uintptr_t>(top->list)!=address+0x4A00||
       !top->output||top->version!=1||(top->actor&&top->actor!=actor)) {
        CBMS_EEexRejectEnvelope("EEex actor exporter does not match the active native V1 timed-effect marshal");return -1;
    }
    if(!top->actor) {
        top->actor=actor;
        CBMS_EEexBeforeEffectMarshal(actor,top->list,top->output,
            (top->permanent?1u:0u)|(top->skip?2u:0u));
    }
    return CBMS_EEexBridgeHealthy()?1:-1;
}
uint32_t CBMS_MarshalCarrier(void* list,void** output,uint8_t version,int permanent,int skip) noexcept(false) {
    if(!admitted()) {Outside outside(gate);return original(list,output,version,permanent,skip);}
    Stack scope(list,output,version,permanent,skip);
    const auto size=original(list,output,version,permanent,skip);
    if(scope.value.actor) CBMS_EEexAfterEffectMarshal(scope.value.actor,size);
    return size;
}
