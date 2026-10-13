#include "dual_manual_session.h"
#include "dual_entry.h"
#include "dual_combined_preview.h"
#include <charconv>
#include <cstring>
#include <vector>
namespace {
uintptr_t tolstring=0,pushstring=0;
const void* actor(void* L){
 if(!CBMDS_IsEngineThread()||!tolstring||!pushstring)return nullptr;
 size_t count=0;const char* s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,1,&count);
 uintptr_t pointer=0;if(!s||!count||count>16)return nullptr;
 const auto p=std::from_chars(s,s+count,pointer,16);return p.ec==std::errc{}&&p.ptr==s+count?reinterpret_cast<void*>(pointer):nullptr;
}
bool index(void* L,uint32_t& n){
 size_t count=0;const char* s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,2,&count);
 if(!s||!count)return false;const auto p=std::from_chars(s,s+count,n);return p.ec==std::errc{}&&p.ptr==s+count;
}
void text(void* L,const char* s){reinterpret_cast<void(*)(void*,const char*)>(pushstring)(L,s);}
template<class T>void number(void* L,T n){char b[32];const auto p=std::to_chars(b,b+31,n);*p.ptr=0;text(L,b);}
}
CBMDS_API int CBMDS_ConfigureLua(uintptr_t a,uintptr_t b){if(!CBMDS_IsEngineThread()||tolstring||pushstring||!a||!b)return 0;tolstring=a;pushstring=b;return 1;}
CBMDS_API int CBMDS_LuaQuery(void* L){
 CBMDS_View v{};if(!CBMDS_Query(actor(L),&v))return 0;
 const char* phases[]={"","preparing","preview","committing","canceling","uncertain"};
 text(L,phases[v.phase]);number(L,v.session);number(L,v.incarnation);text(L,v.owner);
 number(L,v.hp_status);number(L,v.hp_cached);number(L,v.choice_count);return 7;
}
CBMDS_API int CBMDS_LuaBindOwner(void* L){
 const void* sprite=actor(L);if(!sprite)return 0;size_t count=0;
 const auto owner=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,2,&count);
 if(!owner||count!=32)return 0;char stable[33]{};std::memcpy(stable,owner,32);
 if(!CBMDS_BindOwner(sprite,stable))return 0;text(L,"1");return 1;
}
CBMDS_API int CBMDS_LuaHP(void* L){
 CBMDH_Batch b{};if(!CBMDS_GetHP(actor(L),&b))return 0;
 number(L,b.status);number(L,b.native_total);number(L,b.count);
 for(auto n:b.before_levels)number(L,n);for(auto n:b.after_levels)number(L,n);return 9;
}
CBMDS_API int CBMDS_LuaHPSample(void* L){
 CBMDH_Batch b{};if(!CBMDS_GetHP(actor(L),&b))return 0;uint32_t n=0;if(!index(L,n)||n>=b.count)return 0;
 number(L,b.samples[n].level);number(L,b.samples[n].rolled_hp);return 2;
}
CBMDS_API int CBMDS_LuaChoice(void* L){
 const void* s=actor(L);if(!s)return 0;uint32_t n=0;if(!index(L,n))return 0;
 CBMDC_Event e{};if(!CBMDS_GetChoice(s,n,&e))return 0;
 number(L,e.stat);number(L,e.inactive);number(L,e.screen_mode);number(L,e.screen_selected_class);number(L,e.status);
 number(L,e.requested);number(L,e.before);number(L,e.after);return 8;
}
CBMDS_API int CBMDE_LuaCheck(void* L){
 const void* sprite=actor(L);if(!sprite)return 0;
 uint64_t values[4]{};
 for(int i=0;i<4;++i){
  size_t count=0;const char* s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,i+2,&count);
  if(!s||!count||count>20)return 0;
  const auto parsed=std::from_chars(s,s+count,values[i],i==0?16:10);
  if(parsed.ec!=std::errc{}||parsed.ptr!=s+count)return 0;
 }
 if(!values[0]||!values[1]||values[2]>255||values[3]>255)return 0;
 const auto result=CBMDE_Check(reinterpret_cast<void*>(values[0]),const_cast<void*>(sprite),values[1],
  static_cast<uint8_t>(values[2]),static_cast<uint8_t>(values[3]));
 number(L,result);return 1;
}
CBMDS_API int CBMDE_LuaOpen(void* L){
 const void* sprite=actor(L);if(!sprite)return 0;
 uint64_t values[4]{};
 for(int i=0;i<4;++i){size_t count=0;const char*s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,i+2,&count);
  if(!s||!count||count>20)return 0;const auto p=std::from_chars(s,s+count,values[i],i==0?16:10);
  if(p.ec!=std::errc{}||p.ptr!=s+count)return 0;}
 if(!values[0]||!values[1]||values[2]>255||values[3]>255)return 0;
 number(L,CBMDE_Open(reinterpret_cast<void*>(values[0]),const_cast<void*>(sprite),values[1],
  static_cast<uint8_t>(values[2]),static_cast<uint8_t>(values[3])));return 1;
}
namespace {
bool unsignedArg(void* L,int at,uint64_t& value){
 size_t n=0;const char*s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,at,&n);
 if(!s||!n||n>20)return false;auto p=std::from_chars(s,s+n,value);return p.ec==std::errc{}&&p.ptr==s+n;
}
bool pairsArg(void* L,int at,std::vector<CBMDL_ProfChoice>& rows,size_t limit){
 size_t n=0;const char*s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(tolstring)(L,at,&n);
 if(!s||n>8192)return false;const char*end=s+n;
 while(s<end){uint32_t key=0,value=0;auto k=std::from_chars(s,end,key);
  if(k.ec!=std::errc{}||k.ptr==end||*k.ptr!=':')return false;
  auto v=std::from_chars(k.ptr+1,end,value);
  if(v.ec!=std::errc{}||v.ptr==end||*v.ptr!=';'||rows.size()>=limit)return false;
  rows.push_back({key,value});s=v.ptr+1;
 }return true;
}
}
CBMDS_API int CBMDL_LuaSelect(void* L){
 auto*s=const_cast<void*>(actor(L));if(!s)return 0;
 uint64_t v[6]{};for(int i=0;i<6;++i)if(!unsignedArg(L,i+2,v[i]))return 0;
 if(!v[0]||!v[1]||v[2]>255||v[3]>255||v[4]>255||v[5]>255)return 0;
 std::vector<CBMDL_ProfChoice> rolls,choices;
 if(!pairsArg(L,8,rolls,255)||!pairsArg(L,9,choices,46))return 0;
 CBMDP_HPRolls hp{};int64_t total=0;
 for(const auto& r:rolls){if(!r.delta||r.delta>INT32_MAX)return 0;total+=r.delta;
  if(total>INT32_MAX)return 0;hp.samples[hp.count++]={r.stat,static_cast<int32_t>(r.delta)};}
 hp.total=static_cast<int32_t>(total);
 uint64_t xp=0,kit=0;std::vector<CBMDL_ProfChoice> beforeSkills,selectedSkills;
 if(!unsignedArg(L,10,xp)||!unsignedArg(L,11,kit)||xp>UINT32_MAX||kit>UINT32_MAX
  ||!pairsArg(L,12,beforeSkills,7)||!pairsArg(L,13,selectedSkills,7)||beforeSkills.size()!=7||selectedSkills.size()!=7)return 0;
 CBMDP_SkillChoices skills{};bool seen[7]{};
 for(const auto&r:beforeSkills){if(r.stat>6||r.delta>255||seen[r.stat])return 0;seen[r.stat]=true;skills.before[r.stat]=static_cast<uint8_t>(r.delta);}
 std::memset(seen,0,sizeof(seen));
 for(const auto&r:selectedSkills){if(r.stat>6||r.delta>255||seen[r.stat])return 0;seen[r.stat]=true;skills.selected[r.stat]=static_cast<uint8_t>(r.delta);}
 if(!CBMDL_Select(s,v[0],v[1],static_cast<uint8_t>(v[2]),static_cast<uint8_t>(v[3]),
  static_cast<uint8_t>(v[4]),static_cast<uint8_t>(v[5]),&hp))return 0;
 if(!CBMDL_SelectProficiencies(s,v[0],v[1],choices.data(),static_cast<uint32_t>(choices.size())))return 0;
 if(!CBMDL_SelectSkills(s,v[0],v[1],static_cast<uint32_t>(xp),static_cast<uint32_t>(kit),&skills))return 0;
 text(L,"1");return 1;
}
CBMDS_API int CBMDL_LuaReadOld(void* L){
 const auto*s=actor(L);uint32_t stat=0,value=0;
 if(!s||!index(L,stat)||!CBMDL_ReadOld(s,stat,&value))return 0;
 number(L,value);return 1;
}
CBMDS_API int CBMDL_LuaReadSkill(void* L){
 const auto*s=static_cast<const unsigned char*>(actor(L));uint32_t skill=0;
 if(!s||!index(L,skill)||skill>=7)return 0;
 constexpr size_t offsets[]={0x5c2,0x5bf,0x5c1,0x5c0,0x59d,0x5bc,0x5bd};
 number(L,static_cast<uint32_t>(s[offsets[skill]]));return 1;
}
CBMDS_API int CBMDL_LuaDormant(void* L){
 const auto*s=actor(L);uint32_t old=0;if(!s||!index(L,old)||old>255)return 0;
 number(L,CBMDL_IsDormant(s,static_cast<uint8_t>(old)));return 1;
}
