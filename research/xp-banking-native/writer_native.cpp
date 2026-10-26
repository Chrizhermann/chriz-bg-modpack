#include "writer_native.h"
#include "award_native.h"
#include <atomic>
#include <charconv>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <iterator>
#include <thread>
#include <unordered_map>
#include <vector>
namespace{
CBMW_Config config{};bool configured=false;std::thread::id host;std::atomic<int> status{0},fallback_status{0};
std::atomic<uint64_t> fallbacks{0},ended_changes{0};
std::unordered_map<const void*,CBMW_View> records;
using Callback=int(*)(void*);
uint32_t xp(const void* actor){uint32_t n;std::memcpy(&n,static_cast<const unsigned char*>(actor)+0x570,4);return n;}
void xp(void* actor,uint32_t n){std::memcpy(static_cast<unsigned char*>(actor)+0x570,&n,4);}
uint32_t field(const void* p,size_t off){uint32_t n;std::memcpy(&n,static_cast<const unsigned char*>(p)+off,4);return n;}
void field(void* p,size_t off,uint32_t n){std::memcpy(static_cast<unsigned char*>(p)+off,&n,4);}
struct RestoreEffect{void* effect;uint32_t amount,mode;~RestoreEffect(){field(effect,0x1c,amount);field(effect,0x20,mode);}};
bool on_host(){return configured&&std::this_thread::get_id()==host;}
struct Origin{
    const void* sprite;uint64_t incarnation;uint32_t kind,target;bool consumed=false;int completion=0;Origin* prior;static thread_local Origin* top;
    Origin(const void*s,uint64_t i,uint32_t k,uint32_t t):sprite(s),incarnation(i),kind(k),target(t),prior(top){top=this;}
    ~Origin(){top=prior;}
};
thread_local Origin* Origin::top=nullptr;
Origin* take_origin(const void* s,uint64_t i,uint32_t value,uint32_t mode){
    auto* p=Origin::top;
    if(!p||p->consumed||p->sprite!=s||p->incarnation!=i||p->target!=value||mode!=0)return nullptr;
    p->consumed=true;return p;
}
struct OriginResult{Origin* p;~OriginResult(){if(p)p->completion=status.load();}};
void uncertain(void* sprite){status=7;try{reinterpret_cast<Callback>(config.uncertain)(sprite);}catch(...) {}}
// As the award bridge: withdraw the journal of a preparation no store followed.
bool withdrawn(void* sprite){
    records.at(sprite).stage=CBMW_WITHDRAWING;
    try{return reinterpret_cast<Callback>(config.uncertain)(sprite)!=0;}catch(...){return false;}
}
// One retry per opcode-104 effect (either bridge) whose preparation saw its
// state change, then the original (8). An entry leaves when its effect resolves
// (any outcome but a defer) or once its lifetime provably ended; a live entry,
// or one whose lifetime is merely unknown, is never evicted. A table full of
// them grants no new retry: that effect runs the original at once (8). So no
// effect defers twice for a change.
struct Retry{const void* sprite;uint64_t incarnation;};
std::unordered_map<const void*,Retry> retries;
constexpr size_t retry_limit=64;
bool gone(const Retry& r){return CBMI_Lifetime(r.sprite,r.incarnation)<0;}
// Whether a store the bank did not take left base plus overflow inexact: a SET
// or a percentage replaces the word, an addition does when it passes either end
// of the word (the engine wraps it). The bank then takes the stored word (see
// R.Snapshot); any other such store kept base plus overflow exact.
bool replaces(uint32_t before,uint32_t value,uint32_t mode){
    if(mode!=1)return true;
    const int64_t sum=int64_t(before)+(value<=0x7fffffffu?int64_t(value):int64_t(value)-0x100000000ll);
    return sum<0||sum>0xffffffffll;
}
// The original opcode-104 leaf when banking cannot take this write; counted.
int fall_back(uintptr_t leaf,void* effect,void* sprite,int why){
    if(CBMW_LeafReplaces(effect,sprite))CBMI_NoteReplaced(sprite);
    status=why;fallback_status=why;++fallbacks;return reinterpret_cast<int(*)(void*,void*)>(leaf)(effect,sprite);
}
// The original stat44 store (mode 1 adds, any other sets) when banking cannot
// take this setter write; counted. The bank re-derives from that base XP.
void own_write(void* sprite,uint32_t value,uint32_t mode,int why){
    const auto before=xp(sprite);
    if(replaces(before,value,mode))CBMI_NoteReplaced(sprite);
    xp(sprite,mode==1?before+value:value);fallback_status=why;++fallbacks;
}
int holds(const void* sprite,uint64_t incarnation){
    const auto it=records.find(sprite);
    if(it==records.end())return 0;
    return it->second.stage!=CBMW_UNCERTAIN?1:it->second.incarnation==incarnation?2:0;
}
// A setter write that arrived while a change of its actor was in flight. Only
// our own callbacks run inside such a window and none of them writes XP; were
// one to, the write lands as the window closes, never inside it. A setter write
// whose actor's lifetime became unknown at its address (another thread's
// lifetime event there, CBMI_Lifetime 0) is kept here instead (12): never
// applied, never dropped, its actor never read or written again. Kept entries
// are the native unresolved journal of this process; the loader log lists them.
struct Deferred{void* sprite;uint64_t incarnation;uint32_t value,mode;bool kept;};
std::vector<Deferred> deferred;
// Slots promised to setter writes whose preparation runs: a deferral never takes
// them, so keeping such a write after its preparation cannot fail to allocate.
size_t promised=0;
bool room(){try{deferred.reserve(deferred.size()+promised+1);return true;}catch(...){return false;}}
struct Promise{
    bool held=false;
    bool take(){if(!room())return false;held=true;++promised;return true;}
    void use(){if(held){held=false;--promised;}}
    ~Promise(){use();}
};
enum class Outcome{native,defer,complete};
const char* arg(void* L,int n,size_t* length){return reinterpret_cast<const char*(*)(void*,int,size_t*)>(config.lua_tolstring)(L,n,length);}
bool unsigned_arg(void* L,int n,int base,uint64_t* out){
    size_t length=0;const char* s=arg(L,n,&length);if(!s||!length||length>20)return false;
    auto result=std::from_chars(s,s+length,*out,base);return result.ec==std::errc{}&&result.ptr==s+length;
}
const void* actor_arg(void* L){uint64_t n=0;return unsigned_arg(L,1,16,&n)?reinterpret_cast<const void*>(n):nullptr;}
void text(void* L,const char* s){reinterpret_cast<const char*(*)(void*,const char*)>(config.lua_pushstring)(L,s);}
void number(void* L,uint64_t n){char buffer[32];auto result=std::to_chars(buffer,buffer+31,n);*result.ptr=0;text(L,buffer);}
void boolean(void* L,bool b){reinterpret_cast<void(*)(void*,int)>(config.lua_pushboolean)(L,b);}
}
// CGameEffectXP::ApplyEffect writes the XP word only for permanent timing
// (+0x24 1; any other writes a derived stat): mode 0 adds the signed amount, 1
// sets it, 2 sets that percentage of it, any other mode writes nothing. It never
// reads the opcode field (bg2ee-2.7.3-xp.txt, 0x1401CB370).
bool CBMW_LeafReplaces(const void* effect,const void* sprite){
    const auto mode=field(effect,0x20);
    return field(effect,0x24)==1&&mode<=2&&replaces(xp(sprite),field(effect,0x1c),mode==0?1u:0u);
}
bool CBMW_FirstChange(const void* effect,const void* sprite,uint64_t incarnation){
    const auto found=retries.find(effect);
    if(found!=retries.end()&&found->second.sprite==sprite&&found->second.incarnation==incarnation)return false;
    if(found==retries.end()&&retries.size()>=retry_limit){
        for(auto it=retries.begin();it!=retries.end();)it=gone(it->second)?retries.erase(it):std::next(it);
        if(retries.size()>=retry_limit)return false;
    }
    // An entry of another actor or lifetime at this address belonged to an
    // effect that no longer exists there: this one replaces it.
    try{retries[effect]=Retry{sprite,incarnation};}catch(...){return false;} // A retry it cannot remember gets none.
    return true;
}
CBMW_RetryScope::~CBMW_RetryScope(){if(effect&&!kept)retries.erase(effect);}
void CBMW_CountEnded(){++ended_changes;}
uint64_t CBMW_Ended(){return ended_changes.load();}
int CBMW_Configure(const CBMW_Config* in){
    if(configured||!in||in->abi!=1||!in->setter||!in->before||!in->complete||!in->uncertain
        ||!in->lua_tolstring||!in->lua_pushstring||!in->lua_pushboolean)return 0;
    config=*in;configured=true;host=std::this_thread::get_id();return 1;
}
namespace {
void* write_impl(void* sprite,uint32_t value,uint32_t mode,void* effect,uintptr_t leaf,int* native_result){
    if(!sprite){status=2;return sprite;} // Nothing to write to; the game always passes its actor.
    // The thread audit (main-thread-audit-2.7.3.txt) finds no resolved path from
    // another thread to scripts or effects in 2.7.3.0; its unresolved indirect
    // routes stay open. Off the main thread: the game's own store, as without the
    // bank, counted; no record or note, as the bank's registries are the main
    // thread's. CBMW_EffectWrite ran an effect's original.
    if(!on_host()){
        if(!effect)own_write(sprite,value,mode,2);
        status=2;return sprite;
    }
    CBMW_SettleOnExit settle{sprite};
    CBMW_RetryScope resolution{effect};
    const auto effect_mode=effect?field(effect,0x20):0;
    // Unowned (an ineligible actor, a runtime that passes it on): the original as
    // without the bank, not counted, classified as it executes all the same.
    const auto passthrough=[&](){
        if(effect){
            if(CBMW_LeafReplaces(effect,sprite))CBMI_NoteReplaced(sprite);
            *native_result=reinterpret_cast<int(*)(void*,void*)>(leaf)(effect,sprite);
        }else{
            const auto now=xp(sprite);
            if(replaces(now,value,mode))CBMI_NoteReplaced(sprite);
            xp(sprite,mode==1?now+value:value);
        }
        status=1;
    };
    // No refusal drops a stat44 setter write: it is the game's own store. An
    // opcode-104 refusal never leaves a 0 result, which would stop
    // CGameEffectList::HandleList for the rest of the list (CEBG #19). Its
    // defers are bounded exactly as the award bridge's (see CBMA defer).
    const auto refuse=[&](int why,Outcome how){
        if(!effect){own_write(sprite,value,mode,why);status=why;return sprite;}
        if(how==Outcome::native){*native_result=fall_back(leaf,effect,sprite,why);return sprite;}
        if(how==Outcome::complete){field(effect,0x118,1);field(effect,0x114,1);} // Done as the leaf marks it, no XP.
        else resolution.kept=true; // Defer: done/repass unset, resolved again next pass.
        status=why;*native_result=1;return sprite;
    };
    CBMI_View identity{};
    if(!CBMI_Query(sprite,&identity))return refuse(3,Outcome::native);
    const auto before=xp(sprite);
    if(!identity.eligible){passthrough();return sprite;}
    // Every later outcome of an owned SET reaches CBMW_ApplyOwnedSet's status.
    auto* owned=effect?nullptr:take_origin(sprite,identity.incarnation,value,mode);OriginResult receipt{owned};
    // Saving: an effect resolves after it, a setter write is the game's own (9).
    if(!CBMI_CanMutate(sprite,identity.incarnation))return refuse(effect?4:9,Outcome::defer);
    auto prior=records.find(sprite);
    if(prior!=records.end()&&prior->second.stage==CBMW_UNCERTAIN&&prior->second.incarnation!=identity.incarnation)
        records.erase(prior); // A proven new lifetime cannot inherit a receipt.
    const int held=holds(sprite,identity.incarnation)|CBMA_Holds(sprite,identity.incarnation);
    if(held&1){ // A change of this actor is in flight (either bridge).
        if(effect)return refuse(4,Outcome::defer);
        if(!room())return refuse(10,Outcome::native); // Room beyond every promised slot: the push cannot allocate.
        deferred.push_back({sprite,identity.incarnation,value,mode,false});
        status=10;return sprite; // Lands as that change closes (CBMW_Settle).
    }
    if(held&2)return refuse(4,Outcome::native); // Its uncertain journal (either bridge) awaits reconciliation.
    if(effect)for(auto it=records.begin();it!=records.end();){
        if(it->second.stage==CBMW_UNCERTAIN&&CBMI_Lifetime(it->first,it->second.incarnation)<0){
            it=records.erase(it);continue; // Only a lifetime that provably ended takes its receipt along.
        }
        // A completed effect's address may now hold another actor's new effect.
        if(it->second.stage!=CBMW_UNCERTAIN&&it->second.effect==effect)return refuse(4,Outcome::defer);
        ++it;
    }
    CBMW_View v{identity.incarnation,value,mode,before,before,0,owned?owned->kind:0,CBMW_PREPARING,false,
        effect?1u:0u,effect_mode,0,effect};
    try{records.emplace(sprite,v);}catch(...){return refuse(5,Outcome::native);}
    Promise slot; // A setter write kept after its preparation takes it.
    if(!effect&&!slot.take()){records.erase(sprite);return refuse(5,Outcome::native);}
    const auto keep=[&](){ // Kept, never written (12).
        slot.use();deferred.push_back({sprite,identity.incarnation,value,mode,true});status=12;return sprite;
    };
    bool wrote=false;
    try{
        const auto disposition=reinterpret_cast<Callback>(config.before)(sprite);
        const int life=CBMI_Lifetime(sprite,identity.incarnation);
        if(life==0){
            // Another thread constructed or destroyed an actor at this address
            // while the bank prepared this write: no proof that this is still
            // the actor it prepared, nor that it is not. Nothing is written
            // there and its runtime is not called for it again. A journal it
            // published stays, uncertain; the effect is done without XP (7) or,
            // with none, resolved next pass (4), which finds no identity (3); a
            // setter write is kept (12).
            if(disposition==1)records.at(sprite).stage=CBMW_UNCERTAIN;else records.erase(sprite);
            if(!effect)return keep();
            return disposition==1?refuse(7,Outcome::complete):refuse(4,Outcome::defer);
        }
        if(life<0){
            // The preparation provably ended this lifetime (11). Destroying or
            // recreating an actor inside the bank's callbacks is prohibited: the
            // game's callers (HandleList, the setter's recalc) keep using these
            // pointers after we return, which nothing here can make safe; the
            // static check tests/test_campaign_xp_callback_lifetime.py enforces
            // it. Were one to anyway, nothing is written into another lifetime:
            // no store, no callback for the ended one, an effect left as it is.
            records.erase(sprite);CBMW_CountEnded();status=11;
            if(effect)*native_result=1;
            return sprite;
        }
        auto& current=records.at(sprite);
        if(!CBMI_CanMutate(sprite,identity.incarnation)||xp(sprite)!=before
            ||(effect&&(field(effect,0x10)!=104||field(effect,0x1c)!=value||field(effect,0x20)!=effect_mode||field(effect,0x24)!=1))){
            // What the preparation saw changed before any store, or its identity
            // became unknown (another thread's lifetime event at another address:
            // no proof that this lifetime ended, so no write is dropped, and none
            // that it is another actor, so the write lands). Its journal, if a
            // tracked disposition published one, is withdrawn; then nothing holds
            // this write and no record stays: an effect retries once from a fresh
            // boundary, then runs the original leaf (8); a setter write is the
            // game's own (8). Only a journal that cannot be withdrawn (as without
            // an identity) keeps it: the effect is done without XP, the setter
            // write is the game's own (7).
            if(disposition==1&&!withdrawn(sprite)){current.stage=CBMW_UNCERTAIN;uncertain(sprite);return refuse(7,Outcome::complete);}
            records.erase(sprite);
            return effect&&CBMW_FirstChange(effect,sprite,identity.incarnation)?refuse(4,Outcome::defer):refuse(8,Outcome::native);
        }
        if(disposition==2){records.erase(sprite);passthrough();return sprite;}
        if(disposition!=1||!current.planned){records.erase(sprite);return refuse(5,Outcome::native);} // Incl. any Lua error.
        current.stage=CBMW_WRITING;
        // Exactly the stat44-owned 32-bit word. No callback occurs between this
        // store and its observed post-value. Original recalc runs AFTER return.
        // The bank's own planned word: it replaces nothing the bank did not take.
        if(effect){
            RestoreEffect restore{effect,value,effect_mode};
            field(effect,0x1c,current.planned_base);field(effect,0x20,1); // Original native permanent SET path.
            wrote=true;*native_result=reinterpret_cast<int(*)(void*,void*)>(leaf)(effect,sprite);
            current.native_result=*native_result;
        }else{xp(sprite,current.planned_base);wrote=true;}
        current.post_base=xp(sprite);current.stage=CBMW_COMPLETING;
        const bool native_ok=!effect||(current.native_result==1&&field(effect,0x114)==1&&field(effect,0x118)==1);
        if(current.post_base==current.planned_base&&native_ok&&reinterpret_cast<Callback>(config.complete)(sprite)){
            records.erase(sprite);status=6;
        }else{current.stage=CBMW_UNCERTAIN;uncertain(sprite);}
    }catch(...){
        if(records.find(sprite)==records.end())throw; // Unowned original leaf threw.
        if(wrote){auto& current=records.at(sprite);current.post_base=xp(sprite);current.stage=CBMW_UNCERTAIN;uncertain(sprite);}
        else {records.erase(sprite);status=5;}
        throw; // Real caller frame has the game's original unwind metadata.
    }
    return sprite;
}
}
void* CBMW_Write(void* sprite,uintptr_t,uint32_t value,uint32_t mode){return write_impl(sprite,value,mode,nullptr,0,nullptr);}
int CBMW_EffectWrite(void* effect,void* sprite,uintptr_t leaf){
    if(!effect||!sprite||!leaf){status=2;return 1;} // Nothing that can be resolved; touch nothing.
    const auto value=field(effect,0x1c),effect_mode=field(effect,0x20);
    // A host or dispatch mismatch is not a write this bridge owns: the original.
    if(!on_host()||field(effect,0x10)!=104||field(effect,0x24)!=1||effect_mode>2
        ||(effect_mode==0&&value>0&&value<=0x7fffffff))return fall_back(leaf,effect,sprite,2);
    int result=1;
    write_impl(sprite,value,effect_mode==0?1u:effect_mode==1?0u:2u,effect,leaf,&result);
    return result; // Even failed completion retains the original done/repass/result.
}
int CBMW_Query(const void* sprite,CBMW_View* out){
    if(!on_host()||!out)return 0;CBMI_View identity{};
    if(!CBMI_Query(sprite,&identity))return 0;auto found=records.find(sprite);
    if(found==records.end()||found->second.incarnation!=identity.incarnation)return 0;
    *out=found->second;return 1;
}
int CBMW_Plan(const void* sprite,uint32_t target){
    CBMW_View v{};if(!CBMW_Query(sprite,&v)||v.stage!=CBMW_PREPARING||v.planned||xp(sprite)!=v.pre_base)return 0;
    auto& current=records.at(sprite);current.planned=true;current.planned_base=target;return 1;
}
int CBMW_ApplyOwnedSet(void* sprite,uint32_t target,uint32_t kind,uint16_t* result){
    if(!on_host()||!result||(kind!=1&&kind!=2))return 0;
    CBMI_View id{};if(!CBMI_Query(sprite,&id)||!id.eligible||!CBMI_CanMutate(sprite,id.incarnation))return 0;
    Origin scoped(sprite,id.incarnation,kind,target);
    *result=reinterpret_cast<uint16_t(*)(void*,uint32_t,uint32_t,uint32_t)>(config.setter)(sprite,44,target,0);
    if(!scoped.consumed)return 0;
    status=scoped.completion; // Recalc may have performed unrelated nested writes.
    return 1; // Invocation succeeded; LastStatus distinguishes committed/refused.
}
int CBMW_LuaQuery(void* L){
    if(!on_host())return 0;CBMW_View v{};if(!CBMW_Query(actor_arg(L),&v))return 0;
    static const char* stages[]={"","preparing","writing","completing","uncertain","withdrawing"};
    static const char* origins[]={"unclassified","party_average_set","recruitment_catchup"};
    text(L,stages[v.stage]);number(L,v.incarnation);number(L,v.raw_value);number(L,v.mode);
    number(L,v.pre_base);number(L,v.post_base);text(L,origins[v.origin]);
    if(v.planned)number(L,v.planned_base);else text(L,"");
    text(L,v.source==1?"opcode104":"stat44");number(L,v.effect_mode);number(L,static_cast<uint64_t>(v.native_result));
    return 11;
}
int CBMW_LuaPlan(void* L){
    if(!on_host())return 0;uint64_t target=0;
    boolean(L,unsigned_arg(L,2,10,&target)&&target<=0xffffffff&&CBMW_Plan(actor_arg(L),static_cast<uint32_t>(target)));return 1;
}
int CBMW_LuaApplyOwnedSet(void* L){
    if(!on_host())return 0;uint64_t target=0,kind=0;uint16_t result=0;
    if(!unsigned_arg(L,2,10,&target)||target>0xffffffff||!unsigned_arg(L,3,10,&kind)||kind>2
        ||!CBMW_ApplyOwnedSet(const_cast<void*>(actor_arg(L)),static_cast<uint32_t>(target),static_cast<uint32_t>(kind),&result))return 0;
    number(L,result);number(L,status.load());return 2;
}
int CBMW_LastStatus(){return status.load();}
uint64_t CBMW_Fallbacks(int* last_status){if(last_status)*last_status=fallback_status.load();return fallbacks.load();}
int CBMW_Holds(const void* sprite,uint64_t incarnation){return holds(sprite,incarnation);}
void CBMW_Settle(void* sprite){
    if(deferred.empty()||((holds(sprite,0)|CBMA_Holds(sprite,0))&1))return; // An outer change is still open.
    for(size_t i=0;i<deferred.size();){
        auto& d=deferred[i];
        if(d.kept||d.sprite!=sprite){++i;continue;}
        // A lifetime that provably ended inside the window has nothing to write
        // to (11). One unknown at this address (another thread's lifetime event
        // there) may now be another actor: kept in place, never written (12).
        // Otherwise the write lands, the game's own store.
        const int life=CBMI_Lifetime(sprite,d.incarnation);
        if(life==0){d.kept=true;++i;continue;}
        const auto landing=d;deferred.erase(deferred.begin()+static_cast<std::ptrdiff_t>(i));
        if(life<0)CBMW_CountEnded();
        else own_write(sprite,landing.value,landing.mode,10);
    }
}
uint64_t CBMW_Kept(char* text,size_t size){
    uint64_t count=0;size_t used=0;bool full=false;
    if(size)text[0]=0;
    for(const auto& d:deferred){
        if(!d.kept)continue;
        char item[40];const char* separator=count?", ":"";
        // Mode 1 adds the signed 32-bit value; any other mode sets it.
        const int n=d.mode!=1?std::snprintf(item,sizeof(item),"%sset %u",separator,d.value)
            :d.value<=0x7fffffffu?std::snprintf(item,sizeof(item),"%sadd %u",separator,d.value)
            :std::snprintf(item,sizeof(item),"%ssubtract %u",separator,0u-d.value);
        ++count;
        if(full||n<=0)continue;
        const auto length=static_cast<size_t>(n);
        // Room for this item and a later ", ..." mark; past it the rest is counted, not listed.
        if(used+length+6<=size){std::memcpy(text+used,item,length+1);used+=length;}
        else{if(used+6<=size)std::memcpy(text+used,", ...",6);full=true;}
    }
    return count;
}
