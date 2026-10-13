// Real Lua-provider bridge to the audited retired target resolver. Inert until
// explicitly configured from the engine thread. Read-only game queries only.
#include "dual_native_proficiency.h"
#include <charconv>
#include <cstring>
#include <string>
namespace {
 CBMDP_Binding* binding=nullptr;uintptr_t tolstring=0,pushstring=0;
 bool parse(void* L,int index,uint64_t& n,int base=10){
  size_t size=0;const char* s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,index,&size);
  if(!s||!size||size>20)return false;
  const auto result=std::from_chars(s,s+size,n,base);return result.ec==std::errc{}&&result.ptr==s+size;
 }
 void number(void* L,uint64_t n){char s[24];auto end=std::to_chars(s,s+23,n).ptr;*end=0;
  reinterpret_cast<void(*)(void*,const char*)>(pushstring)(L,s);}
}
struct CBMDP_LuaConfig {uint32_t abi;uintptr_t image;size_t size;uintptr_t to_string,push_string;};
CBMDP_API int CBMDP_ConfigureLua(const CBMDP_LuaConfig* c){
 if(binding||!c||c->abi!=1||!c->image||!c->size||!c->to_string||!c->push_string)return 0;
 CBMDP_Binding* b=nullptr;if(CBMDP_Bind(reinterpret_cast<const void*>(c->image),c->size,&b)!=CBMDP_OK)return 0;
 tolstring=c->to_string;pushstring=c->push_string;binding=b;return 1;
}
CBMDP_API int CBMDP_LuaOldTarget(void* L){
 if(!binding||!CBMDP_IsEngineThread())return 0;
 uint64_t actor=0,rules=0,active=0,old=0,xp=0;
 if(!parse(L,1,actor,16)||!parse(L,2,rules,16)||!parse(L,3,active)||!parse(L,4,old)||!parse(L,5,xp)
  ||!actor||!rules||active>255||old>255||xp>UINT32_MAX)return 0;
 // The public resolver checks thread ownership before dereferencing these
 // pointers or calling engine code. This bridge accepts internal EEex pointers,
 // never pointers reconstructed from a save/carrier or actor IDs.
 CBMDP_OldTarget result{};
 const auto status=CBMDP_GetOldTarget(binding,reinterpret_cast<void*>(rules),reinterpret_cast<void*>(actor+0x4b68),
  reinterpret_cast<void*>(actor+0x1120),static_cast<uint8_t>(active),static_cast<uint8_t>(old),static_cast<uint32_t>(xp),&result);
 number(L,status);if(status!=CBMDP_OK)return 1;
 number(L,result.before);number(L,result.target);return 3;
}
CBMDP_API int CBMDP_LuaOldPlan(void* L){
 if(!binding||!CBMDP_IsEngineThread())return 0;
 uint64_t actor=0,rules=0,active=0,old=0,xp=0,kit=0;
 if(!parse(L,1,actor,16)||!parse(L,2,rules,16)||!parse(L,3,active)||!parse(L,4,old)||!parse(L,5,xp)||!parse(L,6,kit)
  ||!actor||!rules||active>255||old>255||xp>UINT32_MAX||kit>UINT32_MAX)return 0;
 CBMDP_OldPlan result{};
 const auto status=CBMDP_GetOldPlan(binding,reinterpret_cast<void*>(rules),reinterpret_cast<void*>(actor+0x4b68),
  reinterpret_cast<void*>(actor+0x1120),static_cast<uint8_t>(active),static_cast<uint8_t>(old),static_cast<uint32_t>(xp),static_cast<uint32_t>(kit),&result);
 number(L,status);if(status!=CBMDP_OK)return 1;
 number(L,result.levels.before);number(L,result.levels.target);number(L,result.prof_points);number(L,result.skill_points);return 5;
}
CBMDP_API int CBMDP_LuaOldCap(void* L){
 if(!binding||!CBMDP_IsEngineThread())return 0;
 uint64_t actor=0,rules=0,active=0,old=0,xp=0,kit=0,stat=0;
 if(!parse(L,1,actor,16)||!parse(L,2,rules,16)||!parse(L,3,active)||!parse(L,4,old)||!parse(L,5,xp)
  ||!parse(L,6,kit)||!parse(L,7,stat)||!actor||!rules||active>255||old>255||xp>UINT32_MAX||kit>UINT32_MAX||stat>UINT32_MAX)return 0;
 CBMDP_ChoiceCap result{};
 const auto status=CBMDP_GetOldCap(binding,reinterpret_cast<void*>(rules),reinterpret_cast<void*>(actor+0x4b68),
  reinterpret_cast<void*>(actor+0x1120),static_cast<uint8_t>(active),static_cast<uint8_t>(old),static_cast<uint32_t>(xp),
  static_cast<uint32_t>(kit),static_cast<uint32_t>(stat),&result);
 number(L,status);if(status!=CBMDP_OK)return 1;
 number(L,result.effective_limit);return 2;
}
CBMDP_API int CBMDP_LuaOldRoll(void* L){
 if(!binding||!CBMDP_IsEngineThread())return 0;
 uint64_t actor=0,rules=0,active=0,old=0,xp=0,kit=0;
 if(!parse(L,1,actor,16)||!parse(L,2,rules,16)||!parse(L,3,active)||!parse(L,4,old)||!parse(L,5,xp)||!parse(L,6,kit)
  ||!actor||!rules||active>255||old>255||xp>UINT32_MAX||kit>UINT32_MAX)return 0;
 CBMDP_HPRolls hp{};
 // Exact constitution byte passed by native ResetLevelUpPanel to GetHitPoints.
 const auto constitution=*reinterpret_cast<const uint8_t*>(actor+0x795);
 const auto status=CBMDP_RollOldPlan(binding,reinterpret_cast<void*>(rules),reinterpret_cast<void*>(actor+0x4b68),
  reinterpret_cast<void*>(actor+0x1120),static_cast<uint8_t>(active),static_cast<uint8_t>(old),static_cast<uint32_t>(xp),
  static_cast<uint32_t>(kit),constitution,&hp);
 number(L,status);if(status!=CBMDP_OK)return 1;
 std::string encoded;
 for(uint32_t i=0;i<hp.count;++i)encoded+=std::to_string(hp.samples[i].level)+":"+std::to_string(hp.samples[i].contribution)+";";
 number(L,hp.total);reinterpret_cast<void(*)(void*,const char*)>(pushstring)(L,encoded.c_str());return 3;
}
// Typed engine call from the owned manual Reset boundary, not a Lua mutation API.
CBMDP_API int CBMDP_ApplySelectedOldSkills(void* rules,void* actor,uint8_t active,uint8_t old,
 uint32_t xp,uint32_t kit,const CBMDP_SkillChoices* choices,uint32_t* unused){
 if(!binding||!CBMDP_IsEngineThread())return CBMDP_WRONG_THREAD;
 return CBMDP_ApplyOldPlanSkills(binding,rules,actor,active,old,xp,kit,choices,unused);
}
