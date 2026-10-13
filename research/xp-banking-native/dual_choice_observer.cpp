#include "dual_choice_observer.h"
#include <atomic>
#include <cstring>
#include <deque>
#include <limits>
namespace {
std::atomic<uint64_t> identities{1},owner{0};
std::atomic<bool> ready{false},fault{false};
CBMDC_Config config{};
std::deque<CBMDC_Event> events;
uint64_t sequence=0;
bool busy=false;
uintptr_t sink=0;
uint64_t self(){thread_local const auto id=identities.fetch_add(1);return id;}
bool host(){return ready.load()&&owner.load()==self();}
void capture(bool inactive,void* sprite,uint32_t stat,int32_t pips,int immediate,void* screen) {
    if(!ready.load())return; // No installed thunk may call an unconfigured binding.
    using Setter=void(*)(void*,uint32_t,int32_t,int);
    using Getter=int32_t(*)(void*,uint32_t);
    const auto setter=reinterpret_cast<Setter>(inactive?config.set_inactive:config.set_active);
    const auto getter=reinterpret_cast<Getter>(inactive?config.get_inactive:config.get_active);
    if(!host()||busy){fault=true;setter(sprite,stat,pips,immediate);return;}
    busy=true;
    CBMDC_Event event{};bool staged=false;
    try {
        if(sequence==std::numeric_limits<uint64_t>::max()){fault=true;}
        else event.sequence=++sequence;
        event.sprite=reinterpret_cast<uintptr_t>(sprite);event.screen=reinterpret_cast<uintptr_t>(screen);
        event.stat=stat;event.inactive=inactive?1u:0u;event.requested=pips;event.status=2;
        std::memcpy(&event.screen_mode,static_cast<unsigned char*>(screen)+0x768,4);
        event.screen_selected_class=*(static_cast<unsigned char*>(screen)+0xa0c);
        event.before=getter(sprite,stat);
        try{events.push_back(event);staged=true;}catch(...){fault=true;}
        // This is the original accepted +/- choice once, with all native args.
        // No global setter detour: item/mod/CLAB changes elsewhere are excluded.
        setter(sprite,stat,pips,immediate);
        if(staged){events.back().after=getter(sprite,stat);events.back().status=1;
            if(sink && reinterpret_cast<int(*)(const CBMDC_Event*)>(sink)(&events.back()))events.pop_back();}
        busy=false;
    } catch(...) {
        fault=true;busy=false;throw; // Retain staged uncertain event, no rollback.
    }
}
}
int CBMDC_Configure(const CBMDC_Config* in){
    if(!in||in->abi!=1||!in->set_active||!in->set_inactive||!in->get_active||!in->get_inactive)return 0;
    uint64_t empty=0;if(!owner.compare_exchange_strong(empty,self()))return 0;
    config=*in;ready=true;return 1;
}
void CBMDC_Active(void* s,uint32_t stat,int32_t p,int immediate,void* screen){capture(false,s,stat,p,immediate,screen);}
void CBMDC_Inactive(void* s,uint32_t stat,int32_t p,int immediate,void* screen){capture(true,s,stat,p,immediate,screen);}
int CBMDC_Peek(CBMDC_Event* out){if(!host()||busy||!out||events.empty())return 0;*out=events.front();return 1;}
int CBMDC_Acknowledge(uint64_t n){if(!host()||busy||events.empty()||events.front().sequence!=n)return 0;events.pop_front();return 1;}
int CBMDC_Faulted(){return !host()||fault.load()?1:0;}
int CBMDC_SetSink(uintptr_t target){if(!host()||busy||!events.empty()||sink||!target)return 0;sink=target;return 1;}
