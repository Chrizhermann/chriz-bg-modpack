// Read-only installed old-class skill rows. Does not project the real actor.
#include "dual_skill_rows.h"
#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <cstring>
#include <new>
namespace {
struct Signature{uint32_t rva,size;uint64_t hash;};
struct Build{uint32_t image_size,cap_rva;Signature functions[8];};
#include "dual_skill_rows_builds.inc"
enum Function{ClassString,DestroyString,TableGet,SkillValue,SkillName,Classes,Atoi,Percentage};
struct String{const char* text;};
uint64_t hash(const unsigned char*p,size_t n){uint64_t h=14695981039346656037ULL;while(n--)h=(h^*p++)*1099511628211ULL;return h;}
bool matches(const unsigned char*p,size_t size,const Build&b){
 if(size!=b.image_size||b.cap_rva>size-4)return false;
 for(const auto&s:b.functions)if(s.rva>size||s.size>size-s.rva||hash(p+s.rva,s.size)!=s.hash)return false;
 return true;
}
}
extern "C" __declspec(noinline) uint32_t CBMDS_ThreadToken(){return GetCurrentThreadId();}
struct CBMDS_Binding{const unsigned char*image;const Build*build;uint32_t owner;};
namespace {
template<class T>T fn(const CBMDS_Binding&b,Function f){return reinterpret_cast<T>(const_cast<unsigned char*>(b.image)+b.build->functions[f].rva);}
using Class=String*(*)(void*,String*,uint8_t,uint32_t);
using Destroy=void(*)(String*);
using GetAt=String*(*)(void*,const String*,const String*);
struct OwnedString{String s{};Destroy destroy;~OwnedString(){destroy(&s);}};
const char* keys[]={"PICK_POCKETS","OPEN_LOCKS","FIND_TRAPS","MOVE_SILENTLY","HIDE_IN_SHADOWS","DETECT_ILLUSION","SET_TRAPS"};
}
int CBMDS_Bind(const void*image,size_t size,CBMDS_Binding**out){
 if(!image||!out)return CBMDS_INVALID;
 const Build*selected=nullptr;
 for(const auto&b:builds)if(matches(static_cast<const unsigned char*>(image),size,b))selected=&b;
 if(!selected)return CBMDS_IMAGE;
 auto*b=new(std::nothrow)CBMDS_Binding{static_cast<const unsigned char*>(image),selected,CBMDS_ThreadToken()};
 if(!b)return CBMDS_INVALID;*out=b;return CBMDS_OK;
}
bool CBMDS_OnThread(CBMDS_Binding*b){return b&&b->owner==CBMDS_ThreadToken();}
int CBMDS_Destroy(CBMDS_Binding*b){if(!CBMDS_OnThread(b))return CBMDS_THREAD;delete b;return CBMDS_OK;}
int CBMDS_Query(CBMDS_Binding*b,void*rules,void*actor,uint8_t old,uint32_t kit,CBMDS_Row*out){
 if(!b||!rules||!actor||!old||!out)return CBMDS_INVALID;
 if(!CBMDS_OnThread(b))return CBMDS_THREAD;
 if(!matches(b->image,b->build->image_size,*b->build))return CBMDS_IMAGE;
 uint8_t active=0,inactive=0;
 fn<void(*)(void*,uint8_t*,uint8_t*)>(*b,Classes)(static_cast<unsigned char*>(actor)+0x4b68,&active,&inactive);
 if(inactive!=old||active==old||active==0)return CBMDS_IDENTITY;
 int32_t cap=0;std::memcpy(&cap,b->image+b->build->cap_rva,4);
 if(cap<0)return CBMDS_RULES;
 // This is the native nonzero class-override lookup: old class/kit and class0,
 // taking max with zero. No temporary actor kit write or display-total replay.
 OwnedString oldName{{},fn<Destroy>(*b,DestroyString)},noneName{{},fn<Destroy>(*b,DestroyString)};
 fn<Class>(*b,ClassString)(rules,&oldName.s,old,kit);
 fn<Class>(*b,ClassString)(rules,&noneName.s,0,kit);
 CBMDS_Row result[7]{};
 for(uint32_t id=0;id<7;++id){
  const String key{keys[id]};
  const auto first=fn<GetAt>(*b,TableGet)(static_cast<unsigned char*>(rules)+0x3270,&oldName.s,&key);
  const auto second=fn<GetAt>(*b,TableGet)(static_cast<unsigned char*>(rules)+0x3270,&noneName.s,&key);
  if(!first||!second||!first->text||!second->text)return CBMDS_RULES;
  auto parse=fn<int32_t(*)(const char*)>(*b,Atoi);
  const auto percentage=std::max(0,std::max(parse(first->text),parse(second->text)));
  const auto value=fn<int32_t(*)(void*,uint8_t,uint8_t,int32_t)>(*b,SkillValue);
  const auto base=value(actor,static_cast<uint8_t>(id),old,1);
  const auto display=value(actor,static_cast<uint8_t>(id),old,0);
  if(base<0||base>255)return CBMDS_RULES;
  const int64_t bonus=static_cast<int64_t>(display)-base;
  const auto limit=static_cast<int32_t>(std::clamp(static_cast<int64_t>(cap)-bonus,int64_t{0},int64_t{255}));
  const auto name=fn<uint32_t(*)(uint8_t)>(*b,SkillName)(static_cast<uint8_t>(id));
  result[id]={id,name,base,display,limit,percentage};
 }
 std::memcpy(out,result,sizeof(result));return CBMDS_OK;
}
