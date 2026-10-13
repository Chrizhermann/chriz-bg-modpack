#include "lifecycle_carrier_api.h"
#include "eeex_save_bridge.h"
#include <stdexcept>
#include <thread>
namespace {
CBMS_EffectCopyOriginal copy_original{};
CBMS_DestroyOriginal effect_original{},actor_original{};
std::thread::id owner;
unsigned busy{};
struct Scope {
    Scope() {
        if(!copy_original||owner!=std::this_thread::get_id()) throw std::logic_error("native lifecycle carrier has no owner-thread setup");
        ++busy;
    }
    ~Scope() {--busy;}
};
}
int CBMS_ConfigureLifecycleCarriers(CBMS_EffectCopyOriginal copy,CBMS_DestroyOriginal effect,CBMS_DestroyOriginal actor) {
    if(copy_original||!copy||!effect||!actor||copy==CBMS_EffectCopyCarrier||effect==CBMS_EffectDestroyCarrier||actor==CBMS_ActorDestroyCarrier) return 0;
    copy_original=copy;effect_original=effect;actor_original=actor;owner=std::this_thread::get_id();return 1;
}
int CBMS_LifecycleCarriersIdle() {return copy_original&&owner==std::this_thread::get_id()&&!busy?1:0;}
int CBMS_DetachLifecycleCarriers() {
    if(!CBMS_LifecycleCarriersIdle()) return 0;
    copy_original=nullptr;effect_original=nullptr;actor_original=nullptr;return 1;
}
void CBMS_EffectCopyCarrier(void* from,void* to) noexcept(false) {
    Scope scope;copy_original(from,to);CBMS_EEexLiveEffectCopied(from,to);
}
void CBMS_EffectDestroyCarrier(void* effect) noexcept(false) {
    Scope scope;CBMS_EEexEffectDestroyed(effect);effect_original(effect);
}
void CBMS_ActorDestroyCarrier(void* actor) noexcept(false) {
    Scope scope;CBMS_EEexActorDestroyed(actor);actor_original(actor);
}
