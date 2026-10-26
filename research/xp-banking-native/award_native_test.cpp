// Runs the actual audited native opcode104 bytes on synthetic buffers only.
// The original dispatch can inject faults around that leaf for recovery tests.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "award_native.h"
#include "writer_native.h"
#include "award_native_leaf.inc"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <new>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <limits>
// One armed allocation fails. The bridges' first allocation is their record insert.
static bool fail_allocation=false;
void* operator new(std::size_t n){
    if(fail_allocation){fail_allocation=false;throw std::bad_alloc();}
    if(void* p=std::malloc(n?n:1))return p;
    throw std::bad_alloc();
}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
namespace {
constexpr size_t ACTOR=0x6000,EFFECT=0x200;
alignas(16) unsigned char actor[ACTOR]{},second[ACTOR]{},effect_buffer[EFFECT]{},other[EFFECT]{},spare[EFFECT]{};
unsigned char* effect=effect_buffer; // The effect the callback doubles expect.
using Apply=int(*)(void*,void*);
Apply leaf;
unsigned char* subject=actor; // The actor whose callbacks the Lua doubles expect.
bool strip=false,preview=false,journal=false,fail_complete=false,throw_native=false,corrupt_result=false;
int disposition=1,checks=0,calls=0,prepares=0,uncertains=0,mutate=0,fault_cases=0;
uint64_t overflow=0;
int write_disposition=2,write_prepares=0,write_completes=0,write_uncertains=0;
uint32_t write_target=0,expected_effect_mode=0,expected_raw=0;
bool write_journal=false,write_fail_complete=false;
bool refuse_withdrawal=false;int withdrawals=0; // The runtime finds the journal no longer exactly prepared.
std::function<void()> in_flight,during_marshal; // Nested resolutions inside a callback or a save.
void check_impl(bool result,int line){++checks;if(!result)throw std::runtime_error("award assertion line "+std::to_string(line));}
#define check(x) check_impl((x),__LINE__)
uint32_t read(const void* p,size_t n){uint32_t x;std::memcpy(&x,static_cast<const unsigned char*>(p)+n,4);return x;}
void write(void* p,size_t n,uint32_t x){std::memcpy(static_cast<unsigned char*>(p)+n,&x,4);}
uint64_t fallbacks(){return CBMA_Fallbacks(nullptr)+CBMW_Fallbacks(nullptr);}
void lifecycle(void*){}
void* copy_actor(void*,int,int,int,int){CBMI_Construct(actor);return actor;}
uintptr_t marshal(void*,void*,void*,void*,unsigned char){if(during_marshal)during_marshal();return 0;}
// What a before callback changes: XP, amount, the actor's lifetime (3 ends it
// and starts a new one at that address, 4 only ends it), the operation (5 a SET
// of 100000, 6 a percentage of 50, 7 a loss of 1000, 8 an award of 64, 10 a
// nonpermanent SET, 11 a SET with another opcode field, which the leaf never
// reads, 12 mode 3; with that opcode field 13 an award of 64, 14 a loss of 1000,
// 15 a percentage of 50, 16 mode 3, 17 a nonpermanent SET; 18 an award of 64 with
// timing 2), or 9: another thread constructs an unrelated actor (see foreign_case).
void changed(unsigned char* a,unsigned char* e){
    if(mutate==1)write(a,0x570,read(a,0x570)+7);
    if(mutate==2)write(e,0x1c,read(e,0x1c)^0x40);
    struct Into{int code;uint32_t opcode,mode,amount,timing;};
    for(const auto i:{Into{5,104,1,100000,1},Into{6,104,2,50,1},Into{7,104,0,0xfffffc18,1},Into{8,104,0,64,1},
                      Into{10,104,1,100000,0},Into{11,187,1,100000,1},Into{12,104,3,100000,1},
                      Into{13,187,0,64,1},Into{14,187,0,0xfffffc18,1},Into{15,187,2,50,1},Into{16,187,3,100000,1},
                      Into{17,187,1,100000,0},Into{18,104,0,64,2}})
        if(mutate==i.code){write(e,0x10,i.opcode);write(e,0x20,i.mode);write(e,0x1c,i.amount);write(e,0x24,i.timing);}
}
alignas(16) unsigned char unrelated[ACTOR]{};
void foreign_event(){std::thread t([]{CBMI_Construct(unrelated);});t.join();}
// 19: another thread destroys the actor and constructs another (B, 10 XP) at its address.
void foreign_replacement(){std::thread t([]{CBMI_Destruct(subject);CBMI_Construct(subject);write(subject,0x570,10);});t.join();}
void change(){
    changed(subject,effect);if(mutate==3||mutate==4)CBMI_Destruct(subject);if(mutate==3)CBMI_Construct(subject);
    if(mutate==9)foreign_event();
    if(mutate==19)foreign_replacement();
}
// Lua host doubles for the bridges' exported Lua functions.
std::string lua_args[2];std::vector<std::string> lua_pushed;
const char* lua_read(void*,int index,size_t* length){const auto& s=lua_args[index-1];*length=s.size();return s.c_str();}
const char* lua_push(void*,const char* s){lua_pushed.emplace_back(s);return s;}
void lua_bool(void*,int b){lua_pushed.emplace_back(b?"true":"false");}
std::string hex(const void* p){char b[32];std::snprintf(b,sizeof(b),"%llx",static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(p)));return b;}
// The lifetime's replaced-word note as the runtime reads it, and its acknowledgment.
bool replaced(const void* a){lua_args[0]=hex(a);lua_pushed.clear();check(CBMI_LuaQuery(nullptr)==8);return lua_pushed[7]=="true";}
void acknowledge(const void* a){
    CBMI_View v{};check(CBMI_Query(a,&v));lua_args[0]=hex(a);lua_args[1]=std::to_string(v.incarnation);
    lua_pushed.clear();check(CBMI_LuaAckReplaced(nullptr)==1&&lua_pushed[0]=="true");
}
CBMA_View view(){CBMA_View r{};check(CBMA_Query(subject,effect,&r));return r;}
int before(void* a,void* e){
    ++prepares;check(a==subject&&e==effect);
    auto r=view();check(r.stage==CBMA_PREPARING&&r.pre_base==read(subject,0x570));
    check(r.amount==read(effect,0x1c)&&r.amount==r.applied+r.remainder);
    check(!CBMA_Query(subject,other,&r));
    if(in_flight)in_flight();
    if(disposition==1)journal=true;
    change();
    return disposition;
}
int complete(void* a,void* e){
    check(a==subject&&e==effect&&journal);
    auto r=view();check(r.stage==CBMA_COMPLETING&&r.native_result==1);
    check(r.post_base==read(subject,0x570)&&r.post_base==r.pre_base+r.applied);
    check(read(effect,0x1c)==r.amount&&read(effect,0x114)==1&&read(effect,0x118)==1);
    if(in_flight)in_flight();
    if(fail_complete)return 0;
    overflow+=r.remainder;journal=false;return 1;
}
// As R.UncertainAward: withdraw an exactly prepared journal no store followed,
// else mark it uncertain. Another lifetime finds no boundary (a Lua error, 0).
int uncertain(void* a,void* e){
    check(a==subject&&e==effect&&journal);++uncertains;
    CBMA_View r{};if(!CBMA_Query(subject,effect,&r))return 0;
    if(r.stage==CBMA_WITHDRAWING){
        check(r.native_result==0&&r.post_base==r.pre_base);
        if(refuse_withdrawal)return 0;
        journal=false;++withdrawals;return 1;
    }
    check(r.stage==CBMA_UNCERTAIN&&(mutate==2||read(effect,0x1c)==r.amount));return 1;
}
int dispatch(void* e,void* a){
    ++calls;
    int result=leaf(e,a);
    if(throw_native)throw std::runtime_error("injected after native store");
    return corrupt_result?0:result;
}
void setup(uint32_t xp,uint32_t amount,uint32_t mode=0,uint32_t timing=1){
    std::memset(effect,0,EFFECT);write(effect,0x10,104);write(effect,0x1c,amount);
    write(effect,0x20,mode);write(effect,0x24,timing);write(subject,0x570,xp);
    write(subject,0x1180,4321);write(subject,0x2ad0,1234);
}
void new_lifetime(){CBMI_Destruct(subject);CBMI_Construct(subject);journal=false;write_journal=false;}
CBMW_View writer_view(){CBMW_View v{};check(CBMW_Query(subject,&v));return v;}
int write_before(void* a){
    check(a==subject);++write_prepares;auto v=writer_view();
    check(v.source==1&&v.effect==effect&&v.stage==CBMW_PREPARING&&v.origin==0);
    check(v.raw_value==read(effect,0x1c)&&v.effect_mode==read(effect,0x20)&&v.pre_base==read(subject,0x570));
    check(v.mode==(v.effect_mode==0?1u:v.effect_mode==1?0u:2u));
    if(in_flight)in_flight();
    if(write_disposition==1){write_journal=true;check(CBMW_Plan(subject,write_target));}
    change();
    return write_disposition;
}
int write_complete(void* a){
    check(a==subject&&write_journal);++write_completes;auto v=writer_view();
    check(v.stage==CBMW_COMPLETING&&v.native_result==1&&v.post_base==write_target);
    check(read(effect,0x1c)==expected_raw&&read(effect,0x20)==expected_effect_mode);
    check(read(effect,0x114)==1&&read(effect,0x118)==1);
    if(in_flight)in_flight();
    if(write_fail_complete)return 0;write_journal=false;return 1;
}
int write_uncertain(void* a){ // As R.UncertainWrite.
    check(a==subject&&write_journal);++write_uncertains;
    CBMW_View v{};if(!CBMW_Query(subject,&v))return 0;
    if(v.stage==CBMW_WITHDRAWING){
        check(v.native_result==0&&v.post_base==v.pre_base);
        if(refuse_withdrawal)return 0;
        write_journal=false;++withdrawals;return 1;
    }
    check(v.stage==CBMW_UNCERTAIN);
    check(mutate==2||(read(effect,0x1c)==expected_raw&&read(effect,0x20)==expected_effect_mode));return 1;
}
// Outcomes of every path that does not commit, byte for byte against copies.
struct Copy{
    std::vector<unsigned char> a,e;unsigned char *actor_,*effect_;
    Copy(unsigned char* x,unsigned char* y):a(x,x+ACTOR),e(y,y+EFFECT),actor_(x),effect_(y){}
    bool same()const{return std::memcmp(actor_,a.data(),ACTOR)==0&&std::memcmp(effect_,e.data(),EFFECT)==0;}
};
using Call=std::function<int()>;
using Adjust=std::function<void(unsigned char*,unsigned char*)>;
// Native: result and bytes equal an independent original run; it ran once; counted.
void expect_native(const Call& call,unsigned char* a=nullptr,unsigned char* e=effect){
    if(!a)a=subject;
    Copy c(a,e);const int expected=leaf(c.e.data(),c.a.data());
    const int n=calls;const auto f=fallbacks();
    check(call()==expected&&calls==n+1&&fallbacks()==f+1&&c.same());
}
// Defer: 1 and nothing touched (adjust: what the callback itself changed).
void expect_defer(const Call& call,unsigned char* a=nullptr,unsigned char* e=effect,const Adjust& adjust=nullptr){
    if(!a)a=subject;
    Copy c(a,e);if(adjust)adjust(c.a.data(),c.e.data());
    const int n=calls;const auto f=fallbacks();
    check(call()==1&&calls==n&&fallbacks()==f&&c.same());
}
// Complete: 1, done and repass as the original marks them, no XP, not counted.
void expect_complete(const Call& call){
    Copy c(subject,effect);changed(c.a.data(),c.e.data());write(c.e.data(),0x114,1);write(c.e.data(),0x118,1);
    const int n=calls;const auto f=fallbacks();
    check(call()==1&&calls==n&&fallbacks()==f&&c.same());
}
int apply(){return CBMA_ApplyEffect(effect,subject);}
// Before any Configure: nothing to run, so touch nothing; never a null call.
void unconfigured(){
    write(effect,0x10,104);write(effect,0x1c,32);write(effect,0x24,1);write(actor,0x570,1000);
    Copy c(actor,effect);
    check(CBMA_ApplyEffect(effect,actor)==1&&CBMA_LastStatus()==2&&c.same()&&fallbacks()==0&&calls==0);
    check(CBMA_ApplyEffect(nullptr,actor)==1&&CBMA_ApplyEffect(effect,nullptr)==1&&c.same());
    check(CBMW_EffectWrite(effect,actor,0)==1&&CBMW_EffectWrite(nullptr,actor,1)==1&&c.same());
    // An unconfigured writer runs the leaf its caller passes: the original write.
    write(effect,0x20,1);write(effect,0x1c,1234);Copy w(actor,effect);
    check(leaf(w.e.data(),w.a.data())==1);
    check(CBMW_EffectWrite(effect,actor,reinterpret_cast<uintptr_t>(leaf))==1&&w.same()&&read(actor,0x570)==1234);
    check(CBMW_Fallbacks(nullptr)==1&&CBMA_Fallbacks(nullptr)==0);
    std::memset(effect,0,EFFECT);std::memset(actor,0,sizeof(actor));
}
// Every fault in every opcode-104 state: never 0, always its one defined outcome.
enum Fault{REFUSED,NO_IDENTITY,FOREIGN_THREAD,STICKY,INSERT_FAILS,SERIALIZING,OTHER_SERIALIZING,IN_FLIGHT,
    SAME_EFFECT,CHANGED_XP,CHANGED_AMOUNT,CHANGED_LIFETIME,DESTROYED,CHANGED_REFUSED,CHANGED_UNOWNED,REUSED_ADDRESS,
    OTHER_IN_FLIGHT,OTHER_STICKY,SETTER_IN_FLIGHT,SETTER_STICKY,CHANGED_UNWITHDRAWN,CHANGED_TWICE,
    CHANGED_TWICE_JOURNALED,FAULTS};
struct Kind{uint32_t amount,mode;bool writer;};
const Kind kinds[]={{32,0,false},{1234,1,true},{50,2,true},{0,0,true},{0xffffff38,0,true}};
uint32_t target(const Kind& k,uint32_t xp){
    if(k.mode==1)return k.amount;
    if(k.mode==2)return static_cast<uint32_t>(static_cast<uint32_t>(static_cast<uint64_t>(xp)*k.amount)/100);
    return xp+k.amount; // Modulo-32 add: zero or a loss.
}
int lua(){return prepares+write_prepares;}
int uncertain_calls(){return uncertains+write_uncertains;}
bool journaled(const Kind& k){return k.writer?write_journal:journal;}
bool record_uncertain(const Kind& k){
    if(k.writer){CBMW_View v{};return CBMW_Query(subject,&v)&&v.stage==CBMW_UNCERTAIN;}
    CBMA_View v{};return CBMA_Query(subject,effect,&v)&&v.stage==CBMA_UNCERTAIN;
}
bool no_record(){CBMA_View a{};CBMW_View w{};return !CBMA_Query(subject,effect,&a)&&!CBMW_Query(subject,&w);}
void matrix(){
    for(const auto& k:kinds)for(uint32_t xp:{600000u,0xfffffff0u})for(int fault=0;fault<FAULTS;++fault){
        subject=actor;new_lifetime();setup(xp,k.amount,k.mode);
        disposition=write_disposition=1;write_target=target(k,xp);expected_raw=k.amount;expected_effect_mode=k.mode;
        const int lua_before=lua(),uncertain_before=uncertain_calls();
        switch(fault){
        case REFUSED: // Any Lua error reaches native code as a refusal.
            disposition=write_disposition=0;expect_native(apply);check(lua()==lua_before+1&&no_record());break;
        case NO_IDENTITY:
            CBMI_Destruct(subject);expect_native(apply);CBMI_Construct(subject);check(lua()==lua_before);break;
        case FOREIGN_THREAD:
            expect_native([]{int r=-1;std::thread t([&]{r=apply();});t.join();return r;});
            check(lua()==lua_before&&CBMA_LastStatus()==2);break;
        case STICKY: // A retained uncertain record of this lifetime: the original until reconciled.
            fail_complete=write_fail_complete=true;check(apply()==1&&record_uncertain(k));
            fail_complete=write_fail_complete=false;setup(xp,k.amount,k.mode);
            expect_native(apply);check(lua()==lua_before+1&&record_uncertain(k)&&journaled(k));break;
        case INSERT_FAILS:
            expect_native([]{fail_allocation=true;return apply();});check(!fail_allocation&&lua()==lua_before&&no_record());break;
        case SERIALIZING: case OTHER_SERIALIZING: { // A save of this or any actor: resolve after it.
            int scopes=0;during_marshal=[&]{++scopes;expect_defer(apply);};
            CBMI_Marshal(fault==SERIALIZING?subject:other,nullptr,nullptr,nullptr,0);during_marshal=nullptr;
            check(scopes==1&&lua()==lua_before&&no_record());
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k)&&lua()==lua_before+1);break;}
        case IN_FLIGHT: // A nested resolution for this actor while its award runs.
            std::memcpy(spare,effect,EFFECT);
            in_flight=[]{expect_defer([]{return CBMA_ApplyEffect(spare,subject);},nullptr,spare);};
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k));in_flight=nullptr;
            check(read(spare,0x114)==0&&read(spare,0x118)==0);break;
        case SAME_EFFECT: // Another actor's in-flight record already holds this effect.
            subject=second;new_lifetime();setup(xp,k.amount,k.mode);
            in_flight=[]{expect_defer([]{return CBMA_ApplyEffect(effect,actor);},actor);};
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k));in_flight=nullptr;subject=actor;break;
        case CHANGED_XP: case CHANGED_AMOUNT: { // No store followed: its journal is withdrawn, retried once.
            mutate=fault==CHANGED_XP?1:2;const int w=withdrawals;
            expect_defer(apply,nullptr,effect,changed);mutate=0;
            check(no_record()&&!journaled(k)&&withdrawals==w+1&&uncertain_calls()==uncertain_before+1);
            if(fault==CHANGED_AMOUNT)write(effect,0x1c,k.amount); // As it was: the same write, fresh boundary.
            write_target=target(k,read(subject,0x570));
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k)&&no_record());
            check((k.writer?CBMW_LastStatus():CBMA_LastStatus())==6&&lua()==lua_before+2);
            if(fault==CHANGED_AMOUNT)break;
            // The finished retry is forgotten: this lifetime's next change at that
            // address that sees new values gets its own retry.
            setup(xp,k.amount,k.mode);mutate=1;expect_defer(apply,nullptr,effect,changed);mutate=0;
            write_target=target(k,xp+7);check(apply()==1&&read(effect,0x114)==1&&no_record());break;}
        case CHANGED_UNWITHDRAWN: { // A journal that cannot be withdrawn alone holds it.
            mutate=1;refuse_withdrawal=true;expect_complete(apply);refuse_withdrawal=false;
            // Asked to withdraw, then marked uncertain: done without XP, not counted.
            check(uncertain_calls()==uncertain_before+2&&journaled(k)&&lua()==lua_before+1&&record_uncertain(k));
            mutate=0;break;}
        case CHANGED_LIFETIME: case DESTROYED: { // The preparation ended this lifetime (11).
            mutate=fault==CHANGED_LIFETIME?3:4;const auto ended=CBMW_Ended();
            // Nothing is written into another lifetime, no callback addresses the
            // ended one, the effect is left as it is (unresolved) and not counted.
            expect_defer(apply);mutate=0;
            check(CBMW_Ended()==ended+1&&(k.writer?CBMW_LastStatus():CBMA_LastStatus())==11);
            check(uncertain_calls()==uncertain_before&&lua()==lua_before+1);
            check(((CBMA_Holds(subject,0)|CBMW_Holds(subject,0))&1)==0); // No record of any lifetime stays in flight.
            if(fault==DESTROYED)CBMI_Construct(subject);
            // Its next pass belongs to the lifetime that holds it then; the ended
            // one's journal went with its actor data.
            journal=write_journal=false;write_target=target(k,xp);
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k)&&no_record());
            check((k.writer?CBMW_LastStatus():CBMA_LastStatus())==6&&lua()==lua_before+2);break;}
        case CHANGED_TWICE: case CHANGED_TWICE_JOURNALED: { // Changed on every pass: one retry, then the original.
            disposition=write_disposition=fault==CHANGED_TWICE?0:1;mutate=1;const int w=withdrawals;
            expect_defer(apply,nullptr,effect,changed);
            Copy c(subject,effect);changed(c.a.data(),c.e.data());const int expected=leaf(c.e.data(),c.a.data());
            const int n=calls;const auto f=fallbacks();
            check(apply()==expected&&calls==n+1&&fallbacks()==f+1&&c.same());mutate=0;
            check((k.writer?CBMW_LastStatus():CBMA_LastStatus())==8&&no_record()&&!journaled(k)&&lua()==lua_before+2);
            check(withdrawals==w+(fault==CHANGED_TWICE?0:2));disposition=write_disposition=1;break;}
        case CHANGED_REFUSED: case CHANGED_UNOWNED: // Nothing journaled: retry from a fresh boundary.
            disposition=write_disposition=fault==CHANGED_REFUSED?0:2;mutate=1;
            expect_defer(apply,nullptr,effect,changed);mutate=0;
            check(no_record()&&uncertain_calls()==uncertain_before&&!journaled(k));
            disposition=write_disposition=1;write_target=target(k,xp+7);
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k));break;
        case REUSED_ADDRESS: { // An uncertain record's effect is done; its address may hold another's new effect.
            fail_complete=write_fail_complete=true;check(apply()==1&&record_uncertain(k));
            fail_complete=write_fail_complete=false;
            subject=second;new_lifetime();setup(xp,k.amount,k.mode);const auto f=fallbacks();
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k)&&fallbacks()==f);
            check((k.writer?CBMW_LastStatus():CBMA_LastStatus())==6);
            subject=actor;setup(xp,k.amount,k.mode);expect_native(apply); // The first actor stays sticky.
            check(record_uncertain(k));break;}
        case OTHER_IN_FLIGHT: { // The other bridge's change of this actor waits while this one runs.
            std::memcpy(spare,effect,EFFECT);write(spare,0x1c,k.writer?32:1234);write(spare,0x20,k.writer?0:1);
            in_flight=[]{expect_defer([]{return CBMA_ApplyEffect(spare,subject);},nullptr,spare);};
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k)&&lua()==lua_before+1);in_flight=nullptr;
            check(read(spare,0x114)==0&&read(spare,0x118)==0);break;}
        case OTHER_STICKY: { // The other bridge keeps this lifetime's uncertain journal: the original, no callback.
            const Kind& o=k.writer?kinds[0]:kinds[1];
            setup(xp,o.amount,o.mode);write_target=target(o,xp);expected_raw=o.amount;expected_effect_mode=o.mode;
            fail_complete=write_fail_complete=true;check(apply()==1&&record_uncertain(o));
            fail_complete=write_fail_complete=false;
            setup(xp,k.amount,k.mode);write_target=target(k,xp);expected_raw=k.amount;expected_effect_mode=k.mode;
            const int prepared=lua();expect_native(apply);
            check(lua()==prepared&&(k.writer?CBMW_LastStatus():CBMA_LastStatus())==4&&record_uncertain(o));break;}
        case SETTER_IN_FLIGHT: { // A stat44 setter call inside this change's callbacks lands as it closes.
            const auto f=fallbacks();
            in_flight=[]{const auto x=read(subject,0x570);CBMW_Write(subject,0,1000,1);
                check(read(subject,0x570)==x&&CBMW_LastStatus()==10);};
            check(apply()==1&&read(effect,0x114)==1&&!journaled(k)&&no_record());in_flight=nullptr;
            const uint64_t sum=static_cast<uint64_t>(xp)+k.amount;
            const uint32_t committed=k.writer?target(k,xp):sum>0xffffffffull?0xffffffffu:static_cast<uint32_t>(sum);
            int last=0;CBMW_Fallbacks(&last);
            check(read(subject,0x570)==static_cast<uint32_t>(committed+2000u)&&fallbacks()==f+2&&last==10);
            check((k.writer?CBMW_LastStatus():CBMA_LastStatus())==6&&lua()==lua_before+1);break;}
        case SETTER_STICKY: { // Behind this lifetime's uncertain journal a setter write is the game's own.
            fail_complete=write_fail_complete=true;check(apply()==1&&record_uncertain(k));
            fail_complete=write_fail_complete=false;const auto f=fallbacks();const int prepared=lua();
            CBMW_Write(subject,0,4321,0);
            check(read(subject,0x570)==4321&&CBMW_LastStatus()==4&&fallbacks()==f+1&&lua()==prepared&&record_uncertain(k));break;}
        }
        ++fault_cases;
    }
    subject=actor;
}
// CGameEffectList::HandleList 2.7.3.0 (0x1401E4F90) on synthetic nodes: an effect is
// resolved only while every earlier one returned nonzero; any +0x118 sets the list's
// repass flag; +0x114 removes it. ProcessEffectList (0x1403AC4E0-5CA) repeats the
// pass while a repass flag is set. Save-time op187 (special 1) are never done.
struct Node{unsigned char* effect;int(*resolve)(void*,void*);};
std::set<uint32_t> locals;
int set_local(void* e,void*){locals.insert(read(e,0x1c));return 1;}
int halt(void*,void*){return 0;} // A vanilla 0, as Q1b's op233: never done.
int award_node(void* e,void* s){return CBMA_ApplyEffect(e,s);}
int pass(std::vector<Node>& list,void* sprite,bool& repass){
    bool resolving=true;repass=false;
    for(size_t i=0;i<list.size();){
        auto* e=list[i].effect;
        resolving=resolving&&list[i].resolve(e,sprite)!=0;
        if(read(e,0x118))repass=true;
        if(read(e,0x114)){list.erase(list.begin()+static_cast<std::ptrdiff_t>(i));continue;}
        ++i;
    }
    return resolving;
}
int process(std::vector<Node>& list,void* sprite){
    int passes=0;bool repass=false;
    do{pass(list,sprite,repass);++passes;}while(repass&&passes<8);
    return passes;
}
void list19(){
    alignas(16) unsigned char stuck[EFFECT]{},local1[EFFECT]{},local2[EFFECT]{};
    write(local1,0x10,187);write(local1,0x1c,1);write(local2,0x10,187);write(local2,0x1c,2);
    const std::set<uint32_t> both{1,2};
    // Control: the model reproduces #19. A 0 ahead of the op187 freezes them on every
    // pass, so after a load the locals never return and a save then drops them.
    std::vector<Node> list{{stuck,halt},{local1,set_local},{local2,set_local}};
    check(process(list,actor)==1&&process(list,actor)==1&&locals.empty()&&list.size()==3);
    // A refused op104 ahead of two op187: original award, removed, locals resolve.
    subject=actor;new_lifetime();setup(1000,100);disposition=0;
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    auto f=fallbacks();
    check(process(list,actor)==2&&locals==both&&list.size()==2&&read(actor,0x570)==1100&&fallbacks()==f+1);
    // Defer: inside a save's scope the award waits without blocking; the next pass banks it.
    locals.clear();new_lifetime();setup(1000,100);disposition=1;
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    int passes=0;during_marshal=[&]{passes=process(list,actor);};
    CBMI_Marshal(actor,nullptr,nullptr,nullptr,0);during_marshal=nullptr;
    check(passes==1&&locals==both&&list.size()==3&&read(actor,0x570)==1000&&read(effect,0x114)==0);
    check(process(list,actor)==2&&list.size()==2&&read(actor,0x570)==1100&&!journal);
    // Withdrawn: changed during a journaled callback before any store. The award
    // waits without holding up the locals; the next pass banks it afresh.
    locals.clear();new_lifetime();setup(1000,100);disposition=1;mutate=1;
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    check(process(list,actor)==1&&locals==both&&list.size()==3&&read(actor,0x570)==1007&&!journal);
    mutate=0;check(process(list,actor)==2&&list.size()==2&&read(actor,0x570)==1107&&!journal);
    // Changed on every pass: one retry, then the original award, unbanked and counted.
    locals.clear();new_lifetime();setup(1000,100);mutate=1;f=fallbacks();
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    check(process(list,actor)==1&&locals==both&&list.size()==3);
    check(process(list,actor)==2&&list.size()==2&&read(actor,0x570)==1114&&fallbacks()==f+1&&!journal);
    // Complete: a journal that cannot be withdrawn keeps the award; it leaves without XP.
    locals.clear();new_lifetime();setup(1000,100);refuse_withdrawal=true;const int u=uncertains;
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    check(process(list,actor)==2&&locals==both&&list.size()==2&&read(actor,0x570)==1007&&journal&&uncertains==u+2);
    mutate=0;refuse_withdrawal=false;
    // Sticky: that actor's next award runs the original; nothing behind it is frozen.
    locals.clear();setup(1007,100);f=fallbacks();
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    check(process(list,actor)==2&&locals==both&&list.size()==2&&read(actor,0x570)==1107&&fallbacks()==f+1);
    // Writer path: a refused SET ahead of the op187 also resolves them.
    locals.clear();new_lifetime();setup(1000,1234,1);write_disposition=0;
    list={{effect,award_node},{local1,set_local},{local2,set_local}};
    check(process(list,actor)==2&&locals==both&&list.size()==2&&read(actor,0x570)==1234);
    write_disposition=1;disposition=1;new_lifetime();
}
// The retry table both bridges share holds 64 entries. More changing effects
// than that, across actors and both bridges, in a stable order: each defers at
// most once and then runs the original; none waits a third pass. A live entry
// is never evicted; a full table first drops entries whose lifetime ended; a
// resolved effect leaves no entry behind; a retry survives the defers between.
constexpr int CROWD=3,POOL=70,RETRIES=64;
alignas(16) unsigned char crowd[CROWD][ACTOR]{},pool[POOL][EFFECT]{};
void prepare(int i,bool writer){
    unsigned char* e=pool[i];std::memset(e,0,EFFECT);write(e,0x10,104);write(e,0x24,1);
    write(e,0x1c,writer?1234:32);write(e,0x20,writer?1:0);
}
int resolve(int i,int on=-1){ // On its own actor, or on crowd[on].
    subject=crowd[on<0?i%CROWD:on];effect=pool[i];journal=write_journal=false;
    expected_raw=read(effect,0x1c);expected_effect_mode=read(effect,0x20);write_target=expected_raw;
    return apply();
}
bool done(int i){return read(pool[i],0x114)==1;}
int tracked_node(void* e,void* s){
    effect=static_cast<unsigned char*>(e);subject=static_cast<unsigned char*>(s);journal=write_journal=false;
    return CBMA_ApplyEffect(e,s);
}
void retry_table(){
    for(auto& a:crowd){CBMI_Construct(a);write(a,0x570,1000);}
    disposition=write_disposition=1;
    for(int mix=0;mix<3;++mix){ // Awards, SET writes, then both alternating.
        for(int i=0;i<POOL;++i)prepare(i,mix==1||(mix==2&&i%2));
        int waits[POOL]{};const auto f=fallbacks();mutate=1;
        for(int pass=0;pass<3;++pass)for(int i=0;i<POOL;++i){
            if(done(i))continue; // Resolved: the list removed it.
            check(resolve(i)==1);
            if(!done(i))++waits[i];
        }
        mutate=0;
        for(int i=0;i<POOL;++i)check(done(i)&&waits[i]==(i<RETRIES?1:0));
        check(fallbacks()==f+POOL&&CBMA_LastStatus()==8);
    }
    // Nothing stays behind: a new change gets its retry, its banked pass resolves it.
    prepare(0,false);mutate=1;check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
    mutate=0;check(resolve(0)==1&&done(0)&&CBMA_LastStatus()==6);
    // A table full of live entries: the next change runs the original at once.
    mutate=1;for(int i=0;i<RETRIES;++i){prepare(i,i%2);check(resolve(i)==1&&!done(i));}
    prepare(RETRIES,false);check(resolve(RETRIES)==1&&done(RETRIES)&&CBMA_LastStatus()==8);
    // Lifetimes that ended leave first: then there is room for a new retry.
    CBMI_Destruct(crowd[0]);CBMI_Construct(crowd[0]);
    prepare(RETRIES+2,true);check(resolve(RETRIES+2)==1&&!done(RETRIES+2)&&CBMA_LastStatus()==4);
    // Every live entry was kept: its next change runs the original; the ended
    // lifetime's effects start again with a retry of the new lifetime.
    for(int i=0;i<RETRIES;++i){
        check(resolve(i)==1&&done(i)==(i%CROWD!=0)&&CBMA_LastStatus()==(i%CROWD!=0?8:4));
        if(!done(i))check(resolve(i)==1&&done(i)&&CBMA_LastStatus()==8);
    }
    check(resolve(RETRIES+2)==1&&done(RETRIES+2)&&CBMA_LastStatus()==8);
    for(bool writer:{false,true}){
        // A reused address: an effect resolved without reaching the change check
        // (its record insert failed, 5) leaves no entry; a new effect there that
        // changes gets a retry of its own.
        prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
        mutate=0;fail_allocation=true;check(resolve(0)==1&&done(0)&&CBMA_LastStatus()==5&&!fail_allocation);
        mutate=1;prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
        check(resolve(0)==1&&done(0)&&CBMA_LastStatus()==8);
        // A reused address whose entry stays: the effect deferred, then left
        // unresolved with its lifetime, or with its list while its actor lives on.
        // A new effect there, of the next lifetime or of another actor, that
        // changes gets a retry of its own; the old entry goes with it.
        prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
        CBMI_Destruct(crowd[0]);CBMI_Construct(crowd[0]);
        prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
        check(resolve(0)==1&&done(0)&&CBMA_LastStatus()==8);
        prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
        prepare(0,writer);check(resolve(0,1)==1&&!done(0)&&CBMA_LastStatus()==4);
        check(resolve(0,1)==1&&done(0)&&CBMA_LastStatus()==8);
        prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4); // Nothing left of either.
        check(resolve(0)==1&&done(0)&&CBMA_LastStatus()==8);
        // A retry survives the defers between its passes: a save keeps it.
        prepare(0,writer);check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);
        int scopes=0;during_marshal=[&]{++scopes;check(resolve(0)==1&&!done(0)&&CBMA_LastStatus()==4);};
        CBMI_Marshal(crowd[0],nullptr,nullptr,nullptr,0);during_marshal=nullptr;
        check(scopes==1&&resolve(0)==1&&done(0)&&CBMA_LastStatus()==8);
    }
    // The 2.7.3.0 HandleList model, one actor's list of 70 changing awards: all
    // resolve within that one list processing, the last on its second pass.
    std::vector<Node> list;
    for(int i=0;i<POOL;++i){prepare(i,false);list.push_back({pool[i],tracked_node});}
    check(process(list,crowd[1])==3&&list.empty());
    mutate=0;subject=actor;effect=effect_buffer;
}
// A fallback that replaced the XP word, and only such a fallback, notes it for
// that lifetime; the runtime then takes the stored word (R.Snapshot).
void replaced_word(){
    subject=actor;effect=effect_buffer;
    struct Case{uint32_t xp,amount,mode;bool replaced;};
    for(const auto c:{Case{1000,32,0,false},Case{0xfffffff0,32,0,true}, // An award within the word, past it (wraps).
                      Case{600000,1234,1,true},Case{600000,50,2,true},    // SET, percentage.
                      Case{600000,0xffffff38,0,false},Case{100,0xfffffc18,0,true}}){ // A loss within it, below zero.
        new_lifetime();setup(c.xp,c.amount,c.mode);disposition=write_disposition=0; // Refused: the original runs.
        check(!replaced(subject));expect_native(apply);check(replaced(subject)==c.replaced);
        if(c.replaced){acknowledge(subject);check(!replaced(subject));}
    }
    // Not for banked changes or another lifetime. An unowned passthrough is the
    // original as it executes: uncounted, it notes a replaced word all the same.
    disposition=write_disposition=1;
    new_lifetime();setup(0xfffffff0,32);check(apply()==1&&read(subject,0x570)==0xffffffff&&!replaced(subject));
    new_lifetime();setup(600000,1234,1);write_target=expected_raw=1234;expected_effect_mode=1;
    check(apply()==1&&CBMW_LastStatus()==6&&!replaced(subject));
    disposition=write_disposition=2;const auto f=fallbacks();
    new_lifetime();setup(0xfffffff0,32);check(apply()==1&&CBMA_LastStatus()==1&&read(subject,0x570)==16&&replaced(subject));
    new_lifetime();setup(1000,32);check(apply()==1&&CBMA_LastStatus()==1&&read(subject,0x570)==1032&&!replaced(subject));
    new_lifetime();setup(600000,1234,1);check(apply()==1&&CBMW_LastStatus()==1&&read(subject,0x570)==1234&&replaced(subject));
    check(fallbacks()==f);
    disposition=write_disposition=0;new_lifetime();setup(0xfffffff0,32);expect_native(apply);check(replaced(subject));
    new_lifetime();check(!replaced(subject));disposition=write_disposition=1;
}
// A preparation that changes the operation: the original that then runs is
// classified as it executes, by the writer's own rule (CBMW_LeafReplaces).
// A SET or a percentage replaces the word, an addition only past either end.
// First pass: XP changed, the retry; second pass: the operation changed.
void mode_changes(){
    subject=actor;effect=effect_buffer;disposition=write_disposition=1;
    struct Case{uint32_t xp,amount,mode;int into;bool replaced;};
    for(const auto c:{Case{600000,32,0,5,true},Case{600000,32,0,6,true}, // An award into a SET (Codex), a percentage,
                      Case{600000,32,0,7,false},Case{500,32,0,7,true},    // a loss within the word, below zero,
                      Case{0xffffffe0,32,0,8,true},                         // another award past the top.
                      Case{600000,1234,1,8,false},Case{0xffffffe0,1234,1,8,true}, // A SET into an award within, past.
                      Case{600000,1234,1,6,true},Case{600000,50,2,7,false}, // A SET into a percentage, that into a loss.
                      Case{600000,32,0,10,false},Case{600000,1234,1,10,false}, // Into a nonpermanent SET: no XP word.
                      Case{600000,32,0,11,true},Case{600000,1234,1,11,true}, // The leaf ignores the opcode field.
                      Case{600000,32,0,12,false},Case{600000,1234,1,12,false}}){ // Mode 3 writes nothing.
        new_lifetime();setup(c.xp,c.amount,c.mode);
        expected_raw=write_target=c.amount;expected_effect_mode=c.mode;
        const auto status=[c]{return c.mode==0?CBMA_LastStatus():CBMW_LastStatus();};
        mutate=1;expect_defer(apply,nullptr,effect,changed);check(status()==4&&!replaced(subject));
        mutate=c.into;Copy copy(subject,effect);changed(copy.a.data(),copy.e.data());
        const int expected=leaf(copy.e.data(),copy.a.data()),n=calls;const auto f=fallbacks();
        check(apply()==expected&&calls==n+1&&fallbacks()==f+1&&copy.same()); // As the original leaf left it.
        check(status()==8&&no_record()&&replaced(subject)==c.replaced);mutate=0;
    }
}
// A preparation that changes the operation on the first pass: that pass defers
// (4) and the retry, unchanged, runs whatever the effect now reads. Each
// original that then runs is classified as it executes: banked (6) it replaces
// nothing; passed through (1, uncounted) or refused (5, counted) it notes a
// replaced word exactly where the leaf replaces it. Routes and notes are this
// table's own; values come from an independent run of the leaf.
void first_pass_changes(){
    subject=actor;effect=effect_buffer;
    enum Route{SHAPE,AWARD,WRITER}; // Neither bridge's shape (no runtime call), the award or the writer bridge.
    struct Case{uint32_t xp;int into;Route route;bool replaces;};
    const Case cases[]={{600000,5,WRITER,true},{600000,6,WRITER,true},     // A SET, a percentage,
        {600000,7,WRITER,false},{500,7,WRITER,true},                       // a loss within the word, below zero,
        {600000,8,AWARD,false},{0xffffffe0,8,AWARD,true},                  // an award within it, past the top;
        {600000,10,SHAPE,false},{600000,12,SHAPE,false},{600000,18,SHAPE,false}, // nonpermanent, mode 3, timing 2.
        {600000,11,SHAPE,true},                                            // Opcode field 187 (Codex): a SET,
        {600000,13,SHAPE,false},{0xffffffe0,13,SHAPE,true},                // an award within the word, past the top,
        {600000,14,SHAPE,false},{500,14,SHAPE,true},                       // a loss within it, below zero,
        {600000,15,SHAPE,true},{600000,16,SHAPE,false},{600000,17,SHAPE,false}}; // a percentage, mode 3, nonpermanent.
    for(const auto& k:{kinds[0],kinds[1]})for(const auto& c:cases)for(int retry:{1,2,0}){
        if(c.route==SHAPE&&retry!=1)continue; // No runtime call: the same passthrough for any disposition.
        new_lifetime();setup(c.xp,k.amount,k.mode);disposition=write_disposition=1;
        expected_raw=write_target=k.amount;expected_effect_mode=k.mode;
        mutate=c.into;const int w=withdrawals;expect_defer(apply,nullptr,effect,changed);mutate=0;
        check(CBMA_LastStatus()==4&&withdrawals==w+1&&no_record()&&!replaced(subject));
        disposition=write_disposition=retry;
        expected_raw=read(effect,0x1c);expected_effect_mode=read(effect,0x20);
        Copy copy(subject,effect);const int expected=leaf(copy.e.data(),copy.a.data());
        write_target=read(copy.a.data(),0x570); // A banked write plans what the leaf would store.
        const uint64_t sum=uint64_t(read(subject,0x570))+read(effect,0x1c);
        const bool banked=c.route!=SHAPE&&retry==1;
        const int n=calls;const auto f=fallbacks();const int result=apply();
        check(no_record()&&CBMA_LastStatus()==(banked?6:c.route==SHAPE||retry==2?1:5));
        if(banked){
            const uint32_t stored=c.route==WRITER?write_target:sum>0xffffffffull?0xffffffffu:static_cast<uint32_t>(sum);
            check(result==1&&read(subject,0x570)==stored&&read(effect,0x114)==1&&fallbacks()==f&&!replaced(subject));
        }else{
            check(result==expected&&calls==n+1&&copy.same()&&fallbacks()==f+(retry==0&&c.route!=SHAPE?1:0));
            check(replaced(subject)==c.replaces);
        }
    }
    // Codex's case: the first preparation makes an award a SET of 100000 with
    // opcode field 187; the retry passes it through, the leaf stores 100000 and
    // the runtime learns the word was replaced (with 199905 XP held above the
    // word it then reports 100000, not 299905: test_campaign_xp_native_runtime.py,
    // test_refused_set_takes_the_stored_word_at_export_reload_and_next_banking_point).
    new_lifetime();setup(600000,32);disposition=write_disposition=1;mutate=11;
    check(apply()==1&&CBMA_LastStatus()==4&&read(subject,0x570)==600000&&!replaced(subject));mutate=0;
    check(apply()==1&&CBMA_LastStatus()==1&&read(subject,0x570)==100000&&replaced(subject));
}
void* executable=nullptr; // The actual leaf's bytes, executable.
void configure(){
    executable=VirtualAlloc(nullptr,sizeof(native_leaf),MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    check(executable!=nullptr);std::memcpy(executable,native_leaf,sizeof(native_leaf));
    DWORD old;check(VirtualProtect(executable,sizeof(native_leaf),PAGE_EXECUTE_READ,&old)!=0);
    check(FlushInstructionCache(GetCurrentProcess(),executable,sizeof(native_leaf))!=0);
    leaf=reinterpret_cast<Apply>(executable);
}
void configure_bridges(){
    const auto lua_read_at=reinterpret_cast<uintptr_t>(lua_read),lua_push_at=reinterpret_cast<uintptr_t>(lua_push);
    CBMI_Config id{1,{reinterpret_cast<uintptr_t>(copy_actor),reinterpret_cast<uintptr_t>(marshal),1,1,
        reinterpret_cast<uintptr_t>(lifecycle),reinterpret_cast<uintptr_t>(lifecycle)},
        lua_read_at,lua_push_at,reinterpret_cast<uintptr_t>(lua_bool),
        reinterpret_cast<uintptr_t>(&strip),reinterpret_cast<uintptr_t>(&preview)};
    check(CBMI_Configure(&id));CBMI_Construct(actor);
    CBMA_Config cfg{1,reinterpret_cast<uintptr_t>(dispatch),reinterpret_cast<uintptr_t>(before),
        reinterpret_cast<uintptr_t>(complete),reinterpret_cast<uintptr_t>(uncertain),lua_read_at,lua_push_at};
    check(!CBMA_Configure(nullptr)&&CBMA_Configure(&cfg)&&!CBMA_Configure(&cfg));
    CBMW_Config writer{1,1,reinterpret_cast<uintptr_t>(write_before),reinterpret_cast<uintptr_t>(write_complete),
        reinterpret_cast<uintptr_t>(write_uncertain),1,1,1};check(CBMW_Configure(&writer));
}
// Another thread's lifetime event (no resolved path in 2.7.3.0, see
// main-thread-audit-2.7.3.txt) leaves every identity unknown for the rest of the
// process, so each case runs in a process of its own (award_check.ps1). Inside
// a preparation it proves no lifetime ended (not 11). At another address (0-4)
// the change goes on as one whose preparation saw values change, and nothing is
// dropped: without an identity no journal can be withdrawn, so a journaled
// change is done without XP, its journal holding it (7); one without a journal
// retries, then runs the original (3); a setter write queued inside lands as
// the change closes (10). A full retry table keeps every live entry. At the
// actor's own address (5-8: destroyed, another actor B constructed there) the
// bank cannot tell whether it still is the actor it prepared, so nothing is
// written there: a journaled change is done without XP (7), one without a
// journal resolves next pass (4, whatever room the retry table has), and a
// setter write queued inside is kept, never written (CBMW_Kept). Codex's case
// is 5: B keeps its 10 XP and the queued 1000 is kept.
constexpr int FOREIGN_CASES=9;
// A table full of live retries (crowd actors, changed preparations): no room for another.
void fill_retries(){
    for(auto& a:crowd){CBMI_Construct(a);write(a,0x570,1000);}
    mutate=1;for(int i=0;i<RETRIES;++i){prepare(i,i%2);check(resolve(i)==1&&!done(i));}
    mutate=0;subject=actor;effect=effect_buffer;journal=write_journal=false;
}
std::string kept_count(){lua_pushed.clear();check(CBMA_LuaFallbacks(nullptr)==6);return lua_pushed[4];}
std::string kept_text(){lua_pushed.clear();check(CBMA_LuaFallbacks(nullptr)==6);return lua_pushed[5];}
int foreign_case(int scenario){
    configure();configure_bridges();subject=actor;effect=effect_buffer;new_lifetime();
    CBMI_View id{};check(CBMI_Query(subject,&id));
    const auto ended=CBMW_Ended();auto f=fallbacks();disposition=write_disposition=1;
    switch(scenario){
    case 0: // A journaled award.
        setup(600000,32);mutate=9;check(apply()==1&&CBMA_LastStatus()==7&&read(effect,0x114)==1);
        check(read(subject,0x570)==600000&&journal&&CBMA_Holds(subject,id.incarnation)==2&&fallbacks()==f);break;
    case 1: // An award without a journal: the retry, then the original.
        setup(600000,32);disposition=0;mutate=9;
        check(apply()==1&&CBMA_LastStatus()==4&&read(effect,0x114)==0&&read(subject,0x570)==600000&&fallbacks()==f);
        mutate=0;expect_native(apply);check(CBMA_LastStatus()==3&&read(subject,0x570)==600032);f=fallbacks();break;
    case 2: { // A table full of live retries: none is evicted, the original at once (8).
        for(auto& a:crowd){CBMI_Construct(a);write(a,0x570,1000);}
        mutate=1;for(int i=0;i<RETRIES;++i){prepare(i,i%2);check(resolve(i)==1&&!done(i));}
        subject=actor;effect=effect_buffer;setup(600000,32);disposition=0;mutate=9;f=fallbacks();
        check(apply()==1&&CBMA_LastStatus()==8&&read(effect,0x114)==1&&read(subject,0x570)==600032&&fallbacks()==f+1);
        mutate=0;f=fallbacks(); // Each live entry's effect then resolves: the original, no identity.
        for(int i=0;i<RETRIES;++i)check(resolve(i)==1&&done(i)&&CBMA_LastStatus()==3);
        check(fallbacks()==f+RETRIES);subject=actor;effect=effect_buffer;f=fallbacks();break;}
    case 3: // A journaled SET.
        setup(600000,1234,1);expected_raw=write_target=1234;expected_effect_mode=1;mutate=9;
        check(apply()==1&&CBMW_LastStatus()==7&&read(effect,0x114)==1&&read(subject,0x570)==600000);
        check(write_journal&&CBMW_Holds(subject,id.incarnation)==2&&fallbacks()==f);break;
    case 4: { // A setter write queued inside a journaled award.
        setup(600000,32);mutate=9;in_flight=[]{CBMW_Write(subject,0,1000,1);check(CBMW_LastStatus()==10);};
        check(apply()==1&&CBMA_LastStatus()==7&&read(effect,0x114)==1&&read(subject,0x570)==601000);
        int last=0;CBMW_Fallbacks(&last);check(fallbacks()==f+1&&last==10);in_flight=nullptr;f=fallbacks();
        check(kept_count()=="0");break;}
    case 5: { // Codex: a setter write queued inside a journaled award; A replaced by B.
        setup(600000,32);mutate=19;in_flight=[]{CBMW_Write(subject,0,1000,1);check(CBMW_LastStatus()==10);};
        const int calls_before=calls;
        check(apply()==1&&CBMA_LastStatus()==7&&read(effect,0x114)==1&&read(effect,0x118)==1&&calls==calls_before);
        check(read(subject,0x570)==10&&journal&&CBMA_Holds(subject,id.incarnation)==2&&fallbacks()==f);
        check(kept_count()=="1"&&kept_text()=="add 1000");in_flight=nullptr;break;}
    case 6: { // An award without a journal; A replaced by B; the retry table full of live entries.
        fill_retries();setup(600000,32);disposition=0;mutate=19;f=fallbacks();
        const int calls_before=calls;
        check(apply()==1&&CBMA_LastStatus()==4&&read(effect,0x114)==0&&read(effect,0x118)==0&&calls==calls_before);
        check(read(subject,0x570)==10&&fallbacks()==f&&kept_count()=="0");
        mutate=0;expect_native(apply);check(CBMA_LastStatus()==3&&read(subject,0x570)==42);f=fallbacks();break;}
    case 7: // A journaled SET; A replaced by B.
        setup(600000,1234,1);expected_raw=write_target=1234;expected_effect_mode=1;mutate=19;
        check(apply()==1&&CBMA_LastStatus()==7&&read(effect,0x114)==1&&read(effect,0x118)==1&&read(subject,0x570)==10);
        check(write_journal&&CBMW_Holds(subject,id.incarnation)==2&&fallbacks()==f&&kept_count()=="0");break;
    case 8: { // A SET without a journal; A replaced by B; the retry table full: resolved next pass, the original then.
        fill_retries();setup(600000,1234,1);expected_raw=write_target=1234;expected_effect_mode=1;write_disposition=0;
        mutate=19;f=fallbacks();const int calls_before=calls;
        check(apply()==1&&CBMA_LastStatus()==4&&read(effect,0x114)==0&&read(subject,0x570)==10&&calls==calls_before);
        check(fallbacks()==f&&kept_count()=="0");
        mutate=0;expect_native(apply);check(CBMA_LastStatus()==3&&read(subject,0x570)==1234);f=fallbacks();break;}
    default: check(false);
    }
    mutate=0;check(CBMW_Ended()==ended);
    // Every later change of any actor runs the original: no identity (3).
    const auto xp=read(subject,0x570);setup(xp,32);expect_native(apply);
    check(CBMA_LastStatus()==3&&read(subject,0x570)==xp+32&&fallbacks()==f+1);
    std::printf("{\"award_foreign_case\":%d,\"award_assertions\":%d,\"game_launched\":false}\n",scenario,checks);
    return 0;
}
}
int run(){
    configure();unconfigured();configure_bridges();
    const auto unconfigured_fallbacks=fallbacks();
    for(auto xp:{0u,160999u,499999u,0x7fffffffu,0xfffffffeu,0xffffffffu}){
        for(auto amount:{1u,2u,17u,0x7fffffffu}){
            setup(xp,amount);uint64_t old_overflow=overflow;
            check(CBMA_ApplyEffect(effect,actor)==1&&!journal);
            check(static_cast<uint64_t>(xp)+amount==read(actor,0x570)+overflow-old_overflow);
            check(read(effect,0x1c)==amount&&read(actor,0x1180)==4321&&read(actor,0x2ad0)==1234);
            CBMA_View absent{};check(!CBMA_Query(actor,effect,&absent));
        }
    }
    // Consecutive awards after saturation add only each after-split entitlement.
    setup(0xfffffff0,17);uint64_t old_overflow=overflow;
    check(CBMA_ApplyEffect(effect,actor)==1);write(effect,0x1c,27);
    check(CBMA_ApplyEffect(effect,actor)==1);
    check(read(actor,0x570)==0xffffffff&&overflow-old_overflow==29);
    // Compare untouched non-earned paths against independent original leaf runs.
    for(auto mode:{0u,1u,2u,9u})for(auto timing:{0u,1u})for(auto amount:{0u,27u,0xffffffe5u}){
        if(mode==0&&timing==1&&amount==27)continue;
        setup(1000,amount,mode,timing);
        alignas(16) unsigned char baseline_actor[sizeof(actor)],baseline_effect[EFFECT];
        std::memcpy(baseline_actor,actor,sizeof(actor));std::memcpy(baseline_effect,effect,EFFECT);
        int expected=leaf(baseline_effect,baseline_actor);int old_prepares=prepares;
        check(CBMA_ApplyEffect(effect,actor)==expected&&prepares==old_prepares);
        check(std::memcmp(actor,baseline_actor,sizeof(actor))==0&&std::memcmp(effect,baseline_effect,EFFECT)==0);
    }
    check(fallbacks()==unconfigured_fallbacks); // Unowned passthroughs are not fallbacks.
    disposition=2;setup(0xfffffff0,32);old_overflow=overflow;
    check(CBMA_ApplyEffect(effect,actor)==1&&read(actor,0x570)==16&&overflow==old_overflow);
    throw_native=true;setup(1000,1);
    try{CBMA_ApplyEffect(effect,actor);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="injected after native store");}
    check(read(actor,0x570)==1001&&!journal);throw_native=false;
    // A refused award, any Lua error included, runs the original award unbanked.
    disposition=0;setup(500000,32);int old_prepares=prepares;
    expect_native([]{return CBMA_ApplyEffect(effect,actor);});
    check(read(actor,0x570)==500032&&read(effect,0x114)==1&&prepares==old_prepares+1&&!journal&&CBMA_LastStatus()==5);
    // A nested resolution while this actor's award is in flight defers.
    disposition=1;setup(0xfffffff0,32);int old_calls=calls;
    in_flight=[]{expect_defer([]{return CBMA_ApplyEffect(effect,actor);});};
    check(CBMA_ApplyEffect(effect,actor)==1&&calls==old_calls+1);in_flight=nullptr;
    // A failed completion leaves an uncertain record. That lifetime's next award
    // runs the original unbanked; its journal awaits reconciliation.
    fail_complete=true;setup(0xfffffff0,32);
    check(CBMA_ApplyEffect(effect,actor)==1&&journal&&view().stage==CBMA_UNCERTAIN);
    check(read(effect,0x1c)==32&&read(actor,0x570)==0xffffffff);fail_complete=false;
    old_prepares=prepares;setup(1000,32);
    expect_native([]{return CBMA_ApplyEffect(effect,actor);});
    check(read(actor,0x570)==1032&&prepares==old_prepares&&journal&&view().stage==CBMA_UNCERTAIN&&CBMA_LastStatus()==4);
    new_lifetime();setup(0xfffffff0,32);throw_native=true;
    try{CBMA_ApplyEffect(effect,actor);check(false);}catch(const std::runtime_error& e){check(std::string(e.what())=="injected after native store");}
    check(journal&&view().stage==CBMA_UNCERTAIN&&read(effect,0x1c)==32&&view().post_base==0xffffffff);
    throw_native=false;new_lifetime();setup(0xfffffff0,32);corrupt_result=true;
    // The committed original's own 0 is passed on; the bridge adds none.
    check(CBMA_ApplyEffect(effect,actor)==0&&journal&&view().stage==CBMA_UNCERTAIN);
    check(uncertains==3);corrupt_result=false;new_lifetime();setup(1000,1);
    // Another thread: the original award; records stay host-only.
    old_prepares=prepares;
    expect_native([]{int foreign=-1;std::thread thread([&]{foreign=CBMA_ApplyEffect(effect,actor);});thread.join();return foreign;});
    check(read(actor,0x570)==1001&&prepares==old_prepares&&CBMA_LastStatus()==2);
    setup(1000,1);check(CBMA_ApplyEffect(effect,actor)==1&&read(actor,0x570)==1001&&!journal);
    // Real permanent effect routes execute the actual leaf's SET branch after
    // a planned account operation, then restore all original effect parameters.
    write_disposition=1;
    struct Case{uint32_t xp,raw,mode,target;};
    for(const auto c:{Case{1000,0xffffffe5,0,973},Case{0xffffffff,0xffffff38,0,0xffffff9b},
                      Case{600000,1234,1,1234},Case{1000,50,2,500},Case{0x80000000,100,2,0},Case{1000,0,0,1000}}){
        new_lifetime();setup(c.xp,c.raw,c.mode);write_target=c.target;expected_raw=c.raw;expected_effect_mode=c.mode;
        alignas(16) unsigned char expected_actor[sizeof(actor)],expected_effect[EFFECT];
        std::memcpy(expected_actor,actor,sizeof(actor));std::memcpy(expected_effect,effect,EFFECT);
        write(expected_effect,0x1c,c.target);write(expected_effect,0x20,1);check(leaf(expected_effect,expected_actor)==1);
        write(expected_effect,0x1c,c.raw);write(expected_effect,0x20,c.mode);
        in_flight=[]{expect_defer([]{return CBMA_ApplyEffect(effect,actor);});};
        check(CBMA_ApplyEffect(effect,actor)==1&&!write_journal&&CBMW_LastStatus()==6);in_flight=nullptr;
        check(std::memcmp(actor,expected_actor,sizeof(actor))==0&&std::memcmp(effect,expected_effect,EFFECT)==0);
    }
    // A refused write, any Lua error included, runs the original effect unbanked.
    new_lifetime();setup(600000,50,2);write_disposition=0;int old_writes=write_prepares;
    expect_native([]{return CBMA_ApplyEffect(effect,actor);});
    check(read(actor,0x570)==300000&&read(effect,0x114)==1&&write_prepares==old_writes+1&&CBMW_LastStatus()==5);
    // A failed completion leaves an uncertain writer record: the original next.
    setup(600000,50,2);write_disposition=1;expected_effect_mode=2;expected_raw=50;write_target=300000;write_fail_complete=true;
    check(CBMA_ApplyEffect(effect,actor)==1&&write_journal&&writer_view().stage==CBMW_UNCERTAIN);
    write_fail_complete=false;old_writes=write_prepares;setup(600000,50,2);
    expect_native([]{return CBMA_ApplyEffect(effect,actor);});
    check(read(actor,0x570)==300000&&write_prepares==old_writes&&write_journal&&CBMW_LastStatus()==4);
    new_lifetime();write_journal=false;setup(1000,17,1);expected_effect_mode=1;expected_raw=17;write_target=17;throw_native=true;
    try{CBMA_ApplyEffect(effect,actor);check(false);}catch(const std::runtime_error&e){check(std::string(e.what())=="injected after native store");}
    check(write_journal&&writer_view().post_base==17&&read(effect,0x1c)==17&&read(effect,0x20)==1);
    check(write_uncertains==2&&write_completes==7);throw_native=false;new_lifetime();write_journal=false;
    // No identity (an actor the lifetime hooks never saw): the original award.
    CBMI_Destruct(actor);setup(1000,1);
    expect_native([]{return CBMA_ApplyEffect(effect,actor);});
    check(read(actor,0x570)==1001&&CBMA_LastStatus()==3);
    check(CBMI_Copy(other,0,0,0,0)==actor);setup(0xfffffff0,32);old_prepares=prepares;
    // An ineligible actor's award is the original as it executes: here it wraps, noted.
    check(CBMA_ApplyEffect(effect,actor)==1&&prepares==old_prepares&&read(actor,0x570)==16&&replaced(actor));
    CBMI_Construct(second);matrix();list19();retry_table();replaced_word();mode_changes();first_pass_changes();
    // The runtime's count: all fallbacks, each bridge's last reason, and the
    // changes whose lifetime ended while the bank prepared them (11).
    lua_pushed.clear();check(CBMA_LuaFallbacks(nullptr)==6&&lua_pushed.size()==6);
    check(lua_pushed[0]==std::to_string(fallbacks())&&lua_pushed[3]==std::to_string(CBMW_Ended())&&CBMW_Ended()>0);
    check(lua_pushed[4]=="0"&&lua_pushed[5].empty()); // No setter write kept: no other thread's lifetime event here.
    check(VirtualFree(executable,0,MEM_RELEASE)!=0);
    std::printf("{\"award_assertions\":%d,\"fault_cases\":%d,\"actual_native_leaf_executed\":true,"
        "\"handle_list_model\":\"2.7.3.0\",\"game_launched\":false}\n",checks,fault_cases);
    return 0;
}
int main(int argc,char** argv){try{
    // award_native_test foreign N: one case of another thread's lifetime event.
    if(argc==3&&std::strcmp(argv[1],"foreign")==0){
        const int n=std::atoi(argv[2]);return n>=0&&n<FOREIGN_CASES?foreign_case(n):2;
    }
    return run();
}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
