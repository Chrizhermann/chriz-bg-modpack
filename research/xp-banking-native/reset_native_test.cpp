// Synthetic engine callbacks exercise the compiled native boundary/ABI. The
// separate reset_probe.py executes actual PE instructions through the XP zero.
#include "reset_native.h"
#include "party_native.h"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>
namespace {
alignas(16) unsigned char actor[0x6000]{},chitin[0x1100]{},game[0x100]{};
void* chitin_ptr=chitin;
bool strip=false,preview=false,journal=false,reject_prepare=false,fail_complete=false,throw_native=false;
int checks=0,native_calls=0,uncertain_calls=0;
uint32_t ceiling=8000000;
int getter_calls=0,party_calls=0;
bool fail_party=false;
bool reject_preview=false,throw_preview=false,throw_remove=false,deny_fail=false;
int captures=0,starts=0,removes=0;
unsigned char clean_marker=0;
void check_impl(bool value,int line) { ++checks; if(!value)throw std::runtime_error("reset assertion at line "+std::to_string(line)); }
#define check(x) check_impl((x),__LINE__)
uint32_t xp() { uint32_t value;std::memcpy(&value,actor+0x570,4);return value; }
void xp(uint32_t n) { std::memcpy(actor+0x570,&n,4); }
void lifecycle(void*) {}
CBMR_View record() { CBMR_View v{};check(CBMR_Query(actor,&v));return v; }
int prepare(void* sprite,unsigned char cls) {
    check(sprite==actor&&cls==4);
    auto r=record();check(r.stage==CBMR_PREPARING&&r.pre_base==xp()&&r.new_class==cls);
    CBMI_View id{};check(CBMI_Query(actor,&id)&&r.incarnation==id.incarnation);
    if(reject_prepare)return 0;
    journal=true;return 1;
}
int complete(void* sprite,unsigned char cls) {
    check(sprite==actor&&cls==4&&journal&&xp()==0);
    check(record().stage==CBMR_COMPLETING);
    if(fail_complete)return 0;
    journal=false;return 1;
}
int uncertain(void* sprite,unsigned char cls) {
    check(sprite==actor&&cls==4&&journal);
    check(record().stage==CBMR_UNCERTAIN);
    ++uncertain_calls;return 1;
}
uintptr_t marshal(void* sprite,void*,void*,void*,unsigned char) {
    check(sprite==actor&&journal&&record().stage==CBMR_NATIVE);
    CBMI_View id{};check(CBMI_Query(sprite,&id)&&id.serializing&&!CBMI_CanMutate(sprite,id.incarnation));
    // Root's serializer sees a full pre-published pendingDual record here, even
    // though native base XP has already changed. We do not mark it completed.
    check(xp()==0);return 0;
}
void native_reset(void* screen,void* sprite,unsigned char cls) {
    check(screen==game&&sprite==actor&&cls==4&&journal);
    auto r=record();check(r.stage==CBMR_NATIVE&&r.pre_base==xp());
    ++native_calls;
    CBMR_MakeDualClass(screen,sprite,cls); // Reentrant attempt must not reset twice.
    xp(0);
    CBMI_Marshal(sprite,nullptr,nullptr,nullptr,0);
    if(throw_native)throw std::runtime_error("partial native reset");
}
uint32_t native_cap(void* rules,const void* start_ai) {
    check(rules==game&&start_ai==actor+0x4B68);return ceiling;
}
uint32_t getter(void* sprite){check(sprite==actor);++getter_calls;return 0xFEDCBA98;}
int party_ready(void* sprite,unsigned char ignored){check(sprite==actor&&ignored==0&&getter_calls==party_calls+1);++party_calls;return !fail_party;}
unsigned char get_deny(int id,void** out){check(id==123);*out=actor;return deny_fail?1:0;}
int capture(void* sprite,unsigned char ignored){
    check(sprite==actor&&ignored==0);CBMR_PreviewView v{};
    check(CBMR_PreviewQuery(sprite,&v)&&v.pre_base==xp());
    CBMI_View id{};check(CBMI_Query(sprite,&id)&&id.incarnation==v.incarnation);
    ++captures;clean_marker=actor[0x100];
    CBMR_StartEditing(game,123,0x18); // Scoped same-actor reentry cannot capture twice.
    if(throw_preview)throw std::runtime_error("preview capture failed");
    return !reject_preview;
}
void start_editing(void* screen,int id,int mode){
    check(screen==game&&id==123&&mode==0x18);CBMR_PreviewView v{};
    check(!CBMR_PreviewQuery(actor,&v));++starts;
    actor[0x100]=9; // Preview choices may change the aggregate after clean capture.
}
void remove_abilities(void* screen,void* sprite,unsigned cls,int remove){
    check(screen==game&&sprite==actor&&cls==4&&remove==1&&journal);
    check(record().stage==CBMR_NATIVE&&record().path==2&&xp()==record().pre_base);
    check(clean_marker==3&&actor[0x100]==9);++removes;
    CBMR_CreateMakeDualClass(screen,sprite,4); // Still inside removal: no reset yet.
    actor[0x100]=0;
    if(throw_remove)throw std::runtime_error("partial ability removal");
}
}
int run() {
    void* game_ptr=game;
    std::memcpy(chitin+0x1090,&game_ptr,sizeof(game_ptr));
    CBMI_Config identity{1,{1,reinterpret_cast<uintptr_t>(marshal),1,1,reinterpret_cast<uintptr_t>(lifecycle),reinterpret_cast<uintptr_t>(lifecycle)},
        1,1,1,reinterpret_cast<uintptr_t>(&strip),reinterpret_cast<uintptr_t>(&preview)};
    check(CBMI_Configure(&identity));CBMI_Construct(actor);
    CBMR_Config cfg{2,reinterpret_cast<uintptr_t>(native_reset),reinterpret_cast<uintptr_t>(prepare),reinterpret_cast<uintptr_t>(complete),
        reinterpret_cast<uintptr_t>(uncertain),reinterpret_cast<uintptr_t>(native_cap),reinterpret_cast<uintptr_t>(&chitin_ptr),1,1,
        reinterpret_cast<uintptr_t>(native_reset),reinterpret_cast<uintptr_t>(remove_abilities),reinterpret_cast<uintptr_t>(start_editing),
        reinterpret_cast<uintptr_t>(get_deny),reinterpret_cast<uintptr_t>(capture)};
    check(!CBMR_Configure(nullptr));check(CBMR_Configure(&cfg));check(!CBMR_Configure(&cfg));
    uint32_t cap=0;check(CBMR_NativeCap(actor,&cap)&&cap==8000000);
    ceiling=123456;check(CBMR_NativeCap(actor,&cap)&&cap==123456);
    chitin_ptr=nullptr;check(!CBMR_NativeCap(actor,&cap));chitin_ptr=chitin;
    xp(600000);CBMR_MakeDualClass(game,actor,4);
    check(native_calls==1&&xp()==0&&!journal);CBMR_View none{};check(!CBMR_Query(actor,&none));
    reject_prepare=true;xp(444444);CBMR_MakeDualClass(game,actor,4);
    check(native_calls==1&&xp()==444444&&!journal&&!CBMR_Query(actor,&none));reject_prepare=false;
    fail_complete=true;xp(777777);CBMR_MakeDualClass(game,actor,4);
    check(native_calls==2&&journal&&xp()==0&&record().stage==CBMR_UNCERTAIN);
    CBMR_MakeDualClass(game,actor,4);check(native_calls==2);fail_complete=false;
    auto old=record().incarnation;
    CBMI_Destruct(actor);CBMI_Construct(actor);journal=false;
    check(!CBMR_Query(actor,&none));
    throw_native=true;xp(999999);
    try {CBMR_MakeDualClass(game,actor,4);check(false);}catch(const std::runtime_error& e){check(std::string(e.what())=="partial native reset");}
    check(journal&&xp()==0&&record().stage==CBMR_UNCERTAIN&&record().pre_base==999999);
    check(record().incarnation!=old&&uncertain_calls==2);
    int foreign=1;std::thread thread([&]{foreign=CBMR_Query(actor,&none);});thread.join();check(!foreign);
    CBMI_Destruct(actor);CBMI_Construct(actor);journal=false;throw_native=false;xp(600000);actor[0x100]=3;
    CBMR_PreviewView pv{};check(!CBMR_PreviewQuery(actor,&pv));
    CBMR_StartEditing(game,123,0x19);check(captures==0&&starts==0);
    deny_fail=true;CBMR_StartEditing(game,123,0x18);check(captures==0);deny_fail=false;
    reject_preview=true;CBMR_StartEditing(game,123,0x18);check(captures==1&&starts==0&&!CBMR_PreviewQuery(actor,&pv));reject_preview=false;
    throw_preview=true;try{CBMR_StartEditing(game,123,0x18);check(false);}catch(const std::runtime_error&){check(!CBMR_PreviewQuery(actor,&pv));}throw_preview=false;
    CBMR_StartEditing(game,123,0x18);check(captures==3&&starts==1&&clean_marker==3&&actor[0x100]==9);
    const int prior=native_calls;
    CBMR_CreateMakeDualClass(game,actor,4);check(native_calls==prior&&xp()==600000); // No late invented receipt.
    CBMR_RemoveAbilities(game,actor,4,1);check(removes==1&&native_calls==prior&&journal&&record().path==2);
    CBMR_CreateMakeDualClass(chitin,actor,4);CBMR_CreateMakeDualClass(game,actor,5);
    check(native_calls==prior&&xp()==600000);
    CBMR_CreateMakeDualClass(game,actor,4);check(native_calls==prior+1&&xp()==0&&!journal&&!CBMR_Query(actor,&none));
    CBMR_CreateMakeDualClass(game,actor,4);check(native_calls==prior+1);
    xp(700000);actor[0x100]=3;CBMR_StartEditing(game,123,0x18);throw_remove=true;
    try{CBMR_RemoveAbilities(game,actor,4,1);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="partial ability removal");}
    check(journal&&xp()==700000&&record().stage==CBMR_UNCERTAIN&&record().pre_base==700000);
    CBMR_CreateMakeDualClass(game,actor,4);check(native_calls==prior+1);throw_remove=false;
    CBMI_Destruct(actor);CBMI_Construct(actor);journal=false;actor[0x100]=3;
    CBMR_StartEditing(game,123,0x18);reject_prepare=true;CBMR_RemoveAbilities(game,actor,4,1);
    check(!journal&&!CBMR_Query(actor,&none)&&removes==2&&xp()==700000);reject_prepare=false;
    actor[0x100]=3;CBMR_StartEditing(game,123,0x18);CBMR_RemoveAbilities(game,actor,4,1);
    xp(700001);CBMR_CreateMakeDualClass(game,actor,4);
    check(journal&&record().stage==CBMR_UNCERTAIN&&native_calls==prior+1&&xp()==700001);
    CBMP_Config party{1,reinterpret_cast<uintptr_t>(getter),reinterpret_cast<uintptr_t>(party_ready)};
    check(!CBMP_Configure(nullptr)&&CBMP_Configure(&party)&&!CBMP_Configure(&party));
    check(CBMP_LastStatus()==0&&CBMP_OnPartyReady(actor)==0xFEDCBA98&&CBMP_LastStatus()==1);
    fail_party=true;check(CBMP_OnPartyReady(actor)==0xFEDCBA98&&CBMP_LastStatus()==3);
    uint32_t foreign_name=0;
    std::thread party_thread([&]{foreign_name=CBMP_OnPartyReady(actor);});party_thread.join();
    check(foreign_name==0xFEDCBA98&&CBMP_LastStatus()==2&&getter_calls==3&&party_calls==2);
    std::printf("{\"reset_shim_assertions\":%d,\"actual_game_execution\":false}\n",checks);
    return 0;
}
int main(){try{return run();}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
