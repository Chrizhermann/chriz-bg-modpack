#include "writer_native.h"
#include <atomic>
#include <charconv>
#include <cstring>
#include <thread>
#include <unordered_map>
namespace{
CBMW_Config config{};bool configured=false;std::thread::id host;std::atomic<int> status{0};
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
int CBMW_Configure(const CBMW_Config* in){
    if(configured||!in||in->abi!=1||!in->setter||!in->before||!in->complete||!in->uncertain
        ||!in->lua_tolstring||!in->lua_pushstring||!in->lua_pushboolean)return 0;
    config=*in;configured=true;host=std::this_thread::get_id();return 1;
}
namespace {
void* write_impl(void* sprite,uint32_t value,uint32_t mode,void* effect,uintptr_t leaf,int* native_result){
    if(!on_host()||!sprite){status=2;return sprite;}
    const auto effect_mode=effect?field(effect,0x20):0;
    const auto passthrough=[&](){
        if(effect)*native_result=reinterpret_cast<int(*)(void*,void*)>(leaf)(effect,sprite);
        else xp(sprite,mode==1?xp(sprite)+value:value);
        status=1;
    };
    CBMI_View identity{};
    if(!CBMI_Query(sprite,&identity)){status=3;return sprite;}
    const auto before=xp(sprite);
    if(!identity.eligible){passthrough();return sprite;}
    if(!CBMI_CanMutate(sprite,identity.incarnation)){status=4;return sprite;}
    auto prior=records.find(sprite);
    if(prior!=records.end()){
        if(prior->second.stage!=CBMW_UNCERTAIN||prior->second.incarnation==identity.incarnation){status=4;return sprite;}
        records.erase(prior);
    }
    if(effect)for(auto it=records.begin();it!=records.end();){
        CBMI_View owner{};
        if(it->second.stage==CBMW_UNCERTAIN&&(!CBMI_Query(it->first,&owner)||owner.incarnation!=it->second.incarnation)){
            it=records.erase(it);continue;
        }
        if(it->second.effect==effect){status=4;return sprite;}
        ++it;
    }
    auto* owned=effect?nullptr:take_origin(sprite,identity.incarnation,value,mode);OriginResult receipt{owned};
    CBMW_View v{identity.incarnation,value,mode,before,before,0,owned?owned->kind:0,CBMW_PREPARING,false,
        effect?1u:0u,effect_mode,0,effect};
    try{records.emplace(sprite,v);}catch(...){status=5;return sprite;}
    bool wrote=false;
    try{
        const auto disposition=reinterpret_cast<Callback>(config.before)(sprite);
        CBMI_View now{};
        auto& current=records.at(sprite);
        if(!CBMI_Query(sprite,&now)||now.incarnation!=identity.incarnation||!CBMI_CanMutate(sprite,identity.incarnation)||xp(sprite)!=before
            ||(effect&&(field(effect,0x10)!=104||field(effect,0x1c)!=value||field(effect,0x20)!=effect_mode||field(effect,0x24)!=1))){
            current.stage=CBMW_UNCERTAIN;uncertain(sprite);return sprite;
        }
        if(disposition==2){records.erase(sprite);passthrough();return sprite;}
        if(disposition!=1||!current.planned){records.erase(sprite);status=5;return sprite;}
        current.stage=CBMW_WRITING;
        // Exactly the stat44-owned 32-bit word. No callback occurs between this
        // store and its observed post-value. Original recalc runs AFTER return.
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
    if(!on_host()||!effect||!sprite||!leaf){status=2;return 0;}
    const auto value=field(effect,0x1c),effect_mode=field(effect,0x20);
    if(field(effect,0x10)!=104||field(effect,0x24)!=1||effect_mode>2
        ||(effect_mode==0&&value>0&&value<=0x7fffffff)){status=2;return 0;}
    int result=0;
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
    static const char* stages[]={"","preparing","writing","completing","uncertain"};
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
