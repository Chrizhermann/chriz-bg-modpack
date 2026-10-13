#include "dual_combined_preview.h"
#include <atomic>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>
namespace {
CBMDL_Config config{};std::atomic<bool> ready{false};
struct Plan{void* actor{};uint64_t session{},incarnation{};uint8_t active{},old{},overall{},before{},target{};CBMDP_HPRolls hp{};
 std::vector<CBMDL_ProfChoice> choices;uint64_t transaction{};bool choices_bound{},merged{},skills_bound{},skills_applied{};
 uint32_t old_xp{},old_kit{},unused_skills{};CBMDP_SkillChoices skills{};}plan;
bool thread(){return CBMDS_IsEngineThread()!=0;}
bool inScope(const void* type){
 if(!ready||!thread()||!plan.actor||type!=static_cast<unsigned char*>(plan.actor)+0x4b68)return false;
 CBMDS_View v{};return CBMDS_Query(plan.actor,&v)&&v.phase==CBMDS_PREPARING
  &&v.session==plan.session&&v.incarnation==plan.incarnation&&v.owner[0];
}
using Next=void(*)(void*,void*,void*);
using HP=int32_t(*)(void*,void*,void*,void*,uint8_t);
using Level=uint8_t(*)(const void*,uint8_t,uint8_t);
using SetLevel=void(*)(void*,uint8_t,uint8_t,uint8_t);
bool choicesScope(void* actor,CBMDS_View& v){
 return actor==plan.actor&&plan.choices_bound&&CBMDS_Query(actor,&v)
  &&(v.phase==CBMDS_PREPARING||v.phase==CBMDS_PREVIEW)
  &&v.session==plan.session&&v.incarnation==plan.incarnation&&v.owner[0];
}
}
int CBMDL_Configure(const CBMDL_Config* c){
 if(!thread()||ready||!c||c->abi!=1||!c->next_level||!c->get_hp||!c->get_classes||!c->get_class
  ||!c->get_level||!c->set_level||!c->is_usable||!c->stats_construct||!c->stats_copy||!c->stats_destruct)return 0;
 config=*c;ready=true;return 1;
}
int32_t CBMDL_GetActive(void* actor,uint32_t stat){
 if(!ready||!thread()||!config.get_active)throw std::runtime_error("Unconfigured class allocation read");
 CBMDS_View v{};
 if(!choicesScope(actor,v))return reinterpret_cast<int32_t(*)(void*,uint32_t)>(config.get_active)(actor,stat);
 uint32_t value=0;
 if(!config.prof_read_active||reinterpret_cast<int(*)(const void*,uint32_t,uint32_t*)>(config.prof_read_active)(actor,stat,&value)!=1)
  throw std::runtime_error("Owned active allocation could not be read");
 return static_cast<int32_t>(value);
}
int CBMDL_ReadOld(const void* actor,uint32_t stat,uint32_t* value){
 if(!ready||!thread()||!actor||!value||!config.prof_read_old)return 0;
 uint32_t pending=0;
 return reinterpret_cast<int(*)(const void*,uint32_t,uint32_t*,uint32_t*)>(config.prof_read_old)(actor,stat,value,&pending);
}
int CBMDL_IsDormant(const void* actor,uint8_t old){
 if(!ready||!thread()||!actor)return -1;
 const auto*type=static_cast<const unsigned char*>(actor)+0x4b68;uint8_t a=0,o=0;
 reinterpret_cast<void(*)(const void*,uint8_t*,uint8_t*)>(config.get_classes)(type,&a,&o);
 if(!o||o!=old||a==o)return -1;
 return reinterpret_cast<int(*)(const void*,uint8_t,int)>(config.is_usable)(type,o,1)?0:1;
}
int32_t CBMDL_GetInactive(void* actor,uint32_t stat){
 if(!ready||!thread()||!config.get_inactive)throw std::runtime_error("Unconfigured old allocation read");
 CBMDS_View v{};
 if(!choicesScope(actor,v))return reinterpret_cast<int32_t(*)(void*,uint32_t)>(config.get_inactive)(actor,stat);
 // Materialized merge has already put the old allocation into active bits.
 // Its inert carrier is retained only for Cancel/Commit, never counted twice.
 if(plan.merged)return 0;
 uint32_t value=0,pending=0;
 if(!config.prof_read_old||reinterpret_cast<int(*)(const void*,uint32_t,uint32_t*,uint32_t*)>(config.prof_read_old)(actor,stat,&value,&pending)!=1)
  throw std::runtime_error("Owned old allocation could not be read");
 for(const auto& row:plan.choices)if(row.stat==stat)value+=row.delta;
 if(value>7)throw std::runtime_error("Owned old allocation exceeds native storage");
 return static_cast<int32_t>(value);
}
void CBMDL_SetActive(void* actor,uint32_t stat,int32_t pips,int immediate){
 if(!ready||!thread()||!config.set_active)throw std::runtime_error("Unconfigured class allocation choice");
 CBMDS_View v{};
 if(!choicesScope(actor,v)){reinterpret_cast<void(*)(void*,uint32_t,int32_t,int)>(config.set_active)(actor,stat,pips,immediate);return;}
 using Set=int(*)(void*,uint64_t,uint64_t,const char*,uint32_t,uint32_t);
 if(v.phase!=CBMDS_PREVIEW||!plan.transaction||immediate!=1||pips<0||pips>7||!config.prof_set_active||!config.process_effects
  ||reinterpret_cast<Set>(config.prof_set_active)(actor,plan.session,plan.incarnation,v.owner,stat,static_cast<uint32_t>(pips))!=1)
  throw std::runtime_error("Owned proficiency choice did not complete; retain journal");
 // The actual +/- calls pass immediate=1. Preserve the native setter's force
 // reload branch after tracked record mutation; the caller then updates UI.
 const uint32_t force=1;std::memcpy(static_cast<unsigned char*>(actor)+0x4ba4,&force,4);
 reinterpret_cast<void(*)(void*,int)>(config.process_effects)(actor,1);
}
void CBMDL_SetInactive(void* actor,uint32_t stat,int32_t pips,int immediate){
 if(!ready||!thread()||!config.set_inactive)throw std::runtime_error("Unconfigured old allocation choice");
 CBMDS_View v{};
 if(choicesScope(actor,v))throw std::runtime_error("Retired choices belong to the detached first page");
 reinterpret_cast<void(*)(void*,uint32_t,int32_t,int)>(config.set_inactive)(actor,stat,pips,immediate);
}
int CBMDL_Select(void* actor,uint64_t session,uint64_t incarnation,uint8_t active,uint8_t old,
 uint8_t before,uint8_t target,const CBMDP_HPRolls* hp){
 if(!ready||!thread()||!actor||!hp||!before||target<before||!active||!old||active==old||plan.transaction||plan.choices_bound)return 0;
 CBMDS_View v{};if(!CBMDS_Query(actor,&v)||v.phase!=CBMDS_PREPARING||v.session!=session
  ||v.incarnation!=incarnation||!v.owner[0])return 0;
 auto* bytes=static_cast<unsigned char*>(actor);void* type=bytes+0x4b68;
 uint8_t a=0,o=0;reinterpret_cast<void(*)(const void*,uint8_t*,uint8_t*)>(config.get_classes)(type,&a,&o);
 const auto overall=reinterpret_cast<uint8_t(*)(const void*)>(config.get_class)(type);
 if(a!=active||o!=old||a==overall||reinterpret_cast<int(*)(const void*,uint8_t,int)>(config.is_usable)(type,old,1))return 0;
 if(reinterpret_cast<Level>(config.get_level)(bytes+0x1120,overall,old)!=before)return 0;
 if(hp->count!=uint32_t(target-before))return 0;
 int64_t total=0;for(uint32_t i=0;i<hp->count;++i){
  if(hp->samples[i].level!=uint32_t(before)+1+i||hp->samples[i].contribution<1)return 0;
  total+=hp->samples[i].contribution;
 }
 if(total!=hp->total||total>INT32_MAX)return 0;
 plan={};plan.actor=actor;plan.session=session;plan.incarnation=incarnation;plan.active=active;plan.old=old;
 plan.overall=overall;plan.before=before;plan.target=target;plan.hp=*hp;return 1;
}
int CBMDL_SelectProficiencies(void* actor,uint64_t session,uint64_t incarnation,const CBMDL_ProfChoice* rows,uint32_t count){
 if(!ready||!thread()||!actor||actor!=plan.actor||session!=plan.session||incarnation!=plan.incarnation
  ||(!rows&&count)||count>46||plan.choices_bound||!config.combine_all||!config.prof_apply||!config.prof_restore||!config.prof_complete||!config.prof_persist_dormant
  ||!inScope(static_cast<unsigned char*>(actor)+0x4b68))return 0;
 bool used[46]{};
 for(uint32_t i=0;i<count;++i){if(rows[i].stat<89||rows[i].stat>134||!rows[i].delta||rows[i].delta>7||used[rows[i].stat-89])return 0;
  used[rows[i].stat-89]=true;}
 if(count)plan.choices.assign(rows,rows+count);plan.choices_bound=true;return 1;
}
int CBMDL_SelectSkills(void* actor,uint64_t session,uint64_t incarnation,uint32_t xp,uint32_t kit,const CBMDP_SkillChoices*choices){
 if(!ready||!thread()||!choices||!config.apply_old_skills||actor!=plan.actor||session!=plan.session||incarnation!=plan.incarnation
  ||plan.skills_bound||!inScope(static_cast<unsigned char*>(actor)+0x4b68))return 0;
 for(unsigned i=0;i<7;++i)if(choices->selected[i]<choices->before[i])return 0;
 plan.old_xp=xp;plan.old_kit=kit;plan.skills=*choices;plan.skills_bound=true;return 1;
}
void CBMDL_CombineAll(void* actor){
 if(!ready||!thread()||!config.combine_all)throw std::runtime_error("Combined proficiency boundary is not configured");
 if(actor!=plan.actor||!inScope(static_cast<unsigned char*>(actor)+0x4b68)){
  reinterpret_cast<void(*)(void*)>(config.combine_all)(actor);return;
 }
 if(!plan.choices_bound||plan.transaction)throw std::runtime_error("Missing or already-applied retired proficiency choices");
 CBMDS_View v{};if(!CBMDS_Query(actor,&v))throw std::runtime_error("Retired merge lost its native owner");
 using Apply=int(*)(void*,uint64_t,uint64_t,const char*,const CBMDL_ProfChoice*,uint32_t,uint64_t*);
 const auto status=reinterpret_cast<Apply>(config.prof_apply)(actor,plan.session,plan.incarnation,v.owner,
  plan.choices.data(),static_cast<uint32_t>(plan.choices.size()),&plan.transaction);
 if(status!=1||!plan.transaction)throw std::runtime_error("Retired proficiency preview did not complete; journal retained");
 plan.merged=true;
 // Native caller retains its ordinary reactivation flag, effect recalculation
 // and active-choice setup. Only its aggregate allocation merge is replaced.
}
int CBMDL_AfterReset(void* actor){
 if(!ready)return 1;if(!thread())return 0;if(actor!=plan.actor)return 1;
 if(!inScope(static_cast<unsigned char*>(actor)+0x4b68)||!plan.choices_bound)return 0;
 if(plan.transaction)return 1;
 CBMDS_View v{};if(!CBMDS_Query(actor,&v)||!config.prof_begin_active)return 0;
 using Begin=int(*)(void*,uint64_t,uint64_t,const char*,uint64_t*);
 return reinterpret_cast<Begin>(config.prof_begin_active)(actor,plan.session,plan.incarnation,v.owner,&plan.transaction)==1&&plan.transaction?1:0;
}
void CBMDL_AddSpecial(void* actor,const void* before){
 if(!ready||!thread()||!config.add_special)throw std::runtime_error("Unconfigured combined ability delivery");
 using Add=void(*)(void*,const void*);
 if(actor!=plan.actor){reinterpret_cast<Add>(config.add_special)(actor,before);return;}
 CBMDS_View v{};
 if(!CBMDS_Query(actor,&v)||v.phase!=CBMDS_COMMITTING||v.session!=plan.session||v.incarnation!=plan.incarnation
  ||!v.owner[0]||!before||reinterpret_cast<Level>(config.get_level)(static_cast<unsigned char*>(actor)+0x1120,plan.overall,plan.old)!=plan.target)
  throw std::runtime_error("Combined ability delivery lost its selected class context");
 alignas(16) unsigned char projected[0xca8];
 reinterpret_cast<void(*)(void*)>(config.stats_construct)(projected);
 try{
  reinterpret_cast<void(*)(void*,const void*)>(config.stats_copy)(projected,before);
  reinterpret_cast<SetLevel>(config.set_level)(projected,plan.overall,plan.old,plan.target);
  // Native later replay grants old1..target only on actual reactivation. The
  // first pass grants only the active interval, so deferred old CLAB is not
  // granted twice. The source helper suppresses dormant class rewards itself.
  reinterpret_cast<Add>(config.add_special)(actor,projected);
 }catch(...){reinterpret_cast<void(*)(void*)>(config.stats_destruct)(projected);throw;}
 reinterpret_cast<void(*)(void*)>(config.stats_destruct)(projected);
}
namespace {
int finish(void* actor,uint32_t phase,uintptr_t at){
 if(!ready)return 1;
 if(!thread())return 0;
 if(actor!=plan.actor)return 1;
 CBMDS_View v{};if(!CBMDS_Query(actor,&v)||v.phase!=phase||v.session!=plan.session||v.incarnation!=plan.incarnation)return 0;
 if(plan.transaction){
  using Finish=int(*)(void*,uint64_t,uint64_t,uint64_t);
  if(!at||reinterpret_cast<Finish>(at)(actor,plan.session,plan.incarnation,plan.transaction)!=1)return 0;
 }
 plan={};return 1;
}
}
int CBMDL_AfterCancel(void* actor){return finish(actor,CBMDS_CANCELING,config.prof_restore);}
int CBMDL_AfterCommit(void* actor){
 if(ready&&thread()&&actor==plan.actor&&!plan.merged&&plan.choices_bound){
  CBMDS_View v{};if(!CBMDS_Query(actor,&v)||v.phase!=CBMDS_COMMITTING||v.session!=plan.session||v.incarnation!=plan.incarnation)return 0;
  const auto* type=static_cast<unsigned char*>(actor)+0x4b68;
  if(reinterpret_cast<int(*)(const void*,uint8_t,int)>(config.is_usable)(type,plan.old,1))return 0;
  if(plan.transaction){
   using Complete=int(*)(void*,uint64_t,uint64_t,uint64_t);
   if(!config.prof_complete||reinterpret_cast<Complete>(config.prof_complete)(actor,plan.session,plan.incarnation,plan.transaction)!=1)return 0;
   plan.transaction=0;
  }
  using Persist=int(*)(void*,uint64_t,uint64_t,const char*,const CBMDL_ProfChoice*,uint32_t,uint64_t*);
  if(!plan.choices.empty()&&(!config.prof_persist_dormant||reinterpret_cast<Persist>(config.prof_persist_dormant)(actor,plan.session,plan.incarnation,
   v.owner,plan.choices.data(),static_cast<uint32_t>(plan.choices.size()),&plan.transaction)!=1||!plan.transaction))return 0;
 }
 return finish(actor,CBMDS_COMMITTING,config.prof_complete);
}
void CBMDL_GetNextLevel(void* rules,void* type,void* stats){
 if(!ready||!thread())throw std::runtime_error("Combined manual level route is not configured on engine thread");
 const bool selected=inScope(type);
 if(selected&&stats!=static_cast<unsigned char*>(plan.actor)+0x1120)
  throw std::runtime_error("Combined manual level route received unrelated stats");
 if(selected&&plan.skills_bound&&!plan.skills_applied){
  using Apply=int(*)(void*,void*,uint8_t,uint8_t,uint32_t,uint32_t,const CBMDP_SkillChoices*,uint32_t*);
  if(reinterpret_cast<Apply>(config.apply_old_skills)(rules,plan.actor,plan.active,plan.old,plan.old_xp,plan.old_kit,&plan.skills,&plan.unused_skills)!=CBMDP_OK)
   throw std::runtime_error("Selected retired skill allocation did not complete; journal retained");
  plan.skills_applied=true;
 }
 reinterpret_cast<Next>(config.next_level)(rules,type,stats);
 if(selected){
  // This is the native SCREEN preview after its backup, never an autonomous
  // world-level write. Ordinary Reset/Cancel owns the backing base/derived copy.
  // The real retired choices/HP are retained in the same manual transaction.
  if(!inScope(type))throw std::runtime_error("Combined manual owner changed during native projection");
  reinterpret_cast<SetLevel>(config.set_level)(stats,plan.overall,plan.old,plan.target);
 }
}
int32_t CBMDL_GetHitPoints(void* rules,void* type,void* before,void* after,uint8_t constitution){
 if(!ready||!thread())throw std::runtime_error("Combined manual HP route is not configured on engine thread");
 if(!inScope(type))return reinterpret_cast<HP>(config.get_hp)(rules,type,before,after,constitution);
 if(after!=static_cast<unsigned char*>(plan.actor)+0x1120
  ||reinterpret_cast<Level>(config.get_level)(after,plan.overall,plan.old)!=plan.target)
  throw std::runtime_error("Combined HP target does not match selected retired level");
 alignas(16) unsigned char projected[0xca8];
 reinterpret_cast<void(*)(void*)>(config.stats_construct)(projected);
 int32_t active=0;
 try{
  reinterpret_cast<void(*)(void*,const void*)>(config.stats_copy)(projected,before);
  reinterpret_cast<SetLevel>(config.set_level)(projected,plan.overall,plan.old,plan.target);
  // Native GetHitPoints otherwise treats a changed retired level as unsupported
  // and skips active gains. A private BEFORE copy makes its active-class branch
  // calculate only levels beyond the new selected retired threshold.
  for(uint32_t i=0;i<plan.hp.count;++i)CBMDH_Record(plan.hp.samples[i].level,plan.hp.samples[i].contribution);
  active=reinterpret_cast<HP>(config.get_hp)(rules,type,projected,after,constitution);
  if(active<0||int64_t(active)+plan.hp.total>INT32_MAX)throw std::runtime_error("Combined native HP overflow");
 }catch(...){reinterpret_cast<void(*)(void*)>(config.stats_destruct)(projected);throw;}
 reinterpret_cast<void(*)(void*)>(config.stats_destruct)(projected);
 return active+plan.hp.total;
}
