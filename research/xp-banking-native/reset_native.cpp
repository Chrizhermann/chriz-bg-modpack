// This bridge calls actual MakeDualClass/GetXPCap functions, connected by the
// reviewed entry loader. Native exceptions are rethrown with recovery state kept.
#include "reset_native.h"
#include <charconv>
#include <cstring>
#include <thread>
#include <unordered_map>
namespace {
CBMR_Config config{};
bool configured=false;
std::thread::id host;
struct Record : CBMR_View { void* screen=nullptr; bool removed=false; };
std::unordered_map<const void*,Record> records;
std::unordered_map<const void*,CBMR_PreviewView> previews;
using Callback = int(*)(void*,unsigned char);
bool on_host() { return configured && std::this_thread::get_id()==host; }
void uncertain(void* sprite,unsigned char cls) {
    // Loader callbacks use EEex's protected Lua-call bridge. Failed diagnostics
    // do not erase the native uncertain record or the root's durable journal.
    try { reinterpret_cast<Callback>(config.uncertain)(sprite,cls); } catch (...) {}
}
const void* lua_actor(void* L) {
    if (!on_host()) return nullptr;
    size_t count=0;
    const auto text=reinterpret_cast<const char*(*)(void*,int,size_t*)>(config.lua_tolstring)(L,1,&count);
    uintptr_t address=0;
    if (!text || count==0 || count>2*sizeof(uintptr_t)) return nullptr;
    const auto result=std::from_chars(text,text+count,address,16);
    return result.ec==std::errc{} && result.ptr==text+count ? reinterpret_cast<void*>(address) : nullptr;
}
void lua_number_string(void* L,uint64_t n) {
    char buffer[32];
    auto result=std::to_chars(buffer,buffer+31,n); *result.ptr=0;
    reinterpret_cast<const char*(*)(void*,const char*)>(config.lua_pushstring)(L,buffer);
}
}
int CBMR_Configure(const CBMR_Config* in) {
    if (configured || !in || in->abi!=2 || !in->original || !in->prepare || !in->complete
        || !in->uncertain || !in->get_xp_cap || !in->chitin_global
        || !in->lua_tolstring || !in->lua_pushstring || !in->original_create || !in->original_remove
        || !in->original_start || !in->get_deny || !in->capture_preview) return 0;
    config=*in; host=std::this_thread::get_id(); configured=true; return 1;
}
void CBMR_MakeDualClass(void* screen,void* sprite,unsigned char new_class) {
    if (!on_host()) return; // No unobserved off-thread reset is permitted.
    CBMI_View identity{};
    if (!CBMI_Query(sprite,&identity) || !identity.eligible
        || !CBMI_CanMutate(sprite,identity.incarnation)) { uncertain(sprite,new_class); return; }
    auto old=records.find(sprite);
    if (old!=records.end()) {
        if (old->second.incarnation==identity.incarnation) return; // Reentrant or unresolved reset.
        records.erase(old); // Proven different lifetime; never reuse stale pointer state.
    }
    Record record{{identity.incarnation,0,new_class,CBMR_PREPARING,1},screen,false};
    std::memcpy(&record.pre_base,static_cast<unsigned char*>(sprite)+0x570,sizeof(record.pre_base));
    try { records.emplace(sprite,record); } catch (...) { uncertain(sprite,new_class); return; }
    bool native_entered=false;
    try {
        // Prepare must validate everything before publishing its complete durable
        // pendingDual record; false/error prevents the first native instruction.
        if (!reinterpret_cast<Callback>(config.prepare)(sprite,new_class)) {
            records.erase(sprite); return;
        }
        records.at(sprite).stage=CBMR_NATIVE;
        native_entered=true;
        reinterpret_cast<void(*)(void*,void*,unsigned char)>(config.original)(screen,sprite,new_class);
        records.at(sprite).stage=CBMR_COMPLETING;
        if (reinterpret_cast<Callback>(config.complete)(sprite,new_class)) records.erase(sprite);
        else { records.at(sprite).stage=CBMR_UNCERTAIN; uncertain(sprite,new_class); }
    } catch (...) {
        if (native_entered) {
            records.at(sprite).stage=CBMR_UNCERTAIN;
            uncertain(sprite,new_class);
        } else records.erase(sprite);
        throw; // Native partial mutation is NEVER guessed back to its before state.
    }
}
void CBMR_StartEditing(void* screen,int actor_id,int mode) {
    if (!on_host() || mode!=0x18) return; // Only the audited dual-button callsite.
    void* sprite=nullptr;
    if (reinterpret_cast<unsigned char(*)(int,void**)>(config.get_deny)(actor_id,&sprite)!=0 || !sprite) return;
    CBMI_View identity{};
    if (!CBMI_Query(sprite,&identity) || !identity.eligible || !CBMI_CanMutate(sprite,identity.incarnation)
        || previews.count(sprite)) return;
    const auto pending=records.find(sprite);
    if (pending!=records.end() && pending->second.incarnation==identity.incarnation) return;
    uint32_t before=0;std::memcpy(&before,static_cast<unsigned char*>(sprite)+0x570,4);
    previews.emplace(sprite,CBMR_PreviewView{identity.incarnation,before});
    try {
        const bool captured=reinterpret_cast<Callback>(config.capture_preview)(sprite,0)!=0;
        previews.erase(sprite); // Authority exists only during the pre-preview callback.
        if (!captured || !CBMI_CanMutate(sprite,identity.incarnation)) return;
        reinterpret_cast<void(*)(void*,int,int)>(config.original_start)(screen,actor_id,mode);
    } catch (...) { previews.erase(sprite);throw; }
}
int CBMR_PreviewQuery(const void* sprite,CBMR_PreviewView* out) {
    if (!on_host() || !out) return 0;
    CBMI_View identity{};if (!CBMI_Query(sprite,&identity)) return 0;
    const auto found=previews.find(sprite);
    if (found==previews.end() || found->second.incarnation!=identity.incarnation) return 0;
    *out=found->second;return 1;
}
void CBMR_RemoveAbilities(void* screen,void* sprite,unsigned new_class,int remove) {
    if (!on_host() || new_class>255 || remove!=1) return;
    CBMI_View identity{};
    if (!CBMI_Query(sprite,&identity) || !identity.eligible || !CBMI_CanMutate(sprite,identity.incarnation)) return;
    auto old=records.find(sprite);
    if (old!=records.end()) {
        if (old->second.incarnation==identity.incarnation) return;
        records.erase(old);
    }
    Record record{{identity.incarnation,0,new_class,CBMR_PREPARING,2},screen,false};
    std::memcpy(&record.pre_base,static_cast<unsigned char*>(sprite)+0x570,4);
    records.emplace(sprite,record);
    bool entered=false;
    try {
        if (!reinterpret_cast<Callback>(config.prepare)(sprite,static_cast<unsigned char>(new_class))) {
            records.erase(sprite);return;
        }
        records.at(sprite).stage=CBMR_NATIVE;entered=true;
        reinterpret_cast<void(*)(void*,void*,unsigned,int)>(config.original_remove)(screen,sprite,new_class,remove);
        records.at(sprite).removed=true;
        // Hold the journal across the audited argument moves to MakeDualClass.
    } catch (...) {
        if (entered) { records.at(sprite).stage=CBMR_UNCERTAIN;uncertain(sprite,static_cast<unsigned char>(new_class)); }
        else records.erase(sprite);
        throw;
    }
}
void CBMR_CreateMakeDualClass(void* screen,void* sprite,unsigned char new_class) {
    if (!on_host()) return;
    CBMI_View identity{};
    auto found=records.find(sprite);
    if (!CBMI_Query(sprite,&identity) || !CBMI_CanMutate(sprite,identity.incarnation) || found==records.end()) return;
    auto& record=found->second;
    if (record.incarnation!=identity.incarnation || record.path!=2 || record.screen!=screen
        || record.new_class!=new_class || record.stage!=CBMR_NATIVE || !record.removed) return;
    uint32_t current=0;std::memcpy(&current,static_cast<unsigned char*>(sprite)+0x570,4);
    if (current!=record.pre_base) {
        record.stage=CBMR_UNCERTAIN;uncertain(sprite,new_class);return;
    }
    record.removed=false; // Consume once before native entry; reentry cannot reuse it.
    try {
        reinterpret_cast<void(*)(void*,void*,unsigned char)>(config.original_create)(screen,sprite,new_class);
        records.at(sprite).stage=CBMR_COMPLETING;
        if (reinterpret_cast<Callback>(config.complete)(sprite,new_class)) records.erase(sprite);
        else { records.at(sprite).stage=CBMR_UNCERTAIN;uncertain(sprite,new_class); }
    } catch (...) { records.at(sprite).stage=CBMR_UNCERTAIN;uncertain(sprite,new_class);throw; }
}
int CBMR_Query(const void* sprite,CBMR_View* out) {
    if (!on_host() || !out) return 0;
    CBMI_View identity{};
    if (!CBMI_Query(sprite,&identity)) return 0;
    const auto it=records.find(sprite);
    if (it==records.end() || it->second.incarnation!=identity.incarnation) return 0;
    *out=it->second; return 1;
}
int CBMR_NativeCap(const void* sprite,uint32_t* out) {
    if (!on_host() || !out) return 0;
    CBMI_View identity{};
    if (!CBMI_Query(sprite,&identity) || !identity.eligible) return 0;
    const auto chitin=*reinterpret_cast<unsigned char*const*>(config.chitin_global);
    if (!chitin) return 0;
    // Both pinned native builds: CBaldurChitin::m_pObjectGame +0x1090;
    // CInfGame::m_ruleTables is its first member (offset zero).
    const auto game=*reinterpret_cast<void*const*>(chitin+0x1090);
    if (!game) return 0;
    const auto start_ai=static_cast<const unsigned char*>(sprite)+0x4B68;
    *out=reinterpret_cast<uint32_t(*)(void*,const void*)>(config.get_xp_cap)(game,start_ai);
    return 1;
}
int CBMR_LuaQuery(void* L) {
    CBMR_View value{};
    if (!CBMR_Query(lua_actor(L),&value)) return 0;
    static const char* stages[]={"", "preparing", "native", "completing", "uncertain"};
    reinterpret_cast<const char*(*)(void*,const char*)>(config.lua_pushstring)(L,stages[value.stage]);
    lua_number_string(L,value.incarnation); lua_number_string(L,value.pre_base); lua_number_string(L,value.new_class);
    reinterpret_cast<const char*(*)(void*,const char*)>(config.lua_pushstring)(L,value.path==2?"create":"character");
    return 5;
}
int CBMR_LuaPreviewQuery(void* L) {
    CBMR_PreviewView value{};if (!CBMR_PreviewQuery(lua_actor(L),&value)) return 0;
    reinterpret_cast<const char*(*)(void*,const char*)>(config.lua_pushstring)(L,"capturing");
    lua_number_string(L,value.incarnation);lua_number_string(L,value.pre_base);return 3;
}
int CBMR_LuaNativeCap(void* L) {
    uint32_t cap=0;
    if (!CBMR_NativeCap(lua_actor(L),&cap)) return 0;
    lua_number_string(L,cap); return 1;
}
