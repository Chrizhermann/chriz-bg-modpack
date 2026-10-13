#include "dual_prof_commit.h"
#include <cstring>
#include <array>
#include <vector>
#include <unordered_set>
#include <unordered_map>
#include <memory>
#include <algorithm>
#include "dual_manual_session.h"
#ifdef _WIN32
#define NOMINMAX
#include <Windows.h>
#endif
namespace {
using Apply = int(*)(void*,void*);
Apply original=nullptr;
bool configured=false;
CBMDPC_Config config{};
uint32_t engine_thread=0;
int status=0;
constexpr unsigned char marker[8]={'C','B','M','D','P','R','F',0};
uint32_t thread_id() {
#ifdef _WIN32
    return GetCurrentThreadId();
#else
    return 1;
#endif
}
uint32_t get(const void* p,size_t at) {uint32_t n;std::memcpy(&n,static_cast<const unsigned char*>(p)+at,4);return n;}
void put(void* p,size_t at,uint32_t n) {std::memcpy(static_cast<unsigned char*>(p)+at,&n,4);}
bool hex32(const unsigned char* p) {
    for(size_t i=0;i<32;++i) if(!((p[i]>='0'&&p[i]<='9')||(p[i]>='a'&&p[i]<='f'))) return false;
    return true;
}
bool valid_stat(uint32_t n) {return n>=89&&n<=134;}
bool carrier_family(const void* p) {return get(p,0x10)==233&&get(p,0x20)==0xFFFF
    &&std::memcmp(static_cast<const unsigned char*>(p)+0x94,marker,8)==0;}
using Query=int(*)(const void*,CBMDS_View*);
using Thread=int(*)();
using Construct=void*(*)(void*);
using Decode=void*(*)(void*);
using Add=void*(*)(void*,void*);
using Remove=void(*)(void*,void*);
struct Entry {uintptr_t node,effect;};
struct Transaction {
    void* actor;uint64_t session,incarnation;char owner[33];bool applied=false,uncertain=false,dormant=false;
    std::vector<CBMDPC_PreviewRecord> records;
};
std::unordered_map<uint64_t,std::unique_ptr<Transaction>> transactions;
uint64_t next_transaction=1;
bool scope(const void* actor,uint64_t session,uint64_t incarnation,const char* owner,uint32_t phase) {
    if(!config.session_query||!config.is_engine_thread||!owner||std::strlen(owner)!=32
       ||!reinterpret_cast<Thread>(config.is_engine_thread)()) return false;
    CBMDS_View v{};
    return reinterpret_cast<Query>(config.session_query)(actor,&v)&&v.sprite==reinterpret_cast<uintptr_t>(actor)
        &&v.session==session&&v.incarnation==incarnation&&v.phase==phase&&std::memcmp(v.owner,owner,33)==0;
}
std::vector<Entry> entries(const void* actor) {
    const auto* list=static_cast<const unsigned char*>(actor)+0x4A00;
    uintptr_t node=0,previous=0;std::memcpy(&node,list+8,8);
    std::vector<Entry> result;std::unordered_set<uintptr_t> seen;
    while(node) {
        if(!seen.insert(node).second) throw 1;
        uintptr_t effect=0,next=0,back=0;
        std::memcpy(&next,reinterpret_cast<void*>(node),8);
        std::memcpy(&back,reinterpret_cast<void*>(node+8),8);
        std::memcpy(&effect,reinterpret_cast<void*>(node+0x10),8);
        if(!effect||back!=previous) throw 1;
        result.push_back({node,effect});previous=node;node=next;
    }
    uintptr_t tail=0;std::memcpy(&tail,list+0x10,8);
    if(result.size()!=get(list,0x18)||tail!=previous) throw 1;
    return result;
}
void destroy(uintptr_t effect) {
    uintptr_t vtable=0,fn=0;std::memcpy(&vtable,reinterpret_cast<void*>(effect),8);
    std::memcpy(&fn,reinterpret_cast<void*>(vtable),8);
    reinterpret_cast<void(*)(void*,unsigned)>(fn)(reinterpret_cast<void*>(effect),1);
}
bool present(const std::vector<Entry>& all,const CBMDPC_PreviewRecord& r) {
    return std::any_of(all.begin(),all.end(),[&](const Entry& e){return e.node==r.node&&e.effect==r.record.effect;});
}
bool allocation(const void* p,uint32_t stat) {return get(p,0x10)==233&&get(p,0x20)==stat&&get(p,0x24)==9;}
}
CBMDPC_API int CBMDPC_Configure(const CBMDPC_Config* c) {
    if(configured||!c||c->abi!=1||(!c->original_apply&&(!c->session_query||!c->is_engine_thread
       ||!c->base_construct||!c->decode_base||!c->add_tail||!c->remove_at))) return 0;
    config=*c;original=reinterpret_cast<Apply>(c->original_apply);configured=true;engine_thread=thread_id();status=0;return 1;
}
CBMDPC_API int CBMDPC_ReadCarrier(const void* p,uint32_t* stat,uint32_t* pips) {
    if(!p||!stat||!pips) return 0;
    const auto* b=static_cast<const unsigned char*>(p);
    if(get(p,0x10)!=233||get(p,0x20)!=0xFFFF||get(p,0x24)!=9||get(p,0x64)!=1
       ||std::memcmp(b+0x94,marker,8)||!hex32(b+0xA8)
       ||!valid_stat(get(p,0x60))||get(p,0x1C)<1||get(p,0x1C)>7) return 0;
    *stat=get(p,0x60);*pips=get(p,0x1C);return 1;
}
CBMDPC_API int CBMDPC_ApplyEffect(void* effect,void* sprite) {
    if(!original) {status=1;return 0;}
    uint32_t stat=0,pips=0;
    if(!sprite||!CBMDPC_ReadCarrier(effect,&stat,&pips)) return original(effect,sprite);
    if(thread_id()!=engine_thread) {status=2;return original(effect,sprite);}
    // Dormant earned deltas remain inert until the owned reactivation preview.
    // A live bonus would be baked into future native SetActiveProficiency.
    status=0;return original(effect,sprite);
}
CBMDPC_API int CBMDPC_ReadOldAllocation(const void* actor,uint32_t stat,uint32_t* value,uint32_t* pending) {
    if(!actor||!value||!pending||!valid_stat(stat)||thread_id()!=engine_thread) return 0;
    uint32_t base=0,added=0;
    try {
        for(const auto& e:entries(actor)) {
            const auto* p=reinterpret_cast<const void*>(e.effect);uint32_t carrier_stat=0,pips=0;
            if(allocation(p,stat)) base=(get(p,0x1C)>>3)&7;
            else if(carrier_family(p)) {
                if(!CBMDPC_ReadCarrier(p,&carrier_stat,&pips)) {status=9;return 0;}
                if(carrier_stat==stat) {added+=pips;if(added>7) return 0;}
            }
        }
    } catch(...) {return 0;}
    if(base+added>7) return 0;
    *value=base+added;*pending=added;return 1;
}
CBMDPC_API int CBMDPC_ReadActiveAllocation(const void* actor,uint32_t stat,uint32_t* value) {
    if(!actor||!value||!valid_stat(stat)||thread_id()!=engine_thread) return 0;
    uint32_t result=0;
    try {for(const auto& e:entries(actor)) if(allocation(reinterpret_cast<void*>(e.effect),stat)) result=get(reinterpret_cast<void*>(e.effect),0x1C)&7;}
    catch(...) {return 0;}
    *value=result;return 1;
}
CBMDPC_API int CBMDPC_MakeCarrierBase(void* p,uint32_t stat,uint32_t pips,const char* owner) {
    if(!p||!owner||!valid_stat(stat)||pips<1||pips>7||std::strlen(owner)!=32
       ||!hex32(reinterpret_cast<const unsigned char*>(owner))) return 0;
    // Base is native object+8; constructor defaults keep generic fields valid.
    put(p,0x08,233);put(p,0x0C,1);put(p,0x14,pips);put(p,0x18,0xFFFF);
    put(p,0x1C,9);put(p,0x58,stat);put(p,0x5C,1);
    std::memcpy(static_cast<unsigned char*>(p)+0x8C,marker,8);
    std::memcpy(static_cast<unsigned char*>(p)+0xA0,owner,32);
    return 1;
}
CBMDPC_API int CBMDPC_PlanSet(const void* p,uint32_t stat,uint32_t delta,CBMDPC_RecordPlan* out) {
    if(!p||!out||!valid_stat(stat)||delta>7||get(p,0x10)!=233||get(p,0x20)!=stat||get(p,0x24)!=9) return 0;
    CBMDPC_RecordPlan plan{};plan.effect=reinterpret_cast<uintptr_t>(p);
    std::memcpy(plan.before,static_cast<const unsigned char*>(p)+8,0x108);
    std::memcpy(plan.after,plan.before,0x108);
    const uint32_t before=get(p,0x1C),old=(before>>3)&7;
    const uint32_t after=old+delta>7?7:old+delta;
    put(plan.after,0x14,(before&~uint32_t(0x38))|(after<<3));
    *out=plan;return old+delta>7?2:1;
}
CBMDPC_API int CBMDPC_LastStatus() {return status;}

CBMDPC_API int CBMDPC_BeginActivePreview(void* actor,uint64_t session,uint64_t incarnation,
 const char* owner,uint64_t* output) {
    if(!actor||!output||!scope(actor,session,incarnation,owner,CBMDS_PREPARING)
       ||!config.base_construct||!config.decode_base||!config.add_tail||!config.remove_at) {status=3;return 0;}
    for(const auto& existing:transactions) if(existing.second->actor==actor&&existing.second->incarnation==incarnation) {status=4;return 0;}
    try {
        auto t=std::make_unique<Transaction>();t->actor=actor;t->session=session;t->incarnation=incarnation;
        std::memcpy(t->owner,owner,33);
        const auto all=entries(actor);t->records.reserve(all.size());
        for(const auto& e:all) {
            auto* effect=reinterpret_cast<void*>(e.effect);const auto stat=get(effect,0x20);
            if(!valid_stat(stat)||!allocation(effect,stat)) continue;
            CBMDPC_PreviewRecord r{};r.node=e.node;r.record.effect=e.effect;
            std::memcpy(r.record.before,reinterpret_cast<void*>(e.effect+8),0x108);
            std::memcpy(r.record.after,r.record.before,0x108);r.start_active=get(effect,0x1C)&7;
            t->records.push_back(r);
        }
        const uint64_t serial=next_transaction++;if(!serial) {status=6;return 0;}
        t->applied=true;transactions.emplace(serial,std::move(t));*output=serial;status=0;return 1;
    } catch(...) {status=6;return 0;}
}

CBMDPC_API int CBMDPC_ApplyPreview(void* actor,uint64_t session,uint64_t incarnation,
 const char* owner,const CBMDPC_Choice* rows,uint32_t count,uint64_t* output) {
    if(!actor||!output||(count&&!rows)||!scope(actor,session,incarnation,owner,CBMDS_PREPARING)
       ||!config.base_construct||!config.decode_base||!config.add_tail||!config.remove_at) {status=3;return 0;}
    for(const auto& existing:transactions) if(existing.second->actor==actor&&existing.second->incarnation==incarnation) {status=4;return 0;}
    std::array<uint32_t,46> delta{},last_old{};std::array<bool,46> found{};
    auto t=std::make_unique<Transaction>();t->actor=actor;t->session=session;t->incarnation=incarnation;
    std::memcpy(t->owner,owner,33);
    try {
        for(uint32_t i=0;i<count;++i) {
            if(!valid_stat(rows[i].stat)||rows[i].delta>7) {status=5;return 0;}
            auto& value=delta[rows[i].stat-89];value+=rows[i].delta;
            if(value>7) {status=5;return 0;}
        }
        const auto all=entries(actor);
        t->records.reserve(all.size()+46);
        for(const auto& e:all) {
            const auto* p=reinterpret_cast<const void*>(e.effect);uint32_t stat=0,pips=0;
            CBMDPC_PreviewRecord record{};record.node=e.node;record.record.effect=e.effect;
            if(CBMDPC_ReadCarrier(p,&stat,&pips)) {
                delta[stat-89]+=pips;if(delta[stat-89]>7) {status=5;return 0;}
                record.carrier=1;
            } else {
                if(carrier_family(p)) {status=9;return 0;}
                stat=get(p,0x20);
                if(!valid_stat(stat)||!allocation(p,stat)) continue;
                found[stat-89]=true;last_old[stat-89]=(get(p,0x1C)>>3)&7;
            }
            std::memcpy(record.record.before,reinterpret_cast<void*>(e.effect+8),0x108);
            std::memcpy(record.record.after,record.record.before,0x108);t->records.push_back(record);
        }
        for(size_t i=0;i<46;++i) if(found[i]&&last_old[i]+delta[i]>7) {status=5;return 0;}
        for(auto& r:t->records) if(!r.carrier) {
            const auto stat=get(r.record.before,0x18),packed=get(r.record.before,0x14);
            const auto old=std::min(uint32_t(7),((packed>>3)&7)+delta[stat-89]);
            put(r.record.after,0x14,(packed&~uint32_t(0x3F))|std::max(packed&7,old));
            r.start_active=std::max(packed&7,old);
        }
        // Allocate every new effect before changing a live record/list. A
        // factory failure cannot leave a half-written existing allocation.
        for(size_t i=0;i<46;++i) if(!found[i]&&delta[i]) {
            alignas(8) unsigned char base[0x108]{};
            reinterpret_cast<Construct>(config.base_construct)(base);
            CBMDPC_MakeCarrierBase(base,static_cast<uint32_t>(89+i),delta[i],owner);
            put(base,0x18,static_cast<uint32_t>(89+i)); // plain native class SET
            std::memcpy(base+0x8C,"CBMDPCM",8);
            auto* created=reinterpret_cast<Decode>(config.decode_base)(base);
            if(!created) throw 1;
            CBMDPC_PreviewRecord r{};r.created=1;r.record.effect=reinterpret_cast<uintptr_t>(created);
            std::memcpy(r.record.after,static_cast<unsigned char*>(created)+8,0x108);r.start_active=delta[i];t->records.push_back(r);
        }
    } catch(...) {
        for(const auto& r:t->records) if(r.created&&!r.node) destroy(r.record.effect);
        status=6;return 0;
    }
    const uint64_t serial=next_transaction++;
    if(!serial) {status=6;return 0;}
    Transaction* active=t.get();transactions.emplace(serial,std::move(t));*output=serial;
    try {
        for(auto& r:active->records) if(r.created) {
            r.node=reinterpret_cast<uintptr_t>(reinterpret_cast<Add>(config.add_tail)(
                static_cast<unsigned char*>(actor)+0x4A00,reinterpret_cast<void*>(r.record.effect)));
            if(!r.node) throw 1;
        }
        for(const auto& r:active->records) if(!r.carrier&&!r.created)
            put(reinterpret_cast<void*>(r.record.effect),0x1C,get(r.record.after,0x14));
        active->applied=true;status=0;return 1;
    } catch(...) {active->uncertain=true;status=7;return -1;}
}
CBMDPC_API int CBMDPC_GetRecordPlan(uint64_t id,uint32_t index,CBMDPC_PreviewRecord* out) {
    const auto t=transactions.find(id);
    if(!out||thread_id()!=engine_thread||t==transactions.end()||index>=t->second->records.size()) return 0;
    *out=t->second->records[index];return 1;
}
CBMDPC_API int CBMDPC_Restore(void* actor,uint64_t session,uint64_t incarnation,uint64_t id) {
    const auto it=transactions.find(id);
    if(it==transactions.end()) {status=8;return 0;}
    auto& t=*it->second;
    if(t.actor!=actor||t.session!=session||t.incarnation!=incarnation||t.uncertain||t.dormant
       ||!scope(actor,session,incarnation,t.owner,CBMDS_CANCELING)) {status=3;return 0;}
    bool mutating=false;
    try {
        const auto all=entries(actor);
        for(const auto& r:t.records) {
            if(!r.node) continue;
            if(!present(all,r)) throw 1;
            if(!r.carrier&&!allocation(reinterpret_cast<void*>(r.record.effect),get(r.record.after,0x18))) throw 1;
            if(r.created&&(std::memcmp(reinterpret_cast<void*>(r.record.effect+0x94),"CBMDPCM",8)
                ||std::memcmp(reinterpret_cast<void*>(r.record.effect+0xA8),t.owner,32))) throw 1;
        }
        mutating=true;
        for(const auto& r:t.records) if(!r.carrier&&!r.created) {
            auto* p=reinterpret_cast<void*>(r.record.effect);
            put(p,0x1C,(get(p,0x1C)&~uint32_t(0x3F))|(get(r.record.before,0x14)&0x3F));
        }
        for(auto& r:t.records) if(r.created) {
            if(r.node) reinterpret_cast<Remove>(config.remove_at)(static_cast<unsigned char*>(actor)+0x4A00,reinterpret_cast<void*>(r.node));
            r.node=0;destroy(r.record.effect);r.record.effect=0;
        }
        transactions.erase(it);status=0;return 1;
    } catch(...) {t.uncertain=mutating;status=7;return mutating?-1:0;}
}
CBMDPC_API int CBMDPC_Complete(void* actor,uint64_t session,uint64_t incarnation,uint64_t id) {
    const auto it=transactions.find(id);
    if(it==transactions.end()) {status=8;return 0;}
    auto& t=*it->second;
    if(t.actor!=actor||t.session!=session||t.incarnation!=incarnation||!t.applied||t.uncertain
       ||!scope(actor,session,incarnation,t.owner,CBMDS_COMMITTING)) {status=3;return 0;}
    if(t.dormant) {transactions.erase(it);status=0;return 1;}
    bool mutating=false;
    try {
        const auto all=entries(actor);
        for(const auto& r:t.records) if(r.carrier) {
            uint32_t stat=0,pips=0;
            if(!present(all,r)||!CBMDPC_ReadCarrier(reinterpret_cast<void*>(r.record.effect),&stat,&pips)
               ||stat!=get(r.record.before,0x58)||pips!=get(r.record.before,0x14)
               ||std::memcmp(reinterpret_cast<void*>(r.record.effect+0xA8),r.record.before+0xA0,32)) throw 1;
        }
        mutating=true;
        for(auto& r:t.records) if(r.carrier) {
            reinterpret_cast<Remove>(config.remove_at)(static_cast<unsigned char*>(actor)+0x4A00,reinterpret_cast<void*>(r.node));
            r.node=0;destroy(r.record.effect);r.record.effect=0;
        }
        transactions.erase(it);status=0;return 1;
    } catch(...) {t.uncertain=mutating;status=7;return mutating?-1:0;}
}
CBMDPC_API int CBMDPC_PersistDormant(void* actor,uint64_t session,uint64_t incarnation,
 const char* owner,const CBMDPC_Choice* rows,uint32_t count,uint64_t* output) {
    if(!actor||!output||(count&&!rows)||!scope(actor,session,incarnation,owner,CBMDS_COMMITTING)
       ||!config.base_construct||!config.decode_base||!config.add_tail) {status=3;return 0;}
    for(const auto& existing:transactions) if(existing.second->actor==actor&&existing.second->incarnation==incarnation) {status=4;return 0;}
    std::array<uint32_t,46> delta{};
    auto t=std::make_unique<Transaction>();t->actor=actor;t->session=session;t->incarnation=incarnation;t->dormant=true;
    std::memcpy(t->owner,owner,33);
    try {
        t->records.reserve(46);
        for(uint32_t i=0;i<count;++i) {
            if(!valid_stat(rows[i].stat)||rows[i].delta>7) {status=5;return 0;}
            auto& n=delta[rows[i].stat-89];n+=rows[i].delta;if(n>7) {status=5;return 0;}
        }
        for(size_t i=0;i<46;++i) if(delta[i]) {
            uint32_t value=0,pending=0;
            if(!CBMDPC_ReadOldAllocation(actor,static_cast<uint32_t>(89+i),&value,&pending)||value+delta[i]>7) {status=5;return 0;}
        }
        for(size_t i=0;i<46;++i) if(delta[i]) {
            alignas(8) unsigned char base[0x108]{};
            reinterpret_cast<Construct>(config.base_construct)(base);
            CBMDPC_MakeCarrierBase(base,static_cast<uint32_t>(89+i),delta[i],owner);
            auto* created=reinterpret_cast<Decode>(config.decode_base)(base);if(!created) throw 1;
            CBMDPC_PreviewRecord r{};r.created=1;r.carrier=1;r.record.effect=reinterpret_cast<uintptr_t>(created);
            std::memcpy(r.record.after,static_cast<unsigned char*>(created)+8,0x108);t->records.push_back(r);
        }
    } catch(...) {
        for(const auto& r:t->records) if(r.created&&!r.node) destroy(r.record.effect);
        status=6;return 0;
    }
    const uint64_t serial=next_transaction++;
    if(!serial) {status=6;return 0;}
    Transaction* active=t.get();transactions.emplace(serial,std::move(t));*output=serial;
    try {
        for(auto& r:active->records) {
            r.node=reinterpret_cast<uintptr_t>(reinterpret_cast<Add>(config.add_tail)(
                static_cast<unsigned char*>(actor)+0x4A00,reinterpret_cast<void*>(r.record.effect)));
            if(!r.node) throw 1;
        }
        active->applied=true;status=0;return 1;
    } catch(...) {active->uncertain=true;status=7;return -1;}
}
CBMDPC_API int CBMDPC_SetActiveOwned(void* actor,uint64_t session,uint64_t incarnation,
 const char* owner,uint32_t stat,uint32_t requested) {
    if(!valid_stat(stat)||requested>7||!scope(actor,session,incarnation,owner,CBMDS_PREVIEW)) {status=3;return 0;}
    Transaction* t=nullptr;
    for(auto& pair:transactions) if(pair.second->actor==actor&&pair.second->session==session
        &&pair.second->incarnation==incarnation) {t=pair.second.get();break;}
    if(!t||!t->applied||t->uncertain||t->dormant||std::memcmp(owner,t->owner,33)) {status=4;return 0;}
    bool mutating=false;uintptr_t created=0;
    try {
        auto all=entries(actor);std::vector<Entry> matching;
        // Native effects may remove/replace list entries during recalculation.
        // Check the live list before dereferencing any captured after-snapshot
        // pointer; otherwise an ordinary later UI choice could read freed data.
        for(const auto& r:t->records) {
            if(!present(all,r)) throw 1;
            if(!r.carrier&&!allocation(reinterpret_cast<void*>(r.record.effect),get(r.record.after,0x18))) throw 1;
        }
        for(const auto& e:all) if(allocation(reinterpret_cast<void*>(e.effect),stat)) matching.push_back(e);
        t->records.reserve(t->records.size()+matching.size()+1);
        for(const auto& e:matching) {
            if(std::any_of(t->records.begin(),t->records.end(),[&](const CBMDPC_PreviewRecord& r){return r.node==e.node&&r.record.effect==e.effect;})) continue;
            CBMDPC_PreviewRecord r{};r.node=e.node;r.record.effect=e.effect;
            std::memcpy(r.record.before,reinterpret_cast<void*>(e.effect+8),0x108);
            std::memcpy(r.record.after,r.record.before,0x108);r.start_active=get(r.record.before,0x14)&7;t->records.push_back(r);
        }
        uint32_t minimum=0;
        if(!matching.empty()) {
            const auto& last=matching.back();
            for(const auto& r:t->records) if(r.node==last.node&&r.record.effect==last.effect) {minimum=r.start_active;break;}
        }
        if(requested<minimum) {status=5;return 0;}
        if(matching.empty()&&requested) {
            alignas(8) unsigned char base[0x108]{};reinterpret_cast<Construct>(config.base_construct)(base);
            CBMDPC_MakeCarrierBase(base,stat,requested,owner);put(base,0x18,stat);std::memcpy(base+0x8C,"CBMDPCM",8);
            created=reinterpret_cast<uintptr_t>(reinterpret_cast<Decode>(config.decode_base)(base));if(!created) throw 1;
            CBMDPC_PreviewRecord r{};r.created=1;r.record.effect=created;
            std::memcpy(r.record.after,reinterpret_cast<void*>(created+8),0x108);t->records.push_back(r);
            mutating=true;
            auto& added=t->records.back();added.node=reinterpret_cast<uintptr_t>(reinterpret_cast<Add>(config.add_tail)(
                static_cast<unsigned char*>(actor)+0x4A00,reinterpret_cast<void*>(created)));
            if(!added.node) throw 1;
        } else {
            mutating=true;
            for(const auto& e:matching) put(reinterpret_cast<void*>(e.effect),0x1C,
                (get(reinterpret_cast<void*>(e.effect),0x1C)&~uint32_t(7))|requested);
            for(auto& r:t->records) if(!r.carrier&&get(r.record.after,0x18)==stat)
                put(r.record.after,0x14,get(reinterpret_cast<void*>(r.record.effect),0x1C));
        }
        status=0;return 1;
    } catch(...) {
        if(!mutating&&created) destroy(created);
        if(mutating) t->uncertain=true;
        status=7;return mutating?-1:0;
    }
}
