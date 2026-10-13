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
std::atomic<int> status{0};
struct Entry {const void* effect;CBMA_View view;};
std::unordered_map<const void*,Entry> records;
using Callback=int(*)(void*,void*);
uint32_t read(const void* object,size_t offset) {
    uint32_t n;std::memcpy(&n,static_cast<const unsigned char*>(object)+offset,4);return n;
}
void write(void* object,size_t offset,uint32_t n){std::memcpy(static_cast<unsigned char*>(object)+offset,&n,4);}
bool on_host(){return configured&&std::this_thread::get_id()==host;}
int original(void* effect,void* sprite){return reinterpret_cast<Callback>(config.original)(effect,sprite);}
void uncertain(void* sprite,void* effect) {
    status=7;
    try {reinterpret_cast<Callback>(config.uncertain)(sprite,effect);}catch(...){}
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
    if(!on_host()||!effect||!sprite){status=2;return 0;}
    const auto amount=read(effect,0x1c);
    const auto mode=read(effect,0x20);
    if(read(effect,0x10)==104&&read(effect,0x24)==1&&mode<=2
        &&(mode!=0||amount==0||amount>0x7fffffffu)){
        try{const int result=CBMW_EffectWrite(effect,sprite,config.original);status=CBMW_LastStatus();return result;}
        catch(...){status=CBMW_LastStatus();throw;}
    }
    // Nonpermanent and unknown modes retain the complete original behavior;
    // they are not earned permanent awards or supported account writes.
    if(read(effect,0x10)!=104||read(effect,0x20)!=0||read(effect,0x24)!=1
        ||amount==0||amount>0x7fffffffu){status=1;return original(effect,sprite);}
    CBMI_View identity{};
    if(!CBMI_Query(sprite,&identity)){status=3;return 0;}
    if(!identity.eligible){status=1;return original(effect,sprite);}
    if(!CBMI_CanMutate(sprite,identity.incarnation)){status=4;return 0;}
    auto previous=records.find(sprite);
    if(previous!=records.end()) {
        if(previous->second.view.stage!=CBMA_UNCERTAIN
            ||previous->second.view.incarnation==identity.incarnation){status=4;return 0;}
        records.erase(previous); // Proven new lifetime cannot inherit a receipt.
    }
    for(auto it=records.begin();it!=records.end();) {
        CBMI_View owner{};
        if(it->second.view.stage==CBMA_UNCERTAIN&&(!CBMI_Query(it->first,&owner)
            ||owner.incarnation!=it->second.view.incarnation)){it=records.erase(it);continue;}
        if(it->second.effect==effect){status=4;return 0;}
        ++it;
    }
    const auto before=read(sprite,0x570);
    const auto applied=std::min(amount,0xffffffffu-before);
    Entry entry{effect,{identity.incarnation,before,amount,applied,amount-applied,before,0,CBMA_PREPARING}};
    try {records.emplace(sprite,entry);}catch(...){status=5;return 0;}
    bool native_entered=false;
    try {
        const int disposition=reinterpret_cast<Callback>(config.before)(sprite,effect);
        CBMI_View now{};
        const bool same=CBMI_Query(sprite,&now)&&now.incarnation==identity.incarnation
            &&CBMI_CanMutate(sprite,identity.incarnation)&&read(sprite,0x570)==before
            &&read(effect,0x10)==104&&read(effect,0x1c)==amount&&read(effect,0x20)==0&&read(effect,0x24)==1;
        if(!same){records.at(sprite).view.stage=CBMA_UNCERTAIN;uncertain(sprite,effect);return 0;}
        if(disposition==2){records.erase(sprite);status=1;return original(effect,sprite);}
        if(disposition!=1){records.erase(sprite);status=5;return 0;}
        auto& v=records.at(sprite).view;
        v.stage=CBMA_NATIVE;
        native_entered=true;
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
    static const char* names[]={"","preparing","native","completing","uncertain"};
    text(L,names[v.stage]);number(L,static_cast<int64_t>(v.incarnation));number(L,v.pre_base);
    number(L,v.amount);number(L,v.applied);number(L,v.remainder);number(L,v.native_result);number(L,v.post_base);
    return 8;
}
int CBMA_LastStatus(){return status.load();}
