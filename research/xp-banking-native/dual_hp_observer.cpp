#include "dual_hp_observer.h"
#include <atomic>
#include <cstring>
#include <limits>
namespace {
std::atomic<uint64_t> identities{1},owner{0};
uint64_t self() { thread_local const uint64_t id=identities.fetch_add(1);return id; }
bool host() { return owner.load()==self(); }
std::atomic<uintptr_t> original{0};
CBMDH_Batch current{},last{};
bool collecting=false,unread=false;
uint32_t serial=0;
uintptr_t sink=0;
void levels(const void* stats,uint16_t (&out)[3]) {
    // Same audited CDerivedStats layout on2.6/2.7; caller owns valid lifetimes.
    std::memcpy(out,static_cast<const unsigned char*>(stats)+0x46,sizeof(out));
}
}
int CBMDH_Configure(const CBMDH_Config* in) {
    if (!in || in->abi!=1 || !in->get_hit_points) return 0;
    uint64_t empty=0;
    if (!owner.compare_exchange_strong(empty,self())) return 0;
    original.store(in->get_hit_points);return 1;
}
int32_t CBMDH_Capture(void* rules,void* type,void* before,void* after,
    unsigned char constitution,void* actor) {
    using Native=int32_t(*)(void*,void*,void*,void*,unsigned char);
    // Foreign/reentrant observation never changes native HP behavior. It simply
    // cannot produce a complete usable receipt. Installation is engine-thread only.
    const auto native=original.load();
    if (!native) return 0; // Not installed/configured; no function to invoke.
    if (!host() || collecting) return reinterpret_cast<Native>(native)(rules,type,before,after,constitution);
    current={};current.abi=1;current.actor=reinterpret_cast<uintptr_t>(actor);
    current.status=unread ? 2u : 1u; // Never silently overwrite a missed batch.
    if (serial==std::numeric_limits<uint32_t>::max()) current.status=2;
    else ++serial;
    current.serial=serial;levels(before,current.before_levels);levels(after,current.after_levels);
    collecting=true;
    try {
        const auto result=reinterpret_cast<Native>(native)(rules,type,before,after,constitution);
        current.native_total=result;
        int64_t total=0;for(uint32_t i=0;i<current.count;++i)total+=current.samples[i].rolled_hp;
        // Existing duals use one active class's RollHitPoints sum. This check
        // honestly marks chargen/multiclass/special transformations unsupported.
        if (total!=result) current.status=2;
        collecting=false;
        if(sink && reinterpret_cast<int(*)(const CBMDH_Batch*)>(sink)(&current))return result;
        if (!unread) {last=current;unread=true;} else last.status=2;
        return result;
    } catch (...) {
        collecting=false;current.status=2;
        if (!unread) {last=current;unread=true;} else last.status=2;
        throw; // No invented rollback, swallowed native failure or extra RNG.
    }
}
void CBMDH_Record(uint32_t level,int32_t rolled_hp) noexcept {
    if (!host() || !collecting) return; // opcodes/chargen outside reviewed callsite
    if (!level || level>255 || rolled_hp<1 || current.count>=255
        || (current.count && current.samples[current.count-1].level>=level)) {
        current.status=2;return;
    }
    current.samples[current.count++]={level,rolled_hp};
}
int CBMDH_Peek(CBMDH_Batch* out) {
    if (!host() || collecting || !unread || !out)return 0;
    *out=last;return 1;
}
int CBMDH_Acknowledge(uint32_t expected) {
    if (!host() || collecting || !unread || expected!=last.serial)return 0;
    unread=false;return 1;
}
int CBMDH_SetSink(uintptr_t target){if(!host()||collecting||unread||sink||!target)return 0;sink=target;return 1;}
