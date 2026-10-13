#include "action_carrier_api.h"
#include "action_binding.hpp"
#include <thread>
namespace {
CBMS_Runtime* runtime{};std::thread::id owner;unsigned busy{};
std::array<char,256> fault{};
void fail(const char* value)noexcept {
    if(fault[0])return;if(!value)value="unknown action lifecycle failure";
    const auto n=(std::min)(std::strlen(value),fault.size()-1);std::memcpy(fault.data(),value,n);fault[n]=0;
}
template<class F> int invoke(CBMS_Runtime* value,F&& callback)noexcept {
    if(!value||value!=runtime||owner!=std::this_thread::get_id()) {
        fail("action lifecycle callback lacks its owner-thread runtime");return -1;
    }
    struct Guard {Guard(){++busy;}~Guard(){--busy;}} guard;
    try {const auto result=callback();if(result!=1)fail(CBMS_LastError(value));return result;}
    catch(const std::exception& issue){fail(issue.what());}catch(...){fail("unexpected action lifecycle failure");}
    return -1;
}
}
int CBMS_BindActionModule(uintptr_t game,CBMS_ActionFunctions* output,char* text,uint32_t capacity) {
    if(!output||!text||capacity<2)return 0;
    auto diagnostic=[&](const char* value){const auto n=(std::min)(std::strlen(value),std::size_t(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try {std::string message;const auto result=cbm::scroll::binding::bind_action(game,message);*output=result;diagnostic(message.c_str());return 1;}
    catch(const std::exception& issue){diagnostic(issue.what());}catch(...){diagnostic("unexpected action binding failure");}return 0;
}
int CBMS_ConfigureActionCarriers(CBMS_Runtime* value) {
    if(runtime||!value)return 0;runtime=value;owner=std::this_thread::get_id();fault.fill(0);return 1;
}
int CBMS_ActionCarriersIdle(){return runtime&&owner==std::this_thread::get_id()&&!busy?1:0;}
int CBMS_DetachActionCarriers(){if(!CBMS_ActionCarriersIdle())return 0;runtime=nullptr;return 1;}
const char* CBMS_ActionCarrierError(){return fault.data();}
int CBMS_ActionCopiedCarrier(CBMS_Runtime* value,uintptr_t source,uintptr_t destination,uint32_t construction) {
    return invoke(value,[&]{return CBMS_ActionCopied(value,source,destination,construction);});
}
int CBMS_ActionDestroyCarrier(CBMS_Runtime* value,uintptr_t action) {
    return invoke(value,[&]{return CBMS_ActionBeforeDestroy(value,action);});
}
