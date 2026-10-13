#include "marshal_carrier_api.h"
#include "eeex_save_bridge.h"
#include <limits>
#include <stdexcept>
#include <thread>

namespace {
CBMS_NativeMarshalTrampoline original{};
std::thread::id owner;
unsigned busy{};
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
    original=function;owner=std::this_thread::get_id();return 1;
}
int CBMS_MarshalCarrierIdle() {return original&&std::this_thread::get_id()==owner&&!busy ? 1:0;}
int CBMS_DetachMarshalCarrier() {
    if(!CBMS_MarshalCarrierIdle()) return 0;
    original=nullptr;return 1;
}
int CBMS_ClaimMarshalActor(void* actor) {
    if(!original) return 0;
    if(std::this_thread::get_id()!=owner) {
        CBMS_EEexRejectEnvelope("native actor marshal exporter entered on another thread");return -1;
    }
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
    if(!original||std::this_thread::get_id()!=owner) throw std::logic_error("native Marshal carrier has no owner-thread configuration");
    Stack scope(list,output,version,permanent,skip);
    const auto size=original(list,output,version,permanent,skip);
    if(scope.value.actor) CBMS_EEexAfterEffectMarshal(scope.value.actor,size);
    return size;
}
