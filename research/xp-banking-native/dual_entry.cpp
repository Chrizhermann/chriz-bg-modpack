#include "dual_entry.h"
#include <atomic>
#include <stdexcept>
#include <cstring>
namespace {
 CBMDE_Config config{};std::atomic<bool> ready{false};
 struct Scope {void* actor{};uint64_t incarnation{};uint8_t overall{},old{},before{},target{};bool query{};}scope;
 using Level=uint8_t(*)(const void*,uint8_t,uint8_t);
 bool identity(void* actor,uint64_t incarnation){
  CBMI_View v{};
  return reinterpret_cast<int(*)(const void*,CBMI_View*)>(config.identity_query)(actor,&v)
   &&v.eligible&&!v.serializing&&v.incarnation==incarnation
   &&reinterpret_cast<int(*)(const void*,uint64_t)>(config.identity_can_mutate)(actor,incarnation);
 }
 struct Clear {~Clear(){scope={};}};
 bool dispatch=false;
 void* selected(void* screen){
  if(!config.game||!config.get_deny||!screen)return nullptr;
  auto**vtable=*reinterpret_cast<void***>(screen);
  const auto slot=reinterpret_cast<int16_t(*)(void*,int)>(vtable[0x1c0/8])(screen,0);
  auto*game=reinterpret_cast<unsigned char*>(config.game);int16_t count=0;std::memcpy(&count,game+0x6630,2);
  if(slot<0||slot>=count)return nullptr;
  int32_t id=0;std::memcpy(&id,game+0x6618+slot*4,4);void*actor=nullptr;
  return reinterpret_cast<uint8_t(*)(int32_t,void**)>(config.get_deny)(id,&actor)==0?actor:nullptr;
 }
}
int CBMDE_Configure(const CBMDE_Config* c){
 if(!CBMDS_IsEngineThread()||ready||!c||c->abi!=1||!c->clickable||!c->next_level||!c->get_classes
  ||!c->get_class||!c->get_level||!c->set_level||!c->is_usable||!c->identity_query||!c->identity_can_mutate)return 0;
 config=*c;ready=true;return 1;
}
int CBMDE_Check(void* screen,void* actor,uint64_t incarnation,uint8_t before,uint8_t target){
 if(!CBMDS_IsEngineThread()||!ready||scope.actor||!screen||!actor||!incarnation||!before||target<=before)return -1;
 if(!identity(actor,incarnation))return -1;
 auto* b=static_cast<unsigned char*>(actor);void* type=b+0x4b50;
 uint8_t active=0,old=0;
 reinterpret_cast<void(*)(const void*,uint8_t*,uint8_t*)>(config.get_classes)(type,&active,&old);
 const auto overall=reinterpret_cast<uint8_t(*)(const void*)>(config.get_class)(type);
 if(!active||!old||active==old||active==overall
  ||reinterpret_cast<Level>(config.get_level)(b+0x1120,overall,old)!=before
  ||reinterpret_cast<int(*)(const void*,uint8_t,int)>(config.is_usable)(type,old,1))return -1;
 scope={actor,incarnation,overall,old,before,target,false};Clear clear;
 // Retains native local/multiplayer control, actor-state and effect checks.
 // A pending spell-pick may independently make the native button clickable;
 // require our private query actually ran, so that branch does not open this UI.
 const auto result=reinterpret_cast<int(*)(void*,void*)>(config.clickable)(screen,actor);
 if(!identity(actor,incarnation))return -1;
 return result&&scope.query?1:0;
}
void CBMDE_GetNextLevel(void* rules,void* type,void* stats){
 if(!ready||!CBMDS_IsEngineThread())throw std::runtime_error("Retired eligibility called off its engine thread");
 const bool selected=scope.actor&&type==static_cast<unsigned char*>(scope.actor)+0x4b50;
 if(selected&&(stats==static_cast<unsigned char*>(scope.actor)+0x1120||!identity(scope.actor,scope.incarnation)))
  throw std::runtime_error("Retired eligibility lost its private projection or actor lifetime");
 reinterpret_cast<void(*)(void*,void*,void*)>(config.next_level)(rules,type,stats);
 if(selected){
  if(!identity(scope.actor,scope.incarnation))throw std::runtime_error("Retired eligibility lifetime changed during query");
  reinterpret_cast<void(*)(void*,uint8_t,uint8_t,uint8_t)>(config.set_level)(stats,scope.overall,scope.old,scope.target);
  scope.query=true;
 }
}
int CBMDE_Clickable(void* screen,void* actor){
 if(!ready||!CBMDS_IsEngineThread())return 0;
 const auto ordinary=reinterpret_cast<int(*)(void*,void*)>(config.clickable)(screen,actor);
 if(scope.actor||dispatch||!config.eligible_lua)return ordinary;
 dispatch=true;int64_t result=-1;
 try{result=reinterpret_cast<int64_t(*)(void*)>(config.eligible_lua)(actor);}catch(...){dispatch=false;throw;}
 dispatch=false;
 if(result==1)return 1;if(result==0)return ordinary;return 0;
}
void CBMDE_Click(void* screen){
 if(!ready||!CBMDS_IsEngineThread()||!config.on_click||dispatch)return;
 if(scope.actor){reinterpret_cast<void(*)(void*)>(config.on_click)(screen);return;}
 void*actor=selected(screen);if(!actor)return;
 if(!config.route_lua){reinterpret_cast<void(*)(void*)>(config.on_click)(screen);return;}
 dispatch=true;int64_t result=-1;
 try{result=reinterpret_cast<int64_t(*)(void*)>(config.route_lua)(actor);}catch(...){dispatch=false;throw;}
 dispatch=false;
 if(result==0)reinterpret_cast<void(*)(void*)>(config.on_click)(screen);
 // 1 handled by detached page; any other value/error rejects with no fallback.
}
int CBMDE_Open(void* screen,void* actor,uint64_t incarnation,uint8_t before,uint8_t target){
 if(!ready||!CBMDS_IsEngineThread()||dispatch||!config.on_click||selected(screen)!=actor)return -1;
 const int allowed=CBMDE_Check(screen,actor,incarnation,before,target);if(allowed!=1)return allowed;
 auto*type=static_cast<unsigned char*>(actor)+0x4b50;uint8_t active=0,old=0;
 reinterpret_cast<void(*)(const void*,uint8_t*,uint8_t*)>(config.get_classes)(type,&active,&old);
 const auto overall=reinterpret_cast<uint8_t(*)(const void*)>(config.get_class)(type);
 scope={actor,incarnation,overall,old,before,target,false};Clear clear;
 reinterpret_cast<void(*)(void*)>(config.on_click)(screen);
 CBMDS_View view{};
 return scope.query&&CBMDS_Query(actor,&view)&&view.incarnation==incarnation&&view.phase==CBMDS_PREVIEW?1:-1;
}
