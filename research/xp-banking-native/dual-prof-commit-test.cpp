#include "dual_prof_commit.h"
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
#include <algorithm>
#include "dual_manual_session.h"
namespace {
int checks=0,forwarded=0;
void require(bool yes) {++checks;if(!yes) {std::cerr<<"Failed assertion "<<checks<<"\n";throw std::runtime_error("Proficiency primitive assertion failed");}}
uint32_t get(const void* p,size_t at) {uint32_t n;std::memcpy(&n,static_cast<const unsigned char*>(p)+at,4);return n;}
void put(void* p,size_t at,uint32_t n) {std::memcpy(static_cast<unsigned char*>(p)+at,&n,4);}
int original(void*,void*) {++forwarded;return 73;}
const char owner[]="0123456789abcdef0123456789abcdef";
CBMDS_View view{};
bool refuse_thread=false,fail_decode=false,fail_add=false,fail_remove=false;
void destruct(void* p,unsigned) {delete[] static_cast<unsigned char*>(p);}
uintptr_t effect_vtable[]={reinterpret_cast<uintptr_t>(&destruct)};
void* base_construct(void* base) {std::memset(base,0,0x108);put(base,0x24,100);return base;}
void* decode(void* base) {
    if(fail_decode) throw std::runtime_error("Synthetic factory failure");
    auto* p=new unsigned char[0x158]{};
    const auto v=reinterpret_cast<uintptr_t>(effect_vtable);std::memcpy(p,&v,8);
    std::memcpy(p+8,base,0x108);return p;
}
struct Node {Node* next;Node* previous;void* data;};
Node* pointer(const void* p,size_t offset) {Node* n;std::memcpy(&n,static_cast<const unsigned char*>(p)+offset,8);return n;}
void pointer(void* p,size_t offset,Node* n) {std::memcpy(static_cast<unsigned char*>(p)+offset,&n,8);}
void* add_tail(void* list,void* effect) {
    if(fail_add) throw std::runtime_error("Synthetic AddTail failure");
    auto* n=new Node{nullptr,pointer(list,0x10),effect};
    if(n->previous) n->previous->next=n;else pointer(list,8,n);
    pointer(list,0x10,n);put(list,0x18,get(list,0x18)+1);return n;
}
void remove_at(void* list,void* at) {
    if(fail_remove) throw std::runtime_error("Synthetic RemoveAt failure");
    auto* n=static_cast<Node*>(at);
    if(n->previous) n->previous->next=n->next;else pointer(list,8,n->next);
    if(n->next) n->next->previous=n->previous;else pointer(list,0x10,n->previous);
    put(list,0x18,get(list,0x18)-1);delete n;
}
int query(const void* actor,CBMDS_View* out) {if(reinterpret_cast<uintptr_t>(actor)!=view.sprite)return 0;*out=view;return 1;}
int on_thread() {return refuse_thread?0:1;}
struct Fixture {
    std::array<unsigned char,0x5000> actor{};
    std::vector<void*> effects;
    Fixture() {view={};view.sprite=reinterpret_cast<uintptr_t>(actor.data());view.screen=123;view.session=9;view.incarnation=7;
        view.phase=CBMDS_PREPARING;std::memcpy(view.owner,owner,33);}
    void* add(uint32_t stat,uint32_t amount,uint32_t timing=9,uint32_t opcode=233) {
        unsigned char base[0x108];base_construct(base);put(base,8,opcode);put(base,0x14,amount);put(base,0x18,stat);put(base,0x1C,timing);
        auto* effect=decode(base);add_tail(actor.data()+0x4A00,effect);effects.push_back(effect);return effect;
    }
    void* carrier(uint32_t stat,uint32_t pips) {
        unsigned char base[0x108];base_construct(base);require(CBMDPC_MakeCarrierBase(base,stat,pips,owner)==1);
        auto* effect=decode(base);add_tail(actor.data()+0x4A00,effect);effects.push_back(effect);return effect;
    }
    ~Fixture() {auto* list=actor.data()+0x4A00;while(auto* n=pointer(list,8)){destruct(n->data,1);remove_at(list,n);}}
};
}
int main() {
    CBMDPC_Config config{1,reinterpret_cast<uintptr_t>(&original),reinterpret_cast<uintptr_t>(&query),reinterpret_cast<uintptr_t>(&on_thread),
        reinterpret_cast<uintptr_t>(&base_construct),reinterpret_cast<uintptr_t>(&decode),reinterpret_cast<uintptr_t>(&add_tail),reinterpret_cast<uintptr_t>(&remove_at)};
    require(CBMDPC_Configure(&config)==1);
    require(CBMDPC_Configure(&config)==0);
    for(uint32_t stat=89;stat<=134;++stat) {
        std::array<unsigned char,0x158> effect{};
        std::array<unsigned char,0x5000> actor{};
        require(CBMDPC_MakeCarrierBase(effect.data()+8,stat,3,owner)==1);
        const auto before_effect=effect;
        auto expected=actor;
        require(CBMDPC_ApplyEffect(effect.data(),actor.data())==73);
        require(effect==before_effect);
        require(actor==expected);
        uint32_t actual_stat=0,actual_pips=0;
        require(CBMDPC_ReadCarrier(effect.data(),&actual_stat,&actual_pips)==1);
        require(actual_stat==stat&&actual_pips==3);
        // Copying to another actor/owner does not remove static earned pips.
        std::array<unsigned char,0x5000> clone{};
        require(CBMDPC_ApplyEffect(effect.data(),clone.data())==73);
        require(clone==expected);
        // Dormant carrier is inert and copies without changing another owner.
        for(size_t corrupt : {size_t(0x10),size_t(0x20),size_t(0x24),size_t(0x64),size_t(0x94),size_t(0xA8)}) {
            auto unknown=effect;unknown[corrupt]^=0x80;
            const auto before_actor=actor;
            const auto before_unknown=unknown;
            require(CBMDPC_ApplyEffect(unknown.data(),actor.data())==73);
            require(unknown==before_unknown&&actor==before_actor);
        }
    }
    for(uint32_t old=0;old<=7;++old) for(uint32_t delta=0;delta<=7;++delta) {
        std::array<unsigned char,0x158> effect;
        for(size_t i=0;i<effect.size();++i) effect[i]=static_cast<unsigned char>(i*17);
        put(effect.data(),0x10,233);put(effect.data(),0x20,99);put(effect.data(),0x24,9);
        const uint32_t packed=0xFEED0000|5|(old<<3);
        put(effect.data(),0x1C,packed);
        const auto before=effect;
        CBMDPC_RecordPlan plan{};
        const int result=CBMDPC_PlanSet(effect.data(),99,delta,&plan);
        require(result==(old+delta>7?2:1));
        require(effect==before);
        require(plan.effect==reinterpret_cast<uintptr_t>(effect.data()));
        require(std::memcmp(plan.before,effect.data()+8,0x108)==0);
        auto expected=before;
        put(expected.data(),0x1C,(packed&~uint32_t(0x38))|((old+delta>7?7:old+delta)<<3));
        require(std::memcmp(plan.after,expected.data()+8,0x108)==0);
    }
    std::array<unsigned char,0x158> effect{};
    std::array<unsigned char,0x5000> actor{};
    require(CBMDPC_MakeCarrierBase(effect.data()+8,99,2,owner)==1);
    const auto unchanged=actor;
    std::thread other([&] {require(CBMDPC_ApplyEffect(effect.data(),actor.data())==73);});
    other.join();
    require(actor==unchanged&&CBMDPC_LastStatus()==2);
    require(CBMDPC_MakeCarrierBase(effect.data()+8,88,1,owner)==0);
    require(CBMDPC_MakeCarrierBase(effect.data()+8,89,8,owner)==0);
    require(CBMDPC_MakeCarrierBase(effect.data()+8,89,1,"bad")==0);
    CBMDPC_RecordPlan sentinel{};
    std::memset(&sentinel,0xA5,sizeof sentinel);
    const auto untouched=sentinel;
    require(CBMDPC_PlanSet(effect.data(),99,1,&sentinel)==0);
    require(std::memcmp(&sentinel,&untouched,sizeof sentinel)==0);
    require(forwarded==46*8+1);
    for(bool cancel:{true,false}) {
        Fixture f;
        auto* first=f.add(89,0x100|1|(2<<3));
        auto* last=f.add(89,0x200|2|(1<<3));
        auto* temporary=f.add(89,7,0);
        auto* additive=f.add(89|(1<<16),1);
        auto* unrelated=f.add(0,123,9,42);
        auto* carry1=f.carrier(89,1);f.carrier(99,2);
        std::array<unsigned char,0x158> temp_before{},add_before{},other_before{};
        std::memcpy(temp_before.data(),temporary,0x158);std::memcpy(add_before.data(),additive,0x158);std::memcpy(other_before.data(),unrelated,0x158);
        CBMDPC_Choice rows[]={{89,1}};uint64_t transaction=0;
        const auto actor_before=f.actor;
        require(CBMDPC_ApplyPreview(f.actor.data(),9,8,owner,rows,1,&transaction)==0);
        require(transaction==0&&f.actor==actor_before);
        require(CBMDPC_ApplyPreview(f.actor.data(),9,7,owner,rows,1,&transaction)==1);
        require(transaction!=0&&get(first,0x1C)==0x104&&get(last,0x1C)==0x203);
        require(std::memcmp(temporary,temp_before.data(),0x158)==0&&std::memcmp(additive,add_before.data(),0x158)==0&&std::memcmp(unrelated,other_before.data(),0x158)==0);
        require(get(f.actor.data()+0x4A00,0x18)==8);
        CBMDPC_PreviewRecord r{};uint32_t records=0,created=0,carriers=0;
        while(CBMDPC_GetRecordPlan(transaction,records,&r)) {++records;created+=r.created;carriers+=r.carrier;if(r.created)require(get(r.record.after,0x14)==2);}
        require(records==5&&created==1&&carriers==2);
        uint32_t class_active=0;require(CBMDPC_ReadActiveAllocation(f.actor.data(),89,&class_active)==1&&class_active==3);
        view.phase=CBMDS_PREVIEW;
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,89,4)==1);
        require(get(first,0x1C)==0x104&&get(last,0x1C)==0x204&&get(temporary,0x1C)==7);
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,89,2)==0); // reactivated class floor cannot be removed
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,115,1)==1);
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,115,0)==1); // undo only the new selection
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,115,1)==1);
        require(CBMDPC_ReadActiveAllocation(f.actor.data(),115,&class_active)==1&&class_active==1);
        // Simulate legitimate unrelated updates while the screen is open.
        put(first,0x1C,get(first,0x1C)|0x10000);put(first,0x58,999);
        auto* extra=f.add(12,77,0,42);
        put(carry1,0xCC,0); // generic effect bookkeeping is not an ownership gate
        if(cancel) {
            view.phase=CBMDS_CANCELING;
            put(first,0x1C,(get(first,0x1C)&~uint32_t(7))|6); // stock Cancel rewrites active bits
            require(CBMDPC_Restore(f.actor.data(),9,7,transaction)==1);
            require(get(first,0x1C)==(0x10111)&&get(last,0x1C)==0x20A);
            require(get(first,0x58)==999&&get(extra,0x1C)==77);
            require(get(f.actor.data()+0x4A00,0x18)==8); // original7 + unrelated new1
        } else {
            view.phase=CBMDS_COMMITTING;
            put(last,0x1C,0x204); // accepted native new-class choice remains
            require(CBMDPC_Complete(f.actor.data(),9,7,transaction)==1);
            require(get(last,0x1C)==0x204&&get(extra,0x1C)==77);
            require(get(f.actor.data()+0x4A00,0x18)==8); // initial7 + merge1 + newchoice1 + extra1 - carriers2
        }
        require(CBMDPC_GetRecordPlan(transaction,0,&r)==0);
    }
    for(bool cancel:{true,false}) {
        Fixture f;auto* class_set=f.add(89,1|(3<<3));auto* carry=f.carrier(89,1);
        auto* temporary=f.add(89,7,0);uint64_t id=0;
        const auto actor_before=f.actor;
        require(CBMDPC_BeginActivePreview(f.actor.data(),9,8,owner,&id)==0&&id==0);
        require(CBMDPC_BeginActivePreview(f.actor.data(),9,7,owner,&id)==1&&id!=0);
        require(f.actor==actor_before&&get(class_set,0x1C)==25&&get(carry,0x1C)==1);
        uint32_t value=0,pending=0;
        require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1&&value==4&&pending==1);
        view.phase=CBMDS_PREVIEW;
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,89,2)==1);
        require(get(class_set,0x1C)==26&&get(temporary,0x1C)==7);
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,89,0)==0);
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,7,owner,99,1)==1);
        if(cancel) {
            view.phase=CBMDS_CANCELING;
            require(CBMDPC_Restore(f.actor.data(),9,7,id)==1);
            require(get(class_set,0x1C)==25&&get(f.actor.data()+0x4A00,0x18)==3);
            require(CBMDPC_ReadActiveAllocation(f.actor.data(),99,&value)==1&&value==0);
        } else {
            view.phase=CBMDS_COMMITTING;
            require(CBMDPC_Complete(f.actor.data(),9,7,id)==1);
            require(get(class_set,0x1C)==26&&get(carry,0x1C)==1);
            require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1&&value==4&&pending==1);
            CBMDPC_Choice rows[]={{89,1}};
            require(CBMDPC_PersistDormant(f.actor.data(),9,7,owner,rows,1,&id)==1);
            require(CBMDPC_Complete(f.actor.data(),9,7,id)==1);
            require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1&&value==5&&pending==2);
            require(CBMDPC_ReadActiveAllocation(f.actor.data(),99,&value)==1&&value==1);
        }
    }
    {
        Fixture f;auto* original_set=f.add(89,2|(1<<3));
        CBMDPC_Choice bad[]={{89,7}};uint64_t id=0;
        require(CBMDPC_ApplyPreview(f.actor.data(),9,7,owner,bad,1,&id)==0);
        require(id==0&&get(original_set,0x1C)==10);
        CBMDPC_Choice create[]={{99,1}};fail_decode=true;
        require(CBMDPC_ApplyPreview(f.actor.data(),9,7,owner,create,1,&id)==0);
        fail_decode=false;require(id==0&&get(original_set,0x1C)==10&&get(f.actor.data()+0x4A00,0x18)==1);
        refuse_thread=true;require(CBMDPC_ApplyPreview(f.actor.data(),9,7,owner,create,1,&id)==0);refuse_thread=false;
    }
    {
        Fixture f;auto* older=f.add(89,7<<3);auto* winning=f.add(89,1|(1<<3));f.add(89,7,0);f.carrier(89,1);
        uint32_t value=0,pending=0;require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1);
        require(value==2&&pending==1); // earlier SET7 and tempSET7 are not the class base
        view.phase=CBMDS_COMMITTING;CBMDPC_Choice rows[]={{89,1},{99,2}};uint64_t id=0;
        require(CBMDPC_PersistDormant(f.actor.data(),9,7,owner,rows,2,&id)==1);
        require(get(older,0x1C)==56&&get(winning,0x1C)==9);
        require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1&&value==3&&pending==2);
        require(CBMDPC_Complete(f.actor.data(),9,7,id)==1);
        CBMDPC_Choice next[]={{89,1}};
        require(CBMDPC_PersistDormant(f.actor.data(),9,7,owner,next,1,&id)==1);
        require(CBMDPC_Complete(f.actor.data(),9,7,id)==1);
        require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1&&value==4&&pending==3);
        view.phase=CBMDS_PREPARING;
        require(CBMDPC_ApplyPreview(f.actor.data(),9,7,owner,nullptr,0,&id)==1);
        require(get(older,0x1C)==7&&get(winning,0x1C)==4); // ignored earlier7 saturates, effective last4 is exact
        view.phase=CBMDS_COMMITTING;
        require(CBMDPC_Complete(f.actor.data(),9,7,id)==1);
        require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==1&&pending==0);
        require(CBMDPC_ReadOldAllocation(f.actor.data(),99,&value,&pending)==1&&pending==0);
    }
    {
        Fixture f;auto* known=f.carrier(89,1);uint32_t value=123,pending=456;
        put(known,0x64,2); // preserve unknown future schema, never guess its accounting
        require(CBMDPC_ReadOldAllocation(f.actor.data(),89,&value,&pending)==0&&value==123&&pending==456);
        uint64_t id=0;require(CBMDPC_ApplyPreview(f.actor.data(),9,7,owner,nullptr,0,&id)==0&&id==0);
        require(get(known,0x64)==2&&get(f.actor.data()+0x4A00,0x18)==1);
    }
    {
        Fixture f;view.phase=CBMDS_COMMITTING;CBMDPC_Choice rows[]={{99,1}};uint64_t id=0;
        fail_add=true;require(CBMDPC_PersistDormant(f.actor.data(),9,7,owner,rows,1,&id)==-1);fail_add=false;
        require(id!=0&&get(f.actor.data()+0x4A00,0x18)==0);
        CBMDPC_PreviewRecord r{};require(CBMDPC_GetRecordPlan(id,0,&r)==1&&r.created&&r.carrier&&r.node==0);
        require(CBMDPC_Complete(f.actor.data(),9,7,id)==0); // uncertainty never replays
        uint64_t retry=0;require(CBMDPC_PersistDormant(f.actor.data(),9,7,owner,rows,1,&retry)==0&&retry==0);
        // Pointer reuse with a different native incarnation is not the old owner.
        view.incarnation=8;require(CBMDPC_PersistDormant(f.actor.data(),9,8,owner,rows,1,&retry)==1);
        require(CBMDPC_Complete(f.actor.data(),9,8,retry)==1);
    }
    {
        Fixture f;auto* removed=f.add(89,1|(3<<3));auto* survivor=f.add(99,2|(1<<3));
        view.incarnation=9; // new lifetime after the preceding quarantined fixture
        uint64_t id=0;require(CBMDPC_BeginActivePreview(f.actor.data(),9,9,owner,&id)==1);
        // A real external removal invalidates a captured pointer. Keeping the
        // remaining choice unchanged is required before touching old snapshots.
        auto* first=pointer(f.actor.data()+0x4A00,8);
        remove_at(f.actor.data()+0x4A00,first);destruct(removed,1);
        view.phase=CBMDS_PREVIEW;const auto before=f.actor;
        require(CBMDPC_SetActiveOwned(f.actor.data(),9,9,owner,99,3)==0);
        require(f.actor==before&&get(survivor,0x1C)==10);
        CBMDPC_PreviewRecord r{};require(CBMDPC_GetRecordPlan(id,0,&r)==1);
        view.phase=CBMDS_CANCELING;
        require(CBMDPC_Restore(f.actor.data(),9,9,id)==0); // recovery, not guessing replacement identity
    }
    std::cout<<checks<<" native proficiency primitive assertions passed; no native game launched.\n";
}
