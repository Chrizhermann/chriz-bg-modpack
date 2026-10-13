#include "dual_manual_session.h"
#include "dual_combined_preview.h"
#include <atomic>
#include <array>
#include <cstring>
#include <limits>
#include <map>
#include <string>
#include <vector>
namespace {
std::atomic<uint64_t> ids{1},thread_owner{0};std::atomic<bool> ready{false};
uint64_t self(){thread_local const auto n=ids.fetch_add(1);return n;}
bool host(){return ready.load()&&thread_owner.load()==self();}
CBMDS_Config config{};
CBMDS_View view{};CBMDH_Batch hp{};
std::vector<CBMDC_Event> choices;
uint64_t next_session=0;bool open=false,in_reset=false,ending=false;
struct Cached {CBMDH_Batch hp;std::array<char,33> owner;};
// Lifetime token prevents pointer reuse; cache intentionally survives Cancel.
std::map<uint64_t,Cached> cache;
using Pair=void(*)(void*,void*);using Single=void(*)(void*);using Callback=int(*)(void*);
bool identity(const void* sprite,CBMI_View& out){
 return reinterpret_cast<int(*)(const void*,CBMI_View*)>(config.identity_query)(sprite,&out)
    &&out.eligible&&!out.serializing&&out.incarnation&&out.owner_token[0]
    &&reinterpret_cast<int(*)(const void*,uint64_t)>(config.identity_can_mutate)(sprite,out.incarnation);
}
bool same(const void* sprite){
 CBMI_View id{};return open&&reinterpret_cast<uintptr_t>(sprite)==view.sprite&&identity(sprite,id)
    &&id.incarnation==view.incarnation;
}
bool callback(uintptr_t at,void* sprite){return reinterpret_cast<Callback>(at)(sprite)!=0;}
void uncertain(){
 view.phase=CBMDS_UNCERTAIN;
 try{callback(config.uncertain_lua,reinterpret_cast<void*>(view.sprite));}catch(...){}
}
bool backupsClear(const void* screen){
 uintptr_t a,b;std::memcpy(&a,static_cast<const unsigned char*>(screen)+0x9a0,8);
 std::memcpy(&b,static_cast<const unsigned char*>(screen)+0x9a8,8);return !a&&!b;
}
void matchCache(void* sprite){
 if(view.hp_status)return;
 uint32_t native_levels[3]{};int32_t total;
 std::memcpy(native_levels,static_cast<unsigned char*>(sprite)+0x4e78,12);
 std::memcpy(&total,static_cast<unsigned char*>(sprite)+0x4e84,4);
 const auto found=cache.find(view.incarnation);
 if(found==cache.end()){view.hp_status=2;return;}
 const auto& old=found->second.hp;
 bool equal=old.native_total==total&&std::memcmp(found->second.owner.data(),view.owner,33)==0;
 for(unsigned i=0;i<3;++i){
  uint16_t actual;std::memcpy(&actual,static_cast<unsigned char*>(sprite)+0x1166+i*2,2);
  equal=equal&&native_levels[i]==actual&&old.after_levels[i]==actual;
 }
 if(!equal){view.hp_status=2;return;}
 hp=old;hp.actor=reinterpret_cast<uintptr_t>(sprite);view.hp_status=old.status;view.hp_cached=1;
}
}
int CBMDS_Configure(const CBMDS_Config* c){
 if(!c||c->abi!=1||!c->reset||!c->commit||!c->cancel||!c->identity_query||!c->identity_can_mutate||!c->begin_lua
    ||!c->prepare_commit_lua||!c->complete_lua||!c->cancel_lua||!c->uncertain_lua)return 0;
 uint64_t empty=0;if(!thread_owner.compare_exchange_strong(empty,self()))return 0;
 config=*c;ready=true;return 1;
}
int CBMDS_IsEngineThread(){return host()?1:0;}
void CBMDS_Reset(void* screen,void* sprite){
 if(!host())return; // Entry installer runs on the proven engine thread only.
 CBMI_View id{};uint32_t flags;
 std::memcpy(&flags,static_cast<unsigned char*>(sprite)+0x568,4);
 // Before-dual HP is baseline evidence, not deferred-active-class ownership.
 if(!(flags&0x1f8)||!identity(sprite,id)){
  reinterpret_cast<Pair>(config.reset)(screen,sprite);return;
 }
 if(open||!backupsClear(screen)||next_session==std::numeric_limits<uint64_t>::max()){
  if(open)uncertain();return;
 }
 view={};hp={};choices.clear();view.session=++next_session;
 view.incarnation=id.incarnation;view.screen=reinterpret_cast<uintptr_t>(screen);view.sprite=reinterpret_cast<uintptr_t>(sprite);
 view.phase=CBMDS_PREPARING;open=true;
 try{
  const auto decision=reinterpret_cast<int64_t(*)(void*)>(config.begin_lua)(sprite);
  if(decision==CBMDS_BEGIN_PASSTHROUGH&&!view.owner[0]&&same(sprite)&&backupsClear(screen)){
   // Explicit campaign/account classification, never an error fallback. No
   // native Reset instruction has run and no owned journal was bound.
   open=false;view={};hp={};choices.clear();
   reinterpret_cast<Pair>(config.reset)(screen,sprite);return;
  }
  if(decision!=CBMDS_BEGIN_OWNED||!view.owner[0]){uncertain();return;}
  in_reset=true;reinterpret_cast<Pair>(config.reset)(screen,sprite);in_reset=false;
  if(!same(sprite)||backupsClear(screen)||!CBMDL_AfterReset(sprite)){uncertain();return;}
  matchCache(sprite);view.phase=CBMDS_PREVIEW;
 }catch(...){in_reset=false;uncertain();throw;}
}
void CBMDS_Commit(void* screen,void* sprite){
 if(!host())return;
 if(!open){reinterpret_cast<Pair>(config.commit)(screen,sprite);return;}
 if(ending||view.phase!=CBMDS_PREVIEW||view.screen!=reinterpret_cast<uintptr_t>(screen)||!same(sprite)
    ||view.hp_status!=1||CBMDC_Faulted()){uncertain();return;}
 try{
  view.phase=CBMDS_COMMITTING;ending=true;
  if(!callback(config.prepare_commit_lua,sprite)){ending=false;uncertain();return;}
  reinterpret_cast<Pair>(config.commit)(screen,sprite);
  if(!same(sprite)||!backupsClear(screen)||!CBMDL_AfterCommit(sprite)||!callback(config.complete_lua,sprite)){
   ending=false;uncertain();return;
  }
  ending=false;open=false;choices.clear();
 }catch(...){ending=false;uncertain();throw;}
}
void CBMDS_Cancel(void* screen){
 if(!host())return;
 if(!open){reinterpret_cast<Single>(config.cancel)(screen);return;}
 if(ending||view.screen!=reinterpret_cast<uintptr_t>(screen)||view.phase==CBMDS_UNCERTAIN){uncertain();return;}
 void* sprite=reinterpret_cast<void*>(view.sprite);
 if(!same(sprite)){uncertain();return;}
 try{
  ending=true;view.phase=CBMDS_CANCELING;
  reinterpret_cast<Single>(config.cancel)(screen);
  if(!same(sprite)||!backupsClear(screen)||!CBMDL_AfterCancel(sprite)||!callback(config.cancel_lua,sprite)){
   ending=false;uncertain();return;
  }
  ending=false;open=false;choices.clear();
 }catch(...){ending=false;uncertain();throw;}
}
int CBMDS_Query(const void* sprite,CBMDS_View* out){
 if(!host()||!out||!same(sprite))return 0;*out=view;out->choice_count=static_cast<uint32_t>(choices.size());return 1;
}
int CBMDS_BindOwner(const void* sprite,const char* saved){
 if(!host()||!same(sprite)||view.phase!=CBMDS_PREPARING||view.owner[0]||!saved)return 0;
 for(unsigned i=0;i<32;++i)if(!((saved[i]>='0'&&saved[i]<='9')||(saved[i]>='a'&&saved[i]<='f')))return 0;
 if(saved[32])return 0;std::memcpy(view.owner,saved,33);return 1;
}
int CBMDS_GetHP(const void* sprite,CBMDH_Batch* out){if(!host()||!out||!same(sprite)||!view.hp_status)return 0;*out=hp;out->status=view.hp_status;return 1;}
int CBMDS_GetChoice(const void* sprite,uint32_t index,CBMDC_Event* out){if(!host()||!out||!same(sprite)||index>=choices.size())return 0;*out=choices[index];return 1;}
int CBMDS_OnHP(const CBMDH_Batch* batch){
 if(!host()||!batch)return 0;
 if(!open)return 1; // Not a tracked dual; ordinary native calculation unchanged.
 if(!in_reset||!same(reinterpret_cast<void*>(batch->actor))){uncertain();return 0;}
 hp=*batch;view.hp_status=batch->status;
 if(batch->status==1){try{Cached c{};c.hp=*batch;std::memcpy(c.owner.data(),view.owner,33);cache[view.incarnation]=c;}catch(...){view.hp_status=2;}}
 return 1;
}
int CBMDS_OnChoice(const CBMDC_Event* event){
 if(!host()||!event)return 0;
 if(!open)return 1;
 if(view.phase!=CBMDS_PREVIEW||event->screen!=view.screen||!same(reinterpret_cast<void*>(event->sprite))){uncertain();return 0;}
 try{choices.push_back(*event);}catch(...){uncertain();return 0;}
 if(event->status!=1)uncertain();return 1;
}
