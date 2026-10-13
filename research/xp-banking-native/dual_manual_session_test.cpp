// Native-boundary protocol fixtures, not gameplay reward simulation.
#include "dual_manual_session.h"
#include "dual_combined_preview.h"
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <thread>
namespace {
unsigned char actor[0x6000]{},screen[0xb00]{};uint64_t incarnation=7;
int begins=0,commits=0,cancels=0,prepares=0,completes=0,uncertain=0,resets=0;
bool roll=true,failCommit=false;
int64_t beginDecision=CBMDS_BEGIN_OWNED;
bool bindBeforePass=false;
bool serializing=false;
int canMutate(const void* s,uint64_t expected){return s==actor&&expected==incarnation&&!serializing;}
int identify(const void* s,CBMI_View* out){if(s!=actor)return 0;*out={};out->incarnation=incarnation;out->eligible=true;std::memset(out->owner_token,'a',32);return 1;}
int64_t begin(void* s){CBMDS_View v{};assert(CBMDS_Query(s,&v)&&v.phase==CBMDS_PREPARING&&v.incarnation==7);
 ++begins;if(beginDecision!=CBMDS_BEGIN_OWNED){if(bindBeforePass)assert(CBMDS_BindOwner(s,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));return beginDecision;}
 assert(CBMDS_BindOwner(s,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));return beginDecision;}
int prepare(void* s){CBMDS_View v{};assert(CBMDS_Query(s,&v)&&v.phase==CBMDS_COMMITTING);++prepares;return 1;}
int complete(void*){++completes;return !failCommit;}int cancel(void*){++cancels;return 1;}int fault(void*){++uncertain;return 1;}
void clear(){uintptr_t zero=0;std::memcpy(screen+0x9a0,&zero,8);std::memcpy(screen+0x9a8,&zero,8);}
void reset(void*,void* s){
 ++resets;uintptr_t pointer=123;std::memcpy(screen+0x9a0,&pointer,8);std::memcpy(screen+0x9a8,&pointer,8);
 uint32_t cacheLevels[3]{10,12,0};uint16_t actual[3]{10,12,0};int32_t total=12;
 std::memcpy(actor+0x4e78,cacheLevels,12);std::memcpy(actor+0x1166,actual,6);std::memcpy(actor+0x4e84,&total,4);
 if(roll){CBMDH_Batch b{};b.abi=1;b.actor=reinterpret_cast<uintptr_t>(s);b.status=1;b.count=2;b.native_total=12;
  b.before_levels[0]=10;b.before_levels[1]=10;b.after_levels[0]=10;b.after_levels[1]=12;
  b.samples[0]={11,7};b.samples[1]={12,5};assert(CBMDS_OnHP(&b));}
}
void commit(void*,void*){++commits;clear();}void nativeCancel(void*){clear();}
void setter(void*,uint32_t,int32_t,int){}int32_t getter(void*,uint32_t){return 1;}
}
int CBMDL_AfterReset(void* s){CBMDS_View v{};assert(CBMDS_Query(s,&v)&&v.phase==CBMDS_PREPARING);return 1;}
int CBMDL_AfterCancel(void* s){CBMDS_View v{};assert(CBMDS_Query(s,&v)&&v.phase==CBMDS_CANCELING);
 uintptr_t backup=1;std::memcpy(&backup,screen+0x9a0,8);assert(!backup);return 1;}
int CBMDL_AfterCommit(void* s){CBMDS_View v{};assert(CBMDS_Query(s,&v)&&v.phase==CBMDS_COMMITTING);
 uintptr_t backup=1;std::memcpy(&backup,screen+0x9a0,8);assert(!backup);return 1;}
int main(int argc,char**argv){
 uint32_t flags=8;std::memcpy(actor+0x568,&flags,4);
 CBMDC_Config pc{1,reinterpret_cast<uintptr_t>(&setter),reinterpret_cast<uintptr_t>(&setter),reinterpret_cast<uintptr_t>(&getter),reinterpret_cast<uintptr_t>(&getter)};assert(CBMDC_Configure(&pc));
 CBMDS_Config c{1,reinterpret_cast<uintptr_t>(&reset),reinterpret_cast<uintptr_t>(&commit),reinterpret_cast<uintptr_t>(&nativeCancel),reinterpret_cast<uintptr_t>(&identify),reinterpret_cast<uintptr_t>(&canMutate),reinterpret_cast<uintptr_t>(&begin),reinterpret_cast<uintptr_t>(&prepare),reinterpret_cast<uintptr_t>(&complete),reinterpret_cast<uintptr_t>(&cancel),reinterpret_cast<uintptr_t>(&fault)};
 assert(CBMDS_Configure(&c));assert(!CBMDS_Configure(&c));
 if(argc>1){
  bindBeforePass=std::strcmp(argv[1],"bound-pass")==0;
  beginDecision=bindBeforePass?2:std::strtoll(argv[1],nullptr,10);
  CBMDS_Reset(screen,actor);CBMDS_View rejected{};
  assert(resets==0&&uncertain==1&&CBMDS_Query(actor,&rejected)&&rejected.phase==CBMDS_UNCERTAIN);
  assert(commits==0&&completes==0);return 0;
 }
 // An explicit unowned/excluded result runs the untouched native pipeline and
 // creates no session/receipt. A later owned actor can still use this screen.
 beginDecision=CBMDS_BEGIN_PASSTHROUGH;CBMDS_Reset(screen,actor);CBMDS_View pass{};
 assert(!CBMDS_Query(actor,&pass)&&begins==1&&resets==1&&uncertain==0);
 CBMDS_Cancel(screen);assert(cancels==0&&!CBMDS_Query(actor,&pass));
 beginDecision=CBMDS_BEGIN_OWNED;begins=0;resets=0;
 CBMDS_Reset(screen,actor);CBMDS_View v{};assert(CBMDS_Query(actor,&v)&&v.phase==CBMDS_PREVIEW&&v.hp_status==1&&!v.hp_cached);
 CBMDC_Event e{};e.sprite=reinterpret_cast<uintptr_t>(actor);e.screen=reinterpret_cast<uintptr_t>(screen);e.status=1;e.stat=101;e.before=1;e.after=2;assert(CBMDS_OnChoice(&e));
 assert(CBMDS_Query(actor,&v)&&v.choice_count==1);CBMDH_Batch b{};assert(CBMDS_GetHP(actor,&b)&&b.count==2);
 serializing=true;assert(!CBMDS_Query(actor,&v));serializing=false;
 std::thread wrong([&]{CBMDS_View x{};assert(!CBMDS_Query(actor,&x));CBMDS_Reset(screen,actor);CBMDS_Commit(screen,actor);CBMDS_Cancel(screen);assert(!CBMDS_OnHP(&b));assert(!CBMDS_OnChoice(&e));});wrong.join();
 assert(resets==1&&begins==1&&commits==0&&cancels==0);
 CBMDS_Cancel(screen);assert(cancels==1&&!CBMDS_Query(actor,&v));
 roll=false;CBMDS_Reset(screen,actor);assert(CBMDS_Query(actor,&v)&&v.hp_cached&&v.hp_status==1&&!v.choice_count);
 assert(CBMDS_GetHP(actor,&b)&&b.samples[0].rolled_hp==7);
 CBMDS_Commit(screen,actor);assert(commits==1&&prepares==1&&completes==1&&!CBMDS_Query(actor,&v));
 // Same address with NEW native lifetime cannot inherit old cached samples.
 incarnation=8;CBMDS_Config ignored{};(void)ignored;
 // begin callback deliberately expects7: switch back for one controlled cache miss.
 incarnation=7;CBMDS_Reset(screen,actor);assert(CBMDS_Query(actor,&v));incarnation=8;
 assert(!CBMDS_Query(actor,&v));CBMDS_Commit(screen,actor);assert(commits==1&&uncertain==1);
 std::cout<<"Native manual session protocol checks passed (simulated native screen)\n";
}
