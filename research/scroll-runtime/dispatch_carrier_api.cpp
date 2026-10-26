#include "dispatch_carrier_api.h"
#include "dispatch_binding.hpp"
#include "carrier_gate.hpp"
#include <algorithm>
#include <array>
#include <cstring>
#include <stdexcept>
#include <intrin.h>
namespace {
CBMS_Runtime* runtime{};CBMS_DispatchFunctions native{};cbm::scroll::CarrierGate gate;unsigned busy{};
std::array<char,256> fault{};
using Outside=cbm::scroll::CarrierGate::Outside;
void fail(const char* value) noexcept {
    CBMS_DisableOverrides(runtime); // e.g. a witness fault: queued casts keep native levels too
    if(fault[0])return;
    if(!value)value="unknown native scroll dispatch failure";
    const auto n=(std::min)(std::strlen(value),fault.size()-1);std::memcpy(fault.data(),value,n);fault[n]=0;
}
bool check(int result) noexcept {if(result==1)return true;fail(CBMS_LastError(runtime));return false;}
template<class F> void safely(F&& body) noexcept {
    if(fault[0])return;
    try {body();}catch(const std::exception& error){fail(error.what());}catch(...){fail("unexpected dispatch carrier failure");}
}
template<class T> T read(void* object,std::size_t offset) {T result;std::memcpy(&result,static_cast<unsigned char*>(object)+offset,sizeof result);return result;}
// Checked before any carrier state: see carrier_gate.hpp.
bool admitted() noexcept {return gate.owner()&&runtime;}
struct Guard {
    Guard(){++busy;}
    ~Guard(){--busy;}
};
struct Apply;
Apply* applying{};
struct Apply {
    Guard guard;Apply* parent{applying};void* effect;void* target;unsigned opcode,mode{},special{};bool owned{};
    // Owned mode0 only: the action this exact invocation constructed inside its
    // CMessageInsertAction (message+10h) at the audited constructor call.
    void* pending{};
    Apply(void* e,void* t,unsigned op):effect(e),target(t),opcode(op) {
        // Every call masks its parent, including unrelated reentrant effects.
        applying=this;
        safely([&]{
            const auto result=CBMS_CarrierIsOwned(runtime,1,reinterpret_cast<uintptr_t>(e));
            if(result<0){check(result);return;}owned=result==1;
            if(!owned)return;
            if(!e||read<uint32_t>(e,0x10)!=op)throw std::logic_error("owned dispatcher disagrees with native opcode class");
            mode=read<uint32_t>(e,0x20);special=read<uint32_t>(e,0x48);
            if(mode>2)throw std::logic_error("owned scroll dispatcher has unsupported mode");
        });
    }
    ~Apply(){applying=parent;}
};
struct Running;
Running* running{};
struct Running {
    Guard guard;Running* parent{running};void* message;
    explicit Running(void* value):message(value){running=this;}
    ~Running(){running=parent;}
};
// CAIAction lifetimes are not observed: 2.7.3.0 inlines most of their
// construction, copies and destruction. Ownership instead travels inside the
// action's own value (action_witness.hpp). This hook only identifies the one
// message action an owned mode0 dispatcher builds.
void* action_default(uintptr_t caller,void* action) {
    if(!admitted()){Outside outside(gate);return native.action_default(action);}
    Guard guard;
    void* result=native.action_default(action);
    if(result!=action||!result)fail("native default action constructor did not return its destination");
    safely([&]{
        if(!applying||!applying->owned||applying->mode!=0)return;
        const auto index=applying->opcode==146?0u:1u;
        if(caller!=native.action_default_returns[index])return;
        if(applying->pending)throw std::logic_error("owned mode0 dispatcher constructed its message action twice");
        applying->pending=action;
    });
    return result;
}
int16_t add_message(uintptr_t caller,void* handler,void* message,int force) {
    if(!admitted()){Outside outside(gate);return native.add_message(handler,message,force);}
    Guard guard;
    safely([&]{
        if(!message||!applying||!applying->owned)return;
        if(applying->mode==0) {
            // EEex's mode0 route calls AddMessage from its own cave, after its
            // SpellNoDec swap, so the identity is the constructed message itself.
            if(!applying->pending||static_cast<unsigned char*>(applying->pending)-0x10!=message)return;
            applying->pending=nullptr;
            if(read<uintptr_t>(message,0)!=native.insert_vtable)throw std::logic_error("owned mode0 dispatcher queued another message class");
            const auto field=reinterpret_cast<uintptr_t>(message)+0x10+0x80;
            // 0: overrides were disabled meanwhile; the action stays native.
            if(const auto stamped=CBMS_StampActionWitness(runtime,reinterpret_cast<uintptr_t>(applying->effect),applying->opcode,0,
                applying->special,field,*reinterpret_cast<const uintptr_t*>(native.empty_string));stamped<0)check(stamped);
            return;
        }
        if(applying->opcode!=146||applying->mode!=1||caller!=native.fire_add_return)return;
        if(read<uintptr_t>(message,0)!=native.fire_vtable)throw std::logic_error("native FireSpell message producer returned another message class");
        if(!check(CBMS_Construct(runtime,2,reinterpret_cast<uintptr_t>(message))))return;
        check(CBMS_Dispatch(runtime,reinterpret_cast<uintptr_t>(applying->effect),146,1,applying->special,2,reinterpret_cast<uintptr_t>(message)));
    });
    // AddMessage owns native scheduling/cancellation. Its return alone does not
    // prove destruction; only the actual deleting destructor erases ownership.
    return native.add_message(handler,message,force);
}
}
int CBMS_BindDispatchModule(uintptr_t game,CBMS_DispatchFunctions* output,char* text,uint32_t capacity) {
    if(!output||!text||capacity<2)return 0;
    auto diagnostic=[&](const char* value){const auto n=(std::min)(std::strlen(value),std::size_t(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try {std::string message;const auto result=cbm::scroll::binding::bind_dispatch(game,message);*output=result;diagnostic(message.c_str());return 1;}
    catch(const std::exception& error){diagnostic(error.what());return 0;}catch(...){diagnostic("unexpected dispatch binding failure");return 0;}
}
int CBMS_ConfigureDispatchCarriers(CBMS_Runtime* value,const CBMS_DispatchFunctions* functions) {
    if(runtime||!value||!functions)return 0;
    const auto& f=*functions;
    if(!f.apply146||!f.apply148||!f.action_default||!f.add_message||!f.fire_run||!f.fire_destroy||
       !f.action_default_returns[0]||!f.action_default_returns[1]||!f.fire_add_return||!f.fire_run_return||
       !f.effect_fire_return||!f.point_fire_return||!f.fire_vtable||!f.insert_vtable||!f.empty_string||
       f.apply146==CBMS_Apply146Carrier||f.apply148==CBMS_Apply148Carrier||f.action_default==CBMS_ActionDefaultCarrier||
       f.add_message==CBMS_AddMessageCarrier||f.fire_run==CBMS_FireMessageRunCarrier||f.fire_destroy==CBMS_FireMessageDestroyCarrier)return 0;
    native=f;runtime=value;gate.configure();fault.fill(0);return 1;
}
int CBMS_DispatchCarriersIdle(){return admitted()&&!busy&&!applying&&!running&&gate.quiet()?1:0;}
int CBMS_DetachDispatchCarriers(){if(!CBMS_DispatchCarriersIdle())return 0;runtime=nullptr;native={};return 1;}
const char* CBMS_DispatchCarrierError(){return fault.data();}
int CBMS_Apply146Carrier(void* effect,void* target) noexcept(false){
    if(!admitted()){Outside outside(gate);return native.apply146(effect,target);}
    Apply scope(effect,target,146);return native.apply146(effect,target);
}
int CBMS_Apply148Carrier(void* effect,void* target) noexcept(false){
    if(!admitted()){Outside outside(gate);return native.apply148(effect,target);}
    Apply scope(effect,target,148);return native.apply148(effect,target);
}
void* CBMS_ActionDefaultCarrier(void* action) noexcept(false){return action_default(reinterpret_cast<uintptr_t>(_ReturnAddress()),action);}
int16_t CBMS_AddMessageCarrier(void* handler,void* message,int force) noexcept(false){return add_message(reinterpret_cast<uintptr_t>(_ReturnAddress()),handler,message,force);}
void CBMS_FireMessageRunCarrier(void* message) noexcept(false){
    if(!admitted()){Outside outside(gate);native.fire_run(message);return;}
    Running scope(message);native.fire_run(message);
}
void* CBMS_FireMessageDestroyCarrier(void* message,uint32_t flags) noexcept(false){
    if(!admitted()){Outside outside(gate);return native.fire_destroy(message,flags);}
    Guard guard;check(CBMS_DestructObserved(runtime,2,reinterpret_cast<uintptr_t>(message)));return native.fire_destroy(message,flags);
}
int CBMS_DispatchOwnerAt(uint32_t selector,uintptr_t caller,void* receiver,uint32_t* kind,uintptr_t* carrier) {
    if(!admitted()||fault[0]||!kind||!carrier)return 0;
    void* source{};uint32_t type=1;
    if(selector==0&&applying&&applying->owned&&applying->opcode==146&&applying->mode==2&&
       caller==native.effect_fire_return&&receiver==applying->effect)source=applying->effect;
    else if(selector==2&&applying&&applying->owned&&applying->opcode==148&&applying->mode>0&&
            caller==native.point_fire_return&&receiver==applying->target)source=applying->effect;
    else if(selector==1&&running&&caller==native.fire_run_return){source=running->message;type=2;}
    if(!source)return 0;
    const auto owned=CBMS_CarrierIsOwned(runtime,type,reinterpret_cast<uintptr_t>(source));
    if(owned<0){check(owned);return 0;}if(!owned)return 0;
    *kind=type;*carrier=reinterpret_cast<uintptr_t>(source);return 1;
}
#ifdef CBMS_OFFLINE_HARNESS
void* CBMS_TestActionDefaultCarrier(uintptr_t caller,void* action) noexcept(false){return action_default(caller,action);}
int16_t CBMS_TestAddMessageCarrier(uintptr_t caller,void* handler,void* message,int force) noexcept(false){return add_message(caller,handler,message,force);}
#endif
