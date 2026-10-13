// Scope protocol fixtures. Fake originals are not native reward acceptance.
#include "dual_combined_preview.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>
namespace{
 unsigned char actor[0x6000]{},before[0xca8]{};uint32_t phase=CBMDS_PREPARING;
 const auto mainThread=std::this_thread::get_id();
 uint64_t session=3;int nextCalls=0,hpCalls=0,copies=0,destroyed=0;bool usable=false;
 int stockMerges=0,ownedMerges=0,restores=0,completes=0,dormant=0;
 int active=3,oldPips=2,stockReads=0,stockWrites=0,ownedWrites=0;
 int refreshes=0;
 void refresh(void*s,int n){assert(s==actor&&n==1&&actor[0x4ba4]==1);++refreshes;}
 int32_t getActive(void*,uint32_t){++stockReads;return 7;}
 int32_t getInactive(void*,uint32_t){++stockReads;return 0;}
 void setActive(void*,uint32_t,int32_t,int){++stockWrites;}
 int readActive(const void*s,uint32_t stat,uint32_t*v){assert(s==actor&&stat==89);*v=active;return 1;}
 int readOld(const void*s,uint32_t stat,uint32_t*v,uint32_t*p){assert(s==actor&&stat==89);*v=oldPips;*p=1;return 1;}
 int ownSet(void*s,uint64_t n,uint64_t inc,const char* owner,uint32_t stat,uint32_t p){
  assert(s==actor&&n==session&&inc==5&&owner[0]=='a'&&stat==89&&phase==CBMDS_PREVIEW);active=p;++ownedWrites;return 1;
 }
 std::vector<CBMDH_Sample> samples;
 void classes(const void*,uint8_t*a,uint8_t*o){*a=1;*o=2;}
 uint8_t cls(const void*){return 7;}
 uint8_t level(const void*s,uint8_t,uint8_t c){return static_cast<const uint8_t*>(s)[c==2?0x46:0x48];}
 void set(void*s,uint8_t,uint8_t c,uint8_t n){static_cast<uint8_t*>(s)[c==2?0x46:0x48]=n;}
 int isUsable(const void*,uint8_t,int){return usable;}
 void construct(void*s){std::memset(s,0,0xca8);}
 void copy(void*a,const void*b){++copies;std::memcpy(a,b,0xca8);}
 void destruct(void*){++destroyed;}
 void next(void*,void*,void*s){++nextCalls;set(s,7,1,13);}
 void merge(void*s){assert(s==actor);++stockMerges;}
 int apply(void*s,uint64_t n,uint64_t inc,const char* owner,const CBMDL_ProfChoice* rows,uint32_t count,uint64_t*t){
  assert(s==actor&&n==session&&inc==5&&owner[0]=='a'&&phase==CBMDS_PREPARING);
  assert(count==1&&rows[0].stat==89&&rows[0].delta==1);++ownedMerges;*t=51;return 1;
 }
 int restore(void*s,uint64_t n,uint64_t inc,uint64_t t){assert(s==actor&&n==session&&inc==5&&t==51&&phase==CBMDS_CANCELING);++restores;return 1;}
 int complete(void*s,uint64_t n,uint64_t inc,uint64_t t){assert(s==actor&&n==session&&inc==5&&(t==51||t==52)&&phase==CBMDS_COMMITTING);++completes;return 1;}
 int persist(void*s,uint64_t n,uint64_t inc,const char* owner,const CBMDL_ProfChoice* rows,uint32_t count,uint64_t*t){
  assert(s==actor&&n==session&&inc==5&&owner[0]=='a'&&phase==CBMDS_COMMITTING);
  assert(count==1&&rows[0].stat==89&&rows[0].delta==1);++dormant;*t=52;return 1;
 }
 int beginActive(void*s,uint64_t n,uint64_t inc,const char* owner,uint64_t*t){
  assert(s==actor&&n==session&&inc==5&&owner[0]=='a'&&phase==CBMDS_PREPARING);*t=51;return 1;
 }
 int specials=0;
 void special(void*s,const void*b){assert(s==actor&&b!=before&&level(b,7,2)==11&&level(b,7,1)==1);++specials;}
 int skillWrites=0;
 int applySkills(void*,void*s,uint8_t a,uint8_t o,uint32_t xp,uint32_t kit,const CBMDP_SkillChoices*c,uint32_t*unused){
  assert(s==actor&&a==1&&o==2&&xp==550000&&kit==16385&&level(actor+0x1120,7,2)==8&&level(actor+0x1120,7,1)==1);
  assert(c->before[0]==10&&c->selected[0]==12);actor[0x5c2]=12;*unused=0;++skillWrites;return 0;
 }
 int32_t hp(void*,void*,void*b,void*a,uint8_t con){
  ++hpCalls;assert(con==18&&b!=before&&level(b,7,2)==11&&level(a,7,2)==11);
  assert(level(b,7,1)==1&&level(a,7,1)==13);
  CBMDH_Record(12,4);CBMDH_Record(13,5);return 9;
 }
}
int CBMDS_IsEngineThread(){return std::this_thread::get_id()==mainThread;}
int CBMDS_Query(const void*s,CBMDS_View*v){
 if(!CBMDS_IsEngineThread()||s!=actor)return 0;
 *v={};v->phase=phase;v->session=session;v->incarnation=5;v->owner[0]='a';return 1;
}
void CBMDH_Record(uint32_t n,int32_t hp)noexcept{samples.push_back({n,hp});}
int main(){
 CBMDL_Config c{1,(uintptr_t)&next,(uintptr_t)&hp,(uintptr_t)&classes,(uintptr_t)&cls,
  (uintptr_t)&level,(uintptr_t)&set,(uintptr_t)&isUsable,(uintptr_t)&construct,(uintptr_t)&copy,(uintptr_t)&destruct,
  (uintptr_t)&merge,(uintptr_t)&apply,(uintptr_t)&restore,(uintptr_t)&complete,(uintptr_t)&persist,
  (uintptr_t)&getActive,(uintptr_t)&getInactive,(uintptr_t)&setActive,(uintptr_t)&readActive,(uintptr_t)&readOld,(uintptr_t)&ownSet,(uintptr_t)&setActive,(uintptr_t)&refresh,(uintptr_t)&beginActive,(uintptr_t)&special,(uintptr_t)&applySkills};
 assert(CBMDL_Configure(&c)&&!CBMDL_Configure(&c));
 set(actor+0x1120,7,2,8);set(actor+0x1120,7,1,1);copy(before,actor+0x1120);copies=0;
 CBMDP_HPRolls old{};old.count=3;old.total=9;for(unsigned i=0;i<3;++i)old.samples[i]={9+i,3};
 assert(!CBMDL_Select(actor,9,5,1,2,8,11,&old));usable=true;
 assert(!CBMDL_Select(actor,3,5,1,2,8,11,&old));usable=false;
 assert(CBMDL_Select(actor,3,5,1,2,8,11,&old));
 CBMDP_SkillChoices selectedSkills{};selectedSkills.before[0]=10;selectedSkills.selected[0]=12;
 assert(CBMDL_SelectSkills(actor,3,5,550000,16385,&selectedSkills));
 CBMDL_GetNextLevel(nullptr,actor+0x4b68,actor+0x1120);
 assert(nextCalls==1&&level(actor+0x1120,7,2)==11&&level(before,7,2)==8&&skillWrites==1&&actor[0x5c2]==12);
 assert(CBMDL_GetHitPoints(nullptr,actor+0x4b68,before,actor+0x1120,18)==18);
 assert(copies==1&&destroyed==1&&hpCalls==1&&samples.size()==5);
 int sum=0;for(unsigned i=0;i<5;++i){assert(samples[i].level==9+i);sum+=samples[i].rolled_hp;}assert(sum==18);
 assert(level(before,7,2)==8&&level(before,7,1)==1);
 std::thread wrong([&]{assert(!CBMDL_Select(actor,3,5,1,2,8,11,&old));
  try{CBMDL_GetNextLevel(nullptr,actor+0x4b68,actor+0x1120);assert(false);}catch(...){}
 });wrong.join();assert(nextCalls==1);
 ++session;set(actor+0x1120,7,2,8);CBMDL_GetNextLevel(nullptr,actor+0x4b68,actor+0x1120);
 assert(nextCalls==2&&level(actor+0x1120,7,2)==8);
 // Real native API boundaries are simulated here; record mutation/restore has
 // its independent native instruction proof in dual_prof_commit.py.
 CBMDL_ProfChoice row{89,1};
 assert(CBMDL_Select(actor,session,5,1,2,8,11,&old));
 assert(CBMDL_SelectProficiencies(actor,session,5,&row,1));
 assert(CBMDL_GetActive(actor,89)==3&&CBMDL_GetInactive(actor,89)==3&&stockReads==0);
 CBMDL_GetNextLevel(nullptr,actor+0x4b68,actor+0x1120);CBMDL_CombineAll(actor);
 assert(ownedMerges==1&&stockMerges==0);
 phase=CBMDS_COMMITTING;CBMDL_AddSpecial(actor,before);assert(specials==1&&level(before,7,2)==8);
 phase=CBMDS_PREPARING;
 assert(CBMDL_GetInactive(actor,89)==0);phase=CBMDS_PREVIEW;
 CBMDL_SetActive(actor,89,4,1);assert(ownedWrites==1&&stockWrites==0&&refreshes==1&&CBMDL_GetActive(actor,89)==4);
 try{CBMDL_SetInactive(actor,89,5,0);assert(false);}catch(...){}
 try{CBMDL_SetActive(actor,89,5,0);assert(false);}catch(...){}
 std::thread bad([&]{try{CBMDL_GetActive(actor,89);assert(false);}catch(...){}
  try{CBMDL_SetActive(actor,89,6,0);assert(false);}catch(...){} });bad.join();
 assert(ownedWrites==1&&stockWrites==0&&stockReads==0);
 phase=CBMDS_CANCELING;assert(CBMDL_AfterCancel(actor));assert(restores==1);
 assert(CBMDL_GetActive(actor,89)==7&&CBMDL_GetInactive(actor,89)==0&&stockReads==2);
 CBMDL_SetActive(actor,89,2,0);assert(stockWrites==1);
 phase=CBMDS_PREPARING;CBMDL_CombineAll(actor);assert(stockMerges==1);
 // A later active-only level-up may reactivate stored inert deltas even though
 // no further old levels are due. Target==before and zero old rolls are valid.
 CBMDP_HPRolls none{};assert(CBMDL_Select(actor,session,5,1,2,11,11,&none));
 assert(CBMDL_SelectProficiencies(actor,session,5,&row,1));CBMDL_CombineAll(actor);
 phase=CBMDS_COMMITTING;assert(CBMDL_AfterCommit(actor));assert(completes==1&&ownedMerges==2);
 // Old-only commit never reaches the merge call. It must not discard inert
 // choices through a fictitious native materialization/retirement operation.
 phase=CBMDS_PREPARING;assert(CBMDL_Select(actor,session,5,1,2,11,11,&none));
 assert(CBMDL_SelectProficiencies(actor,session,5,&row,1));phase=CBMDS_COMMITTING;
 assert(CBMDL_AfterCommit(actor)&&completes==2&&dormant==1);
 phase=CBMDS_PREPARING;assert(CBMDL_Select(actor,session,5,1,2,11,11,&none));
 assert(CBMDL_SelectProficiencies(actor,session,5,&row,1));assert(CBMDL_AfterReset(actor));
 assert(CBMDL_GetInactive(actor,89)==3);phase=CBMDS_PREVIEW;
 CBMDL_SetActive(actor,89,5,1);assert(ownedWrites==2&&refreshes==2);
 phase=CBMDS_COMMITTING;assert(CBMDL_AfterCommit(actor)&&completes==4&&dormant==2);
 std::cout<<"Combined old-first projection protocol checks passed; native originals simulated\n";
}
