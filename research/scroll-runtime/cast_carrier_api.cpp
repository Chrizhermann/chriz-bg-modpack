#include "cast_carrier_api.h"
#include "dispatch_carrier_api.h"
#include "carrier_gate.hpp"
#include <algorithm>
#include <array>
#include <cstring>
#include <stdexcept>
#include <intrin.h>
namespace {
CBMS_Runtime* runtime{};CBMS_CastFunctions native{};cbm::scroll::CarrierGate gate;unsigned busy{};std::array<char,256> fault{};
CBMS_AdditionalCastOwner additional_owner{};
using Outside=cbm::scroll::CarrierGate::Outside;
void fail(const char* value) noexcept {
    CBMS_DisableOverrides(runtime); // this group's first fault disables every override
    if(fault[0])return;if(!value)value="unknown native scroll cast failure";
    const auto n=(std::min)(std::strlen(value),fault.size()-1);std::memcpy(fault.data(),value,n);fault[n]=0;
}
bool check(int value) noexcept {if(value>=0)return true;fail(CBMS_LastError(runtime));return false;}
template<class F> void safely(F&& body) noexcept {
    if(fault[0])return;try{body();}catch(const std::exception& error){fail(error.what());}catch(...){fail("unexpected native cast carrier failure");}
}
template<class T> T read(const void* base,std::size_t offset) {T out;std::memcpy(&out,static_cast<const unsigned char*>(base)+offset,sizeof out);return out;}
template<class T> void write(void* base,std::size_t offset,T value) {std::memcpy(static_cast<unsigned char*>(base)+offset,&value,sizeof value);}
// Checked before any carrier state: see carrier_gate.hpp.
bool admitted() noexcept {return gate.owner()&&runtime;}
struct Guard {
    Guard(){++busy;}
    ~Guard(){--busy;}
};
struct Invocation;Invocation* current{};
struct Invocation {
    Guard guard;Invocation* parent{current};uint32_t selector;void* receiver;uint64_t capture{},frame{};void* instance{};
    bool owned{},selected{},overridden{};uint32_t level{};
    Invocation(uint32_t s,uintptr_t caller,void* r):selector(s),receiver(r) {
        current=this; // Also masks parents on every unowned/reentrant path.
        safely([&]{
            int result;
            const bool continuation=parent&&parent->capture&&parent->receiver==r&&
                ((s==1&&parent->selector==5&&caller==native.extra_returns[0])||
                 (s==2&&parent->selector==6&&caller==native.extra_returns[1]));
            if(continuation)result=CBMS_ContinueCastOwner(runtime,parent->capture,s,&capture);
            else {
                uint32_t kind=1;uintptr_t carrier{};
                if(s<3){if(!additional_owner||!additional_owner(s,caller,r,&carrier))(void)CBMS_DispatchOwnerAt(s,caller,r,&kind,&carrier);}
                else if(r) {
                    // The receiver's m_curAction (+3F8h) is the action these
                    // entries execute; its m_source (+80h) CString carries
                    // ownership by value through every native (often inline) copy.
                    uintptr_t witness{};
                    const auto found=CBMS_ActionWitnessCarrier(runtime,read<uintptr_t>(r,0x3F8+0x80),&witness);if(!check(found))return;
                    if(found){kind=3;carrier=witness;}
                }
                result=CBMS_CaptureCastOwner(runtime,kind,carrier,s,&capture);
            }
            if(check(result))owned=result==1;
        });
    }
    ~Invocation() noexcept {
        // Cleanup remains active after a fault and during a native exception.
        if(frame)check(CBMS_EndCast(runtime,frame));
        if(capture)check(CBMS_ReleaseCastOwner(runtime,capture));
        current=parent;
        // A nested cast on the same sprite can overwrite the shared native
        // working level. Restore only an owned outer Spell/Point scalar.
        if(parent&&parent->receiver==receiver&&parent->selector>=5&&parent->overridden)
            write<uint16_t>(receiver,0x4C8A,static_cast<uint16_t>(parent->level));
    }
};
uint32_t installed_type(void* spell) {
    const auto type=static_cast<unsigned>(native.caster_type(spell));
    if(type==1)return 0;if(type==2)return 1;if(type>=3&&type<=5)return 3;
    if(type==0&&read<uint8_t>(spell,8)) {
        const auto resource=read<void*>(spell,0);const auto header=resource?read<void*>(resource,0x68):nullptr;
        if(header&&std::memcmp(header,"SPL V1  ",8)==0&&read<uint16_t>(header,0x1C)==0)return 3;
    }
    throw std::logic_error("installed spell type is missing, malformed, or unsupported");
}
// Every entry: a foreign call runs only the original, with its arguments.
template<class Original,class... Arguments>
auto entry(uint32_t selector,uintptr_t caller,void* self,Original original,Arguments... arguments) {
    if(!admitted()){Outside outside(gate);return original(self,arguments...);}
    Invocation call(selector,caller,self);return original(self,arguments...);
}
void effect_fire(uintptr_t caller,void* self,void* spell,void* target,int flags,int level,int source) {
    entry(0,caller,self,native.effect_fire,spell,target,flags,level,source);
}
int16_t fire(uint32_t path,uintptr_t caller,void* self,void* spell,void* target,int flags,int source,void* modifiers,int a,int b) {
    return entry(path,caller,self,path==1?native.fire:native.fire_point,spell,target,flags,source,modifiers,a,b);
}
void* child(uintptr_t caller,void* spell,int ability,int index,void* caster) {
    if(!admitted()){Outside outside(gate);return native.child(spell,ability,index,caster);}
    Guard guard;auto* invocation=current;
    // Capture before original callbacks; a nested invocation must unwind before
    // this exact GetAbilityEffect returns. Do not attach by resource name.
    const bool attributed=invocation&&invocation->owned&&invocation->frame&&invocation->instance==spell&&
        caller==native.child_returns[invocation->selector];
    void* result=native.child(spell,ability,index,caster);
    safely([&]{
        if(!result||!attributed)return;
        if(current!=invocation)throw std::logic_error("native child returned across a broken cast scope");
        uint32_t level{};const auto status=CBMS_SpellChildObserved(runtime,invocation->frame,reinterpret_cast<uintptr_t>(spell),reinterpret_cast<uintptr_t>(result),&level);
        if(!check(status))return;if(status==1)write<uint32_t>(result,0xC8,level);
    });
    return result;
}
}
int CBMS_ConfigureCastCarriers(CBMS_Runtime* value,const CBMS_CastFunctions* functions) {
    if(runtime||!value||!functions)return 0;const auto& f=*functions;
    if(!f.effect_fire||!f.fire||!f.fire_point||!f.force||!f.force_point||!f.spell||!f.spell_point||!f.child||!f.caster_type||!f.count_getter||
       f.effect_fire==CBMS_EffectFireCarrier||f.fire==CBMS_FireCarrier||f.fire_point==CBMS_FirePointCarrier||f.force==CBMS_ForceCarrier||
       f.force_point==CBMS_ForcePointCarrier||f.spell==CBMS_SpellCarrier||f.spell_point==CBMS_SpellPointCarrier||f.child==CBMS_SpellEffectCarrier)return 0;
    for(unsigned i=0;i<7;++i)if(!f.selection_calls[i]||!f.child_returns[i])return 0;
    if(!f.extra_returns[0]||!f.extra_returns[1])return 0;
    native=f;runtime=value;gate.configure();fault.fill(0);return 1;
}
int CBMS_CastCarriersIdle(){return admitted()&&!busy&&!current&&gate.quiet()?1:0;}
int CBMS_DetachCastCarriers(){if(!CBMS_CastCarriersIdle())return 0;runtime=nullptr;native={};return 1;}
const char* CBMS_CastCarrierError(){return fault.data();}
void CBMS_SetAdditionalCastOwner(CBMS_AdditionalCastOwner value){additional_owner=value;}
void CBMS_EffectFireCarrier(void* self,void* spell,void* target,int flags,int level,int source) noexcept(false){effect_fire(reinterpret_cast<uintptr_t>(_ReturnAddress()),self,spell,target,flags,level,source);}
int16_t CBMS_FireCarrier(void* self,void* spell,void* target,int flags,int source,void* modifiers,int a,int b) noexcept(false){return fire(1,reinterpret_cast<uintptr_t>(_ReturnAddress()),self,spell,target,flags,source,modifiers,a,b);}
int16_t CBMS_FirePointCarrier(void* self,void* spell,void* target,int flags,int source,void* modifiers,int a,int b) noexcept(false){return fire(2,reinterpret_cast<uintptr_t>(_ReturnAddress()),self,spell,target,flags,source,modifiers,a,b);}
int16_t CBMS_ForceCarrier(void* self,void* target) noexcept(false){return entry(3,0,self,native.force,target);}
int16_t CBMS_ForcePointCarrier(void* self) noexcept(false){return entry(4,0,self,native.force_point);}
int16_t CBMS_SpellCarrier(void* self,void* target) noexcept(false){return entry(5,0,self,native.spell,target);}
int16_t CBMS_SpellPointCarrier(void* self) noexcept(false){return entry(6,0,self,native.spell_point);}
void* CBMS_SpellEffectCarrier(void* spell,int ability,int index,void* caster) noexcept(false){return child(reinterpret_cast<uintptr_t>(_ReturnAddress()),spell,ability,index,caster);}
void CBMS_SelectCapturedNative(uint32_t path,uint64_t* saved) {
    // The bridge itself then calls the native getter with the saved registers.
    if(!admitted()){Outside outside(gate);return;}
    safely([&]{
        if(!saved||!current||path>6||current->selector!=path||saved[16]!=native.selection_calls[path]+5)
            throw std::logic_error("selector did not enter through its audited native CALL/frame");
        if(!current->owned)return;
        auto* spell=reinterpret_cast<void*>(saved[14]);if(!spell)throw std::logic_error("null native preselection CSpell");
        if(current->selected)throw std::logic_error("native preselection repeated inside one cast entry");
        const auto type=installed_type(spell);current->instance=spell;
        if(!check(CBMS_BeginCapturedCast(runtime,current->capture,reinterpret_cast<uintptr_t>(spell),static_cast<const char*>(spell)+8,type,&current->frame)))return;
        uint32_t level{};const auto status=CBMS_Select(runtime,current->frame,path,reinterpret_cast<uintptr_t>(spell),&level);
        if(!check(status))return;current->selected=true;if(status==0)return;
        // All seven downstream native loops consume signed16 levels except
        // EffectFire's explicit dword. Refuse truncation rather than wrap it.
        if(!level||level>32767)throw std::logic_error("reader caster level exceeds native signed16 selection range");
        current->level=level;current->overridden=true;
        auto* native_rsp=reinterpret_cast<unsigned char*>(saved+17);
        switch(path) {
        case 0:write<uint32_t>(reinterpret_cast<void*>(saved[11]),0x77,level);break;
        case 1:write<uint32_t>(native_rsp,0x58,level);break;
        case 2:saved[3]=level;write<uint32_t>(native_rsp,0x6C,level);break;
        case 3:saved[2]=level;break;
        case 4:saved[4]=level;break;
        case 5:case 6:
            if(saved[12]!=reinterpret_cast<uintptr_t>(current->receiver))throw std::logic_error("native Spell selector receiver changed");
            write<uint16_t>(current->receiver,0x4C8A,static_cast<uint16_t>(level));break;
        }
    });
}
#ifdef CBMS_OFFLINE_HARNESS
void CBMS_TestEffectFireCarrier(uintptr_t pc,void* self,void* spell,void* target,int flags,int level,int source) noexcept(false){effect_fire(pc,self,spell,target,flags,level,source);}
int16_t CBMS_TestFireCarrier(uint32_t path,uintptr_t pc,void* self,void* spell,void* target,int flags,int source,void* modifiers,int a,int b) noexcept(false){return fire(path,pc,self,spell,target,flags,source,modifiers,a,b);}
void* CBMS_TestSpellEffectCarrier(uintptr_t pc,void* spell,int ability,int index,void* caster) noexcept(false){return child(pc,spell,ability,index,caster);}
#endif
