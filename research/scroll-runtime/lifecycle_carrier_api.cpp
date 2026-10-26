#include "lifecycle_carrier_api.h"
#include "eeex_save_bridge.h"
#include "carrier_gate.hpp"
namespace {
CBMS_EffectCopyOriginal copy_original{};
CBMS_DestroyOriginal effect_original{},actor_original{};
cbm::scroll::CarrierGate gate;
unsigned busy{};
using Outside=cbm::scroll::CarrierGate::Outside;
// Checked before any carrier state: see carrier_gate.hpp.
bool admitted() noexcept {return gate.owner()&&copy_original;}
struct Scope {
    Scope() {++busy;}
    ~Scope() {--busy;}
};
}
int CBMS_ConfigureLifecycleCarriers(CBMS_EffectCopyOriginal copy,CBMS_DestroyOriginal effect,CBMS_DestroyOriginal actor) {
    if(copy_original||!copy||!effect||!actor||copy==CBMS_EffectCopyCarrier||effect==CBMS_EffectDestroyCarrier||actor==CBMS_ActorDestroyCarrier) return 0;
    copy_original=copy;effect_original=effect;actor_original=actor;gate.configure();return 1;
}
int CBMS_LifecycleCarriersIdle() {return admitted()&&!busy&&gate.quiet()?1:0;}
int CBMS_DetachLifecycleCarriers() {
    if(!CBMS_LifecycleCarriersIdle()) return 0;
    copy_original=nullptr;effect_original=nullptr;actor_original=nullptr;return 1;
}
// An unrecorded copy or destruction elsewhere is why a foreign call disables
// every override: a stale registration could otherwise name a reused address.
void CBMS_EffectCopyCarrier(void* from,void* to) noexcept(false) {
    if(!admitted()){Outside outside(gate);copy_original(from,to);return;}
    Scope scope;copy_original(from,to);CBMS_EEexLiveEffectCopied(from,to);
}
void CBMS_EffectDestroyCarrier(void* effect) noexcept(false) {
    if(!admitted()){Outside outside(gate);effect_original(effect);return;}
    Scope scope;CBMS_EEexEffectDestroyed(effect);effect_original(effect);
}
void CBMS_ActorDestroyCarrier(void* actor) noexcept(false) {
    if(!admitted()){Outside outside(gate);actor_original(actor);return;}
    Scope scope;CBMS_EEexActorDestroyed(actor);actor_original(actor);
}
