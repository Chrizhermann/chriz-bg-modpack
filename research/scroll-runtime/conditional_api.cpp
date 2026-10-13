#include "conditional_api.h"
#include "cast_carrier_api.h"
#include <algorithm>
#include <array>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <intrin.h>
namespace {
CBMS_Runtime* runtime{};CBMS_ConditionalFunctions native{};std::thread::id owner;unsigned busy{};
std::array<char,256> fault{};
struct Pending{uintptr_t effect{},caller{};void* receiver{};}pending;
void fail(const char* why)noexcept{if(fault[0])return;const auto n=(std::min)(std::strlen(why),fault.size()-1);std::memcpy(fault.data(),why,n);fault[n]=0;}
bool check(int value)noexcept{if(value>=0)return true;fail(CBMS_LastError(runtime));return false;}
struct Guard{Guard(){if(!runtime||owner!=std::this_thread::get_id())throw std::logic_error("conditional carrier lacks owner thread");++busy;}~Guard(){--busy;}};
struct Update;Update* current{};
struct Update{
 Guard guard;Update* previous{current};uintptr_t effect{};bool owned{};
 explicit Update(void* self){current=this;std::memcpy(&effect,static_cast<unsigned char*>(self)+0x38,8);
  if(!fault[0]){const auto value=CBMS_CarrierIsOwned(runtime,1,effect);if(check(value))owned=value==1;}}
 ~Update(){current=previous;}
};
void* decoded(uintptr_t caller,const void* raw){
 Guard guard;auto* parent=current;const bool attach=parent&&parent->owned&&caller==native.decode_call+5;
 auto* result=native.decode(raw);
 if(!fault[0]&&attach&&result){uint32_t level{};const auto value=CBMS_Linked177Observed(runtime,parent->effect,reinterpret_cast<uintptr_t>(result),&level);if(check(value)&&value==1)std::memcpy(static_cast<unsigned char*>(result)+0xC8,&level,4);}
 return result;
}
}
int CBMS_ConfigureConditional(CBMS_Runtime* value,const CBMS_ConditionalFunctions* f){
 if(runtime||!value||!f||!f->update||!f->decode||!f->decode_call||!f->fire326_return)return 0;
 for(unsigned i=0;i<10;++i)if(!f->calls[i]||!f->targets[i])return 0;
 runtime=value;native=*f;owner=std::this_thread::get_id();fault.fill(0);CBMS_SetAdditionalCastOwner(CBMS_ConditionalOwnerAt);return 1;
}
int CBMS_ConditionalIdle(){return runtime&&owner==std::this_thread::get_id()&&!busy&&!current&&!pending.effect?1:0;}
int CBMS_DetachConditional(){if(!CBMS_ConditionalIdle())return 0;CBMS_SetAdditionalCastOwner(nullptr);runtime=nullptr;native={};return 1;}
const char* CBMS_ConditionalError(){return fault.data();}
void CBMS_RepeatingCarrier(void* self,void* target,int elapsed)noexcept(false){Update scope(self);native.update(self,target,elapsed);}
void* CBMS_RepeatingDecodeCarrier(const void* raw)noexcept(false){return decoded(reinterpret_cast<uintptr_t>(_ReturnAddress()),raw);}
void CBMS_ConditionalBefore(uint32_t index,uintptr_t* snapshot){
 if(!runtime||owner!=std::this_thread::get_id()||!snapshot||index>=10)return;
 if(snapshot[16]!=native.calls[index]+5){fail("conditional CALL identity mismatch");return;}
 if(index<6){
  if(pending.effect){fail("unconsumed conditional cast context");return;}
  // Both native contingency loops hold the active CContingency in RSI.
  pending={snapshot[10]+0x78,snapshot[16],reinterpret_cast<void*>(snapshot[14])};
 }else{
  // All four actual embedded destructors call CSound with effect+0x130.
  if(snapshot[14]<0x130){fail("invalid contingency destructor member");return;}
  check(CBMS_DestructObserved(runtime,1,snapshot[14]-0x130));
 }
}
int CBMS_ConditionalOwnerAt(uint32_t selector,uintptr_t caller,void* receiver,uintptr_t* effect){
 if(!runtime||owner!=std::this_thread::get_id()||!effect)return 0;
 uintptr_t source{};
 if(selector==0&&caller==native.fire326_return)source=reinterpret_cast<uintptr_t>(receiver);
 else if(selector==1&&pending.effect){const auto held=pending;pending={};if(caller!=held.caller||receiver!=held.receiver){fail("contingency cast crossed its native boundary");return 0;}source=held.effect;}
 if(fault[0]||!source)return 0;
 const auto value=CBMS_CarrierIsOwned(runtime,1,source);if(!check(value)||!value)return 0;*effect=source;return 1;
}
#ifdef CBMS_OFFLINE_HARNESS
extern "C" CBMS_EXPORT void* CBMS_TestRepeatingDecode(uintptr_t pc,const void* raw){return decoded(pc,raw);}
#endif
