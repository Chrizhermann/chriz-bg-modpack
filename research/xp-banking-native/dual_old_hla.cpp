#include "dual_old_hla.h"
#include <array>
#include <cstring>
#include <cmath>
#include <limits>
#include <memory>
#include <unordered_map>
#include <algorithm>
#include <vector>
#include <unordered_set>
#include <string>
#include <stdexcept>
#include "dual_manual_session.h"
namespace {
CBMDHLA_Config config{};bool configured=false;int status=0;uint64_t next_id=1;
using Thread=int(*)();
using Num=int(*)(void*,void*,void*,void*,uint8_t*);
using SetLevel=void(*)(void*,uint8_t,uint8_t,uint8_t);
using ClassString=void*(*)(void*,void*,uint8_t,uint32_t);
using GetAt=void*(*)(void*,const void*,const void*);
using Scan=int(*)(const char*,const char*,...);
using DestroyString=void(*)(void*);
using Catalog=void*(*)(void*,void*);
using Complete=void(*)(void*,void*);
using Construct=void*(*)(void*);
using StringChars=void*(*)(void*,const char*);
using ResRefString=void*(*)(void*,const void*);
using Check=int(*)(void*,void*,void*);
template<class T>T read(const void* p,size_t offset) {T value;std::memcpy(&value,static_cast<const unsigned char*>(p)+offset,sizeof value);return value;}
template<class T>void write(void* p,size_t offset,T value) {std::memcpy(static_cast<unsigned char*>(p)+offset,&value,sizeof value);}
bool thread() {return configured&&reinterpret_cast<Thread>(config.is_engine_thread)();}
struct Session {void* catalog=nullptr;uint32_t rows=0,points=0,capped=0;uint8_t flags=0;};
std::unordered_map<uint64_t,std::unique_ptr<Session>> sessions;
uintptr_t session_query=0;uint64_t next_projection=1;
struct Projection {CBMDS_View scope;uint64_t token;std::vector<std::string> effects;};
std::unordered_map<uintptr_t,Projection> projections;
struct NativeRow {
    alignas(8) std::array<unsigned char,0x40> bytes{};
    NativeRow(){reinterpret_cast<Construct>(config.ability_construct)(bytes.data());}
    ~NativeRow(){for(size_t off:{size_t(0x10),size_t(0x28),size_t(0x30),size_t(0x38)})reinterpret_cast<DestroyString>(config.cstring_destroy)(bytes.data()+off);}
    NativeRow(const NativeRow&)=delete;
    void set(const CBMDHLA_Row& value) {
        if(!value.effect||!value.prerequisite||!value.excluded_by||!value.alignment)throw 1;
        std::memcpy(bytes.data(),value.icon,8);write(bytes.data(),8,value.name_strref);
        write(bytes.data(),0x18,value.min_level);write(bytes.data(),0x1C,value.max_level);write(bytes.data(),0x20,value.max_rank);
        const char* strings[]={value.effect,value.prerequisite,value.excluded_by,value.alignment};
        size_t offsets[]={0x10,0x28,0x30,0x38};
        for(size_t i=0;i<4;++i)reinterpret_cast<StringChars>(config.cstring_assign_chars)(bytes.data()+offsets[i],strings[i]);
    }
};
struct ListNode {ListNode* next;ListNode* previous;const void* effect;};
struct EligibilityActor {
    alignas(8) std::array<unsigned char,0x4A60> bytes{};
    std::array<uintptr_t,5> vtable{};
    std::vector<ListNode> nodes;
    std::vector<std::array<unsigned char,0x40>> markers;
    EligibilityActor(const void* actor,const CBMDHLA_Row* pending,uint32_t count) {
        vtable[4]=config.get_ai_type;write(bytes.data(),0,vtable.data());
        std::memcpy(bytes.data()+0x30,static_cast<const unsigned char*>(actor)+0x30,0x18);
        std::vector<const void*> effects;std::unordered_set<uintptr_t> seen;
        auto at=read<uintptr_t>(actor,0x4A08);
        while(at) {
            if(!seen.insert(at).second)throw 1;
            auto* effect=read<const void*>(reinterpret_cast<void*>(at),0x10);if(!effect)throw 1;
            effects.push_back(effect);at=read<uintptr_t>(reinterpret_cast<void*>(at),0);
        }
        markers.resize(count);
        for(uint32_t i=0;i<count;++i) {
            const char* effect=pending[i].effect;
            if(!effect||std::strlen(effect)<3)throw 1;
            // Exact native marker codec: resource is effect.Right(length-3),
            // converted by the real CResRef CString constructor.
            uintptr_t suffix=0;reinterpret_cast<StringChars>(config.cstring_construct_chars)(&suffix,effect+3);
            try {reinterpret_cast<ResRefString>(config.resref_construct_cstring)(markers[i].data()+0x30,&suffix);}
            catch(...) {reinterpret_cast<DestroyString>(config.cstring_destroy)(&suffix);throw;}
            reinterpret_cast<DestroyString>(config.cstring_destroy)(&suffix);
            write<uint32_t>(markers[i].data(),0x10,313);effects.push_back(markers[i].data());
        }
        nodes.resize(effects.size());
        for(size_t i=0;i<nodes.size();++i)nodes[i]={i+1<nodes.size()?&nodes[i+1]:nullptr,i?&nodes[i-1]:nullptr,effects[i]};
        write(bytes.data(),0x4A08,nodes.empty()?nullptr:nodes.data());
    }
};
void close_catalog(void* catalog) {
    if(!catalog)return;
    // Exact native cleanup branch: selection count0, so no actor is accessed
    // and no ability can fire. The helper frees every CAbilityData and array.
    alignas(8) std::array<unsigned char,0xA10> screen{};
    write(screen.data(),0x9E8,catalog);
    reinterpret_cast<Complete>(config.complete_abilities)(screen.data(),nullptr);
}
int64_t native_term(float value) {
    // Match native MULSS/SUBSS/CVTTSS2SI precision and truncation. Invalid or
    // overflowing native signed counts cannot describe a usable entitlement.
    if(!std::isfinite(value)||static_cast<double>(value)<std::numeric_limits<int32_t>::min()
       ||static_cast<double>(value)>std::numeric_limits<int32_t>::max())throw 1;
    return static_cast<int32_t>(value);
}
uint32_t uncapped(uint8_t cls,uint8_t before,uint8_t after) {
    uintptr_t row=0;bool row_constructed=false;
    try {
        reinterpret_cast<ClassString>(config.class_string)(reinterpret_cast<void*>(config.rules),&row,cls,0x4000);
        row_constructed=true;
        uint32_t first=0,change=0;float rate=0,new_rate=0;
        uintptr_t columns[]={config.first_level,config.rate,config.change_level,config.new_rate};
        void* values[]={&first,&rate,&change,&new_rate};
        for(size_t i=0;i<4;++i) {
            auto* cell=reinterpret_cast<GetAt>(config.get_at)(reinterpret_cast<void*>(config.rules+0x3008),
                reinterpret_cast<void*>(columns[i]),&row);
            if(!cell)throw 1;
            auto* text=read<const char*>(cell,0);if(!text)throw 1;
            if(reinterpret_cast<Scan>(config.scan)(text,(i%2)?"%f":"%u",values[i])!=1)throw 1;
        }
        reinterpret_cast<DestroyString>(config.cstring_destroy)(&row);row_constructed=false;
        int64_t total=0;
        if(after>=first) {
            const uint32_t levels=before>=first?uint32_t(after-before):uint32_t(after)-first+1;
            total+=native_term(static_cast<float>(levels)*rate);
        }
        if(after>=change) {
            const uint32_t levels=before>=change?uint32_t(after-before):uint32_t(after)-change+1;
            const float adjustment=new_rate-rate;
            total+=native_term(static_cast<float>(levels)*adjustment);
        }
        if(total<0||total>std::numeric_limits<int32_t>::max())throw 1;
        return static_cast<uint32_t>(total);
    }catch(...) {if(row_constructed)reinterpret_cast<DestroyString>(config.cstring_destroy)(&row);throw;}
}
}
CBMDHLA_API int CBMDHLA_Configure(const CBMDHLA_Config* c) {
    if(configured||!c||c->abi!=1||!c->rules||!c->is_engine_thread||!c->num_abilities||!c->set_level
       ||!c->class_string||!c->get_at||!c->scan||!c->cstring_destroy||!c->first_level||!c->rate
       ||!c->change_level||!c->new_rate||!c->get_abilities||!c->complete_abilities
       ||!c->ability_construct||!c->cstring_construct_chars||!c->cstring_assign_chars
       ||!c->resref_construct_cstring||!c->check_enabled||!c->get_ai_type)return 0;
    config=*c;configured=true;return 1;
}
CBMDHLA_API int CBMDHLA_Open(const void* actor,uint8_t cls,uint32_t kit,
 uint8_t before,uint8_t after,CBMDHLA_View* out) {
    if(!thread()||!actor||!out||after<before){status=1;return 0;}
    void* catalog=nullptr;
    try {
        // Only native level-query fields are used by Num; SetLevel itself
        // resolves the selected class slot. No copied effects or game state.
        alignas(8) std::array<unsigned char,0xCA8> prior{},next{};
        alignas(8) std::array<unsigned char,0x18> ai{};
        ai[0xB]=cls;write<uint32_t>(ai.data(),0xC,0xFFFFFFFF);
        reinterpret_cast<SetLevel>(config.set_level)(prior.data(),cls,cls,before);
        reinterpret_cast<SetLevel>(config.set_level)(next.data(),cls,cls,after);
        uint8_t flags=0;
        const int capped=reinterpret_cast<Num>(config.num_abilities)(reinterpret_cast<void*>(config.rules),
            ai.data(),prior.data(),next.data(),&flags);
        const uint32_t points=uncapped(cls,before,after);
        if(capped<0||static_cast<uint32_t>(capped)!=std::min(points,uint32_t(24))) {status=2;return 0;}
        // GetLevelUpAbilities reads just this AI object and split kit words.
        // Borrowing the real CString name is safe for this synchronous call;
        // native CAIObjectType::Set creates/destroys its own reference copy.
        alignas(8) std::array<unsigned char,0x4B68> view{};
        std::memcpy(view.data()+0x4B50,static_cast<const unsigned char*>(actor)+0x4B50,0x18);
        view[0x4B5B]=cls;write<uint32_t>(view.data(),0x4B5C,0xFFFFFFFF);
        write<uint16_t>(view.data(),0x79C,static_cast<uint16_t>(kit>>16));
        write<uint16_t>(view.data(),0x79E,static_cast<uint16_t>(kit));
        // A zero-choice interval has no catalog dependency. The next interval
        // reopens against the then-installed native rules and ability table.
        if(points)catalog=reinterpret_cast<Catalog>(config.get_abilities)(reinterpret_cast<void*>(config.rules),view.data());
        const int32_t rows=catalog?read<int32_t>(catalog,0x10):0;
        if(rows<0||(rows&&(!read<void*>(catalog,8))))throw 1;
        auto session=std::make_unique<Session>();session->catalog=catalog;session->rows=static_cast<uint32_t>(rows);
        session->points=points;session->capped=static_cast<uint32_t>(capped);session->flags=flags;
        const uint64_t id=next_id++;if(!id)throw 1;
        sessions.emplace(id,std::move(session));catalog=nullptr;
        *out={id,points,static_cast<uint32_t>(capped),static_cast<uint32_t>(rows),flags};status=0;return 1;
    }catch(...) {
        if(catalog)try {close_catalog(catalog);}catch(...) {status=4;return 0;}
        status=3;return 0;
    }
}
CBMDHLA_API int CBMDHLA_ReadRow(uint64_t id,uint32_t index,CBMDHLA_Row* out) {
    const auto found=sessions.find(id);
    if(!thread()||!out||found==sessions.end()||index>=found->second->rows)return 0;
    auto* array=read<void**>(found->second->catalog,8);auto* row=array[index];if(!row)return 0;
    CBMDHLA_Row result{};std::memcpy(result.icon,row,8);
    result.name_strref=read<uint32_t>(row,8);result.min_level=read<int32_t>(row,0x18);
    result.max_level=read<int32_t>(row,0x1C);result.max_rank=read<int32_t>(row,0x20);
    result.effect=read<const char*>(row,0x10);result.prerequisite=read<const char*>(row,0x28);
    result.excluded_by=read<const char*>(row,0x30);result.alignment=read<const char*>(row,0x38);
    if(!result.effect||!result.prerequisite||!result.excluded_by||!result.alignment)return 0;
    *out=result;return 1;
}
CBMDHLA_API int CBMDHLA_Close(uint64_t id) {
    auto found=sessions.find(id);if(!thread()||found==sessions.end())return 0;
    // Consume the handle before cleanup. A destructor may have partially freed
    // its native array when it throws; retry would risk a second free.
    void* catalog=found->second->catalog;sessions.erase(found);
    try {close_catalog(catalog);return 1;}
    catch(...) {status=4;return -1;}
}
CBMDHLA_API int CBMDHLA_CanChoose(uint64_t id,const void* actor,uint32_t index,
 const uint32_t* selected,uint32_t selected_count,const CBMDHLA_Row* deferred,uint32_t deferred_count) {
    const auto found=sessions.find(id);
    if(!thread()||!actor||found==sessions.end()||(selected_count&&!selected)||(deferred_count&&!deferred))return -1;
    try {
        CBMDHLA_Row candidate{};if(!CBMDHLA_ReadRow(id,index,&candidate))return -1;
        uint64_t matching=0;std::vector<CBMDHLA_Row> representatives;
        bool prereq=false,exclusion=false;
        for(uint32_t i=0;i<selected_count;++i) {
            CBMDHLA_Row current{};if(!CBMDHLA_ReadRow(id,selected[i],&current))return -1;
            if(std::strcmp(current.effect,candidate.effect)==0)++matching;
            const bool need_prereq=!prereq&&std::strcmp(candidate.prerequisite,"*")&&std::strcmp(current.effect,candidate.prerequisite)==0;
            const bool need_exclusion=!exclusion&&std::strcmp(candidate.excluded_by,"*")&&std::strcmp(current.effect,candidate.excluded_by)==0;
            if(need_prereq||need_exclusion)representatives.push_back(current);
            prereq=prereq||need_prereq;exclusion=exclusion||need_exclusion;
        }
        if(candidate.max_rank<=0||matching>=static_cast<uint32_t>(candidate.max_rank))return 0;
        uint32_t represented_matching=0;
        for(const auto& r:representatives)if(std::strcmp(r.effect,candidate.effect)==0)++represented_matching;
        candidate.max_rank-=static_cast<int32_t>(matching);
        candidate.max_rank+=static_cast<int32_t>(represented_matching);
        NativeRow native_candidate;native_candidate.set(candidate);
        EligibilityActor projected(actor,deferred,deferred_count);
        std::vector<std::unique_ptr<NativeRow>> owned;std::vector<void*> pointers;
        for(const auto& r:representatives){auto value=std::make_unique<NativeRow>();value->set(r);pointers.push_back(value->bytes.data());owned.push_back(std::move(value));}
        alignas(8) std::array<unsigned char,0x20> list{};
        write(list.data(),8,pointers.data());write<int32_t>(list.data(),0x10,static_cast<int32_t>(pointers.size()));
        alignas(8) std::array<unsigned char,0xA10> screen{};
        screen[0x9E0]=found->second->flags;write(screen.data(),0x9E8,list.data());
        for(size_t i=0;i<pointers.size();++i)screen[0x9F0+i]=static_cast<unsigned char>(i);
        screen[0xA08]=static_cast<unsigned char>(pointers.size());
        return reinterpret_cast<Check>(config.check_enabled)(screen.data(),projected.bytes.data(),native_candidate.bytes.data())?1:0;
    }catch(...){status=5;return -1;}
}
CBMDHLA_API int CBMDHLA_LastStatus(){return status;}
CBMDHLA_API int CBMDHLA_ConfigureProjection(const CBMDHLA_ProjectionConfig* c){
 if(session_query||!c||c->abi!=1||!c->session_query)return 0;session_query=c->session_query;return 1;
}
CBMDHLA_API int CBMDHLA_PrepareManual(void* actor,const char* owner,const CBMDHLA_Row* rows,uint32_t count,uint64_t* token){
 if(!thread()||!session_query||!actor||!owner||std::strlen(owner)!=32||!token||(count&&!rows))return 0;
 CBMDS_View scope{};
 if(!reinterpret_cast<int(*)(const void*,CBMDS_View*)>(session_query)(actor,&scope)||scope.phase!=CBMDS_PREPARING
  ||scope.sprite!=reinterpret_cast<uintptr_t>(actor)||std::memcmp(scope.owner,owner,33))return 0;
 try {
  Projection p{scope,next_projection++,{}};if(!p.token)return 0;
  for(uint32_t i=0;i<count;++i){if(!rows[i].effect||std::strlen(rows[i].effect)<=3)return 0;p.effects.emplace_back(rows[i].effect);}
  const auto key=reinterpret_cast<uintptr_t>(actor);auto prior=projections.find(key);
  if(prior!=projections.end()&&prior->second.scope.session==scope.session&&prior->second.scope.incarnation==scope.incarnation)return 0;
  *token=p.token;projections[key]=std::move(p);return 1;
 }catch(...){return 0;}
}
CBMDHLA_API int CBMDHLA_ClearManual(uint64_t token){
 if(!thread())return 0;
 for(auto i=projections.begin();i!=projections.end();++i)if(i->second.token==token){projections.erase(i);return 1;}
 return 1; // idempotent token cleanup cannot erase a newer actor context
}
CBMDHLA_API int CBMDHLA_CheckAbilityEnabled(void* screen,void* actor,void* candidate){
 if(!configured)throw std::runtime_error("Unconfigured HLA predicate");
 CBMDS_View scope{};
 const bool owned=thread()&&session_query&&reinterpret_cast<int(*)(const void*,CBMDS_View*)>(session_query)(actor,&scope)
  &&scope.screen==reinterpret_cast<uintptr_t>(screen)&&scope.sprite==reinterpret_cast<uintptr_t>(actor)
  &&scope.owner[0]!=0
  &&(scope.phase==CBMDS_PREPARING||scope.phase==CBMDS_PREVIEW);
 if(!owned)return reinterpret_cast<Check>(config.check_enabled)(screen,actor,candidate);
 const auto found=projections.find(reinterpret_cast<uintptr_t>(actor));
 if(found==projections.end()||found->second.scope.session!=scope.session||found->second.scope.incarnation!=scope.incarnation
  ||std::memcmp(found->second.scope.owner,scope.owner,33))throw std::runtime_error("Owned HLA preview context missing or stale");
 std::vector<CBMDHLA_Row> rows(found->second.effects.size());
 for(size_t i=0;i<rows.size();++i)rows[i].effect=found->second.effects[i].c_str();
 EligibilityActor projected(actor,rows.data(),static_cast<uint32_t>(rows.size()));
 return reinterpret_cast<Check>(config.check_enabled)(screen,projected.bytes.data(),candidate);
}
