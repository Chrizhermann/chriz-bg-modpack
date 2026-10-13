// Protocol fixtures only; actual native restriction instructions are separately
// exercised by dual_entry_probe.py, never by these simulated originals.
#include "dual_entry.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <thread>
namespace {
 unsigned char actor[0x6000]{},projected[0xca8]{};const auto mainThread=std::this_thread::get_id();
 int calls=0;bool controlled=true,blocked=false,serializing=false,usable=false,fail=false;
 uint64_t incarnation=8;
 unsigned char game[0x6700]{},screenBytes[0x100]{};void*vt[57]{};
 int16_t selectedIndex=0;int64_t routeResult=1,eligibleResult=0;int routed=0,originalClicks=0;bool opened=false;
 int16_t selected(void*,int n){assert(n==0);return selectedIndex;}
 uint8_t deny(int32_t id,void**out){assert(id==1);*out=actor;return 0;}
 int64_t eligible(void*s){assert(s==actor);return eligibleResult;}
 int64_t route(void*s){assert(s==actor);++routed;return routeResult;}
 int id(const void* s,CBMI_View*v){++calls;assert(s==actor);*v={};v->incarnation=incarnation;v->eligible=1;v->serializing=serializing;return 1;}
 int mutate(const void*,uint64_t i){return i==incarnation&&!serializing;}
 void classes(const void*,uint8_t*a,uint8_t*o){*a=1;*o=2;}
 uint8_t overall(const void*){return 7;}
 uint8_t level(const void*s,uint8_t,uint8_t){return static_cast<const unsigned char*>(s)[0x46];}
 void set(void*s,uint8_t,uint8_t,uint8_t n){static_cast<unsigned char*>(s)[0x46]=n;}
 int oldUsable(const void*,uint8_t,int){return usable;}
 void next(void*,void*,void*){if(fail)throw 3;}
 int clickable(void*,void* a){
  if(!controlled)return 0;std::memcpy(projected,actor+0x1120,sizeof(projected));
  CBMDE_GetNextLevel(nullptr,static_cast<unsigned char*>(a)+0x4b50,projected);
  return !blocked&&projected[0x46]!=actor[0x1166];
 }
 void originalClick(void*s){++originalClicks;if(CBMDE_Clickable(s,actor))opened=true;}
}
int CBMDS_IsEngineThread(){return std::this_thread::get_id()==mainThread;}
int CBMDS_Query(const void*s,CBMDS_View*v){if(s!=actor||!opened)return 0;*v={};v->phase=CBMDS_PREVIEW;v->incarnation=incarnation;return 1;}
int main(){
 CBMDE_Config c{1,(uintptr_t)&clickable,(uintptr_t)&next,(uintptr_t)&classes,(uintptr_t)&overall,
  (uintptr_t)&level,(uintptr_t)&set,(uintptr_t)&oldUsable,(uintptr_t)&id,(uintptr_t)&mutate,
  (uintptr_t)&originalClick,(uintptr_t)game,(uintptr_t)&deny,(uintptr_t)&eligible,(uintptr_t)&route};
 vt[0x1c0/8]=(void*)&selected;void**table=vt;std::memcpy(screenBytes,&table,sizeof(table));
 int16_t count=1;int32_t actorId=1;std::memcpy(game+0x6630,&count,2);std::memcpy(game+0x6618,&actorId,4);
 assert(CBMDE_Configure(&c)&&!CBMDE_Configure(&c));actor[0x1166]=8;int screen=0;
 const auto pristine=actor[0x1166];assert(CBMDE_Check(&screen,actor,8,8,11)==1&&actor[0x1166]==pristine);
 controlled=false;assert(CBMDE_Check(&screen,actor,8,8,11)==0);controlled=true;
 blocked=true;assert(CBMDE_Check(&screen,actor,8,8,11)==0);blocked=false;
 serializing=true;assert(CBMDE_Check(&screen,actor,8,8,11)==-1);serializing=false;
 usable=true;assert(CBMDE_Check(&screen,actor,8,8,11)==-1);usable=false;
 assert(CBMDE_Check(&screen,actor,9,8,11)==-1&&CBMDE_Check(&screen,actor,8,7,11)==-1);
 assert(CBMDE_Check(&screen,actor,8,8,8)==-1);
 fail=true;try{CBMDE_Check(&screen,actor,8,8,11);assert(false);}catch(int n){assert(n==3);}fail=false;
 assert(CBMDE_Check(&screen,actor,8,8,11)==1); // scope cleared after native exception
 auto savedCalls=calls;std::thread wrong([&]{assert(CBMDE_Check(&screen,actor,8,8,11)==-1);});wrong.join();assert(calls==savedCalls);
 projected[0x46]=8;CBMDE_GetNextLevel(nullptr,actor+0x4b50,projected);assert(projected[0x46]==8);
 eligibleResult=1;assert(CBMDE_Clickable(screenBytes,actor)==1);eligibleResult=-1;assert(!CBMDE_Clickable(screenBytes,actor));eligibleResult=0;
 CBMDE_Click(screenBytes);assert(routed==1&&originalClicks==0);
 routeResult=-1;CBMDE_Click(screenBytes);assert(routed==2&&originalClicks==0);
 routeResult=0;CBMDE_Click(screenBytes);assert(originalClicks==1&&!opened);
 assert(CBMDE_Open(screenBytes,actor,8,8,11)==1&&originalClicks==2&&opened);
 selectedIndex=-1;assert(CBMDE_Open(screenBytes,actor,8,8,11)==-1);CBMDE_Click(screenBytes);assert(originalClicks==2);
 const int savedRouted=routed;std::thread off([&]{CBMDE_Click(screenBytes);assert(!CBMDE_Clickable(screenBytes,actor));
  assert(CBMDE_Open(screenBytes,actor,8,8,11)==-1);});off.join();assert(routed==savedRouted&&originalClicks==2);
 std::cout<<"Retired-only entry eligibility protocol checks passed; no actor fields changed\n";
}
