#include "award_native.h"
#include "writer_native.h"
#include <algorithm>
#include <atomic>
#include <charconv>
#include <cstring>
#include <thread>
#include <unordered_map>
namespace {
CBMA_Config config{};
bool configured=false;
std::thread::id host;
std::atomic<int> status{0},fallback_status{0};
std::atomic<uint64_t> fallbacks{0};
struct Entry {const void* effect;CBMA_View view;};
std::unordered_map<const void*,Entry> records;
using Callback=int(*)(void*,void*);
uint32_t read(const void* object,size_t offset) {
    uint32_t n;std::memcpy(&n,static_cast<const unsigned char*>(object)+offset,4);return n;
}
void write(void* object,size_t offset,uint32_t n){std::memcpy(static_cast<unsigned char*>(object)+offset,&n,4);}
bool on_host(){return configured&&std::this_thread::get_id()==host;}
int original(void* effect,void* sprite){return reinterpret_cast<Callback>(config.original)(effect,sprite);}
// No refusal returns 0. CGameEffectList::HandleList (2.7.3.0) then stops
// resolving the rest of the list and keeps this undone effect, which blocks it
// on every later pass; a save then drops the op187 locals behind it (CEBG #19).
// Native: the original, unbanked, counted for the fallback notice. Where the
// operation it executes replaces the word, the bank takes the stored word. That
// is the effect as it now reads: a changed preparation may have made the award
// a SET, a percentage or a loss (CBMW_LeafReplaces, the writer's own rule).
int native(void* effect,void* sprite,int why){
    if(CBMW_LeafReplaces(effect,sprite))CBMI_NoteReplaced(sprite);
    status=why;fallback_status=why;++fallbacks;return original(effect,sprite);
}
// Unowned: the original as without the bank, neither banked nor counted (status
// 1): an effect of another shape, an ineligible actor, a runtime that passes it
// on. It is classified as it executes all the same: a retry runs whatever the
// effect then reads, so an award its first preparation made a SET is a SET here.
int unowned(void* effect,void* sprite){
    if(CBMW_LeafReplaces(effect,sprite))CBMI_NoteReplaced(sprite);
    status=1;return original(effect,sprite);
}
// Defer: neither done (+0x114) nor repass (+0x118). The list continues and
// resolves this effect again on its next pass. No defer can repeat without end:
// - while any actor is saved: a marshal scope is RAII on this thread and ends
//   with that save; effects resolved inside it wait for the next pass after it;
// - while a change of this actor (either bridge) or this effect is in flight: a
//   record leaves that stage on every exit of its call, an exception included,
//   and only the bank's callbacks and the call-free leaf run inside it;
// - when what a preparation saw changed: once per effect, then native; with no
//   room in the retry table, native at once (CBMW_FirstChange);
// - when the preparation provably ended the actor's lifetime (11): prohibited
//   for the bank's callbacks and enforced statically, and the effect then
//   belongs to whatever the list holds next pass;
// - when another thread's lifetime event at the actor's address left it unknown
//   while the bank prepared: once, as every identity then stays unavailable for
//   the process and the next pass runs the original (3);
// - with no effect, actor or configuration (status 2): unreachable, as
//   HandleList passes its own effect and actor, and the hook exists only after
//   Configure succeeded.
int defer(int why){status=why;return 1;}
// Complete: done and repass as the original sets them, without XP. Only for an
// award whose (now uncertain) journal holds the amount.
int complete(void* effect,int why){write(effect,0x118,1);write(effect,0x114,1);status=why;return 1;}
void uncertain(void* sprite,void* effect) {
    status=7;
    try {reinterpret_cast<Callback>(config.uncertain)(sprite,effect);}catch(...){}
}
// The runtime withdraws the journal of a preparation no store followed, and
// only while it is still exactly that prepared journal.
bool withdrawn(void* sprite,void* effect) {
    records.at(sprite).view.stage=CBMA_WITHDRAWING;
    try {return reinterpret_cast<Callback>(config.uncertain)(sprite,effect)!=0;}catch(...){return false;}
}
int holds(const void* sprite,uint64_t incarnation) {
    const auto it=records.find(sprite);
    if(it==records.end())return 0;
    return it->second.view.stage!=CBMA_UNCERTAIN?1:it->second.view.incarnation==incarnation?2:0;
}
struct RestoreAmount {
    void* effect;uint32_t value;
    ~RestoreAmount(){write(effect,0x1c,value);}
};
const void* lua_pointer(void* L,int index) {
    size_t size=0;
    const auto s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(config.lua_tolstring)(L,index,&size);
    uintptr_t p=0;
    if(!s||size==0||size>sizeof(p)*2)return nullptr;
    const auto result=std::from_chars(s,s+size,p,16);
    return result.ec==std::errc{}&&result.ptr==s+size?reinterpret_cast<void*>(p):nullptr;
}
void text(void* L,const char* s){reinterpret_cast<const char*(*)(void*,const char*)>(config.lua_pushstring)(L,s);}
void number(void* L,int64_t n){char buffer[32];auto r=std::to_chars(buffer,buffer+31,n);*r.ptr=0;text(L,buffer);}
}
int CBMA_Configure(const CBMA_Config* in) {
    if(configured||!in||in->abi!=1||!in->original||!in->before||!in->complete||!in->uncertain
        ||!in->lua_tolstring||!in->lua_pushstring)return 0;
    config=*in;host=std::this_thread::get_id();configured=true;return 1;
}
int CBMA_ApplyEffect(void* effect,void* sprite) {
    if(!effect||!sprite){status=2;return 1;} // Nothing to resolve; touch nothing.
    if(!configured){status=2;return 1;} // No original to run; the hook is installed only after Configure.
    // The thread audit (main-thread-audit-2.7.3.txt) finds no resolved path from another
    // thread to effect resolution in 2.7.3.0; its unresolved indirect routes stay open.
    // Off the main thread: the original, as without the bank, counted; no record or
    // note, as the bank's registries are the main thread's.
    if(!on_host())return native(effect,sprite,2);
    CBMW_SettleOnExit settle{sprite};
    const auto amount=read(effect,0x1c);
    const auto mode=read(effect,0x20);
    if(read(effect,0x10)==104&&read(effect,0x24)==1&&mode<=2
        &&(mode!=0||amount==0||amount>0x7fffffffu)){
        try{const int result=CBMW_EffectWrite(effect,sprite,config.original);status=CBMW_LastStatus();return result;}
        catch(...){status=CBMW_LastStatus();throw;}
    }
    CBMW_RetryScope resolution{effect};
    const auto wait=[&](int why){resolution.kept=true;return defer(why);};
    // Nonpermanent and unknown modes retain the complete original behavior;
    // they are not earned permanent awards or supported account writes.
    if(read(effect,0x10)!=104||read(effect,0x20)!=0||read(effect,0x24)!=1
        ||amount==0||amount>0x7fffffffu)return unowned(effect,sprite);
    CBMI_View identity{};
    if(!CBMI_Query(sprite,&identity))return native(effect,sprite,3);
    if(!identity.eligible)return unowned(effect,sprite);
    if(!CBMI_CanMutate(sprite,identity.incarnation))return wait(4); // Serializing: resolve after it.
    auto previous=records.find(sprite);
    if(previous!=records.end()&&previous->second.view.stage==CBMA_UNCERTAIN
        &&previous->second.view.incarnation!=identity.incarnation)records.erase(previous); // Proven new lifetime cannot inherit a receipt.
    const int held=holds(sprite,identity.incarnation)|CBMW_Holds(sprite,identity.incarnation);
    if(held&1)return wait(4); // A change of this actor is in flight (either bridge).
    if(held&2)return native(effect,sprite,4); // Its uncertain journal (either bridge) awaits reconciliation; never bank around it.
    for(auto it=records.begin();it!=records.end();) {
        // Only a lifetime that provably ended takes its receipt along.
        if(it->second.view.stage==CBMA_UNCERTAIN&&CBMI_Lifetime(it->first,it->second.view.incarnation)<0){
            it=records.erase(it);continue;
        }
        // An uncertain record's effect was completed, so its address may now hold
        // another actor's new effect. Only an in-flight record still holds it.
        if(it->second.view.stage!=CBMA_UNCERTAIN&&it->second.effect==effect)return wait(4);
        ++it;
    }
    const auto before=read(sprite,0x570);
    const auto applied=std::min(amount,0xffffffffu-before);
    Entry entry{effect,{identity.incarnation,before,amount,applied,amount-applied,before,0,CBMA_PREPARING}};
    try {records.emplace(sprite,entry);}catch(...){return native(effect,sprite,5);}
    bool native_entered=false;
    try {
        const int disposition=reinterpret_cast<Callback>(config.before)(sprite,effect);
        const int life=CBMI_Lifetime(sprite,identity.incarnation);
        if(life==0) {
            // Another thread constructed or destroyed an actor at this address
            // while the bank prepared this award: no proof that this is still
            // the actor it prepared, nor that it is not. No leaf runs in this
            // call and its runtime is not called for it again. A journal it
            // published stays, uncertain, and the effect is done without XP (7);
            // with none it is resolved next pass (4), which finds no identity
            // and runs the original (3), whatever room the retry table has.
            if(disposition==1){records.at(sprite).view.stage=CBMA_UNCERTAIN;return complete(effect,7);}
            records.erase(sprite);return wait(4);
        }
        if(life<0) {
            // The preparation provably ended this lifetime (11). Destroying or
            // recreating an actor inside the bank's callbacks is prohibited:
            // CGameEffectList::HandleList keeps using these pointers after we
            // return, which nothing here can make safe; the static check
            // tests/test_campaign_xp_callback_lifetime.py enforces it. Were one
            // to anyway, nothing is written into another lifetime: no award, no
            // callback for the ended one, the effect left as it is, unresolved.
            records.erase(sprite);CBMW_CountEnded();status=11;return 1;
        }
        const bool same=CBMI_CanMutate(sprite,identity.incarnation)&&read(sprite,0x570)==before
            &&read(effect,0x10)==104&&read(effect,0x1c)==amount&&read(effect,0x20)==0&&read(effect,0x24)==1;
        if(!same) {
            // What the preparation saw changed before any store, or its identity
            // became unknown (another thread's lifetime event at another address:
            // no proof that this lifetime ended, so the award is not dropped, and
            // none that it is another actor). Its journal, if a tracked
            // disposition published one, is withdrawn; nothing then holds this
            // award and it is retried from a fresh boundary. Only a journal that
            // cannot be withdrawn (as without an identity) keeps it: done without
            // XP.
            if(disposition==1&&!withdrawn(sprite,effect)) {
                records.at(sprite).view.stage=CBMA_UNCERTAIN;uncertain(sprite,effect);return complete(effect,7);
            }
            records.erase(sprite);
            return CBMW_FirstChange(effect,sprite,identity.incarnation)?wait(4):native(effect,sprite,8);
        }
        if(disposition==2){records.erase(sprite);return unowned(effect,sprite);}
        if(disposition!=1){records.erase(sprite);return native(effect,sprite,5);} // Refused, including any Lua error.
        auto& v=records.at(sprite).view;
        v.stage=CBMA_NATIVE;
        native_entered=true;
        // The banked add replaces nothing: same proved a permanent mode-0 award
        // of 1..0x7fffffff, and it is narrowed to the room above the stored word.
        {
            RestoreAmount restore{effect,amount};
            if(applied!=amount)write(effect,0x1c,applied);
            v.native_result=original(effect,sprite);
        } // Original amount is restored BEFORE protected completion/serialization.
        v.post_base=read(sprite,0x570);
        v.stage=CBMA_COMPLETING;
        CBMI_View after{};
        const bool valid=CBMI_Query(sprite,&after)&&after.incarnation==identity.incarnation
            &&v.native_result==1&&v.post_base==before+applied
            &&read(effect,0x114)==1&&read(effect,0x118)==1;
        const int result=v.native_result;
        if(valid&&reinterpret_cast<Callback>(config.complete)(sprite,effect)) {
            records.erase(sprite);status=6;
        }else{v.stage=CBMA_UNCERTAIN;uncertain(sprite,effect);}
        return result; // A committed native award must not be replayed after Lua failure.
    } catch(...) {
        if(records.find(sprite)==records.end())throw; // Unowned original passthrough threw.
        auto& v=records.at(sprite).view;
        if(native_entered) {
            v.post_base=read(sprite,0x570);v.stage=CBMA_UNCERTAIN;uncertain(sprite,effect);
        }else records.erase(sprite);
        throw; // Preserve ordinary C++ unwind; no invented native rollback.
    }
}
int CBMA_Query(const void* sprite,const void* effect,CBMA_View* out) {
    if(!on_host()||!out)return 0;
    CBMI_View identity{};
    if(!CBMI_Query(sprite,&identity))return 0;
    const auto it=records.find(sprite);
    if(it==records.end()||it->second.effect!=effect||it->second.view.incarnation!=identity.incarnation)return 0;
    *out=it->second.view;return 1;
}
int CBMA_LuaQuery(void* L) {
    if(!on_host())return 0;
    CBMA_View v{};
    if(!CBMA_Query(lua_pointer(L,1),lua_pointer(L,2),&v))return 0;
    static const char* names[]={"","preparing","native","completing","uncertain","withdrawing"};
    text(L,names[v.stage]);number(L,static_cast<int64_t>(v.incarnation));number(L,v.pre_base);
    number(L,v.amount);number(L,v.applied);number(L,v.remainder);number(L,v.native_result);number(L,v.post_base);
    return 8;
}
int CBMA_LastStatus(){return status.load();}
int CBMA_Holds(const void* sprite,uint64_t incarnation){return holds(sprite,incarnation);}
uint64_t CBMA_Fallbacks(int* last_status){if(last_status)*last_status=fallback_status.load();return fallbacks.load();}
int CBMA_LuaFallbacks(void* L) {
    if(!on_host())return 0;
    int award=0,writer=0;
    const auto total=CBMA_Fallbacks(&award)+CBMW_Fallbacks(&writer);
    char kept[256];const auto count=CBMW_Kept(kept,sizeof(kept));
    number(L,static_cast<int64_t>(total));number(L,award);number(L,writer);
    number(L,static_cast<int64_t>(CBMW_Ended()));number(L,static_cast<int64_t>(count));text(L,kept);
    return 6;
}
