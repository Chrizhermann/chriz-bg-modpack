#include "party_native.h"
#include <atomic>
#include <thread>
namespace {
CBMP_Config config{};
bool configured=false;
std::thread::id host;
std::atomic<int> status{0};
}
int CBMP_Configure(const CBMP_Config* in) {
    if(configured||!in||in->abi!=1||!in->original_get_name_ref||!in->protected_callback)return 0;
    config=*in;host=std::this_thread::get_id();configured=true;return 1;
}
uint32_t CBMP_OnPartyReady(void* sprite) {
    if(!configured){status=2;return 0;} // Cannot occur through the configured loader.
    // The original getter is always executed exactly once, even on an unexpected
    // thread. The scoped patch targets only party insertion, not all GetNameRef.
    auto result=reinterpret_cast<uint32_t(*)(void*)>(config.original_get_name_ref)(sprite);
    if(std::this_thread::get_id()!=host){status=2;return result;}
    try {
        status=reinterpret_cast<int(*)(void*,unsigned char)>(config.protected_callback)(sprite,0)?1:3;
    }catch(...){status=3;} // Getter result and completed native party join survive.
    return result;
}
int CBMP_LastStatus(){return status.load();}
