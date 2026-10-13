#include "dual_skill_rows.h"
#include <charconv>
#include <string>
namespace{
CBMDS_Binding* binding=nullptr;uintptr_t to_string=0,push_string=0;
bool parse(void*L,int i,uint64_t&v,int base=10){size_t n=0;auto*s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(to_string)(L,i,&n);
 if(!s||!n||n>20)return false;auto r=std::from_chars(s,s+n,v,base);return r.ec==std::errc{}&&r.ptr==s+n;}
}
struct CBMDS_LuaConfig{uint32_t abi;uintptr_t image;size_t size;uintptr_t to_string,push_string;};
CBMDS_API int CBMDS_ConfigureLua(const CBMDS_LuaConfig*c){
 if(binding||!c||c->abi!=1||!c->image||!c->to_string||!c->push_string)return 0;
 CBMDS_Binding*b=nullptr;if(CBMDS_Bind(reinterpret_cast<const void*>(c->image),c->size,&b)!=CBMDS_OK)return 0;
 binding=b;to_string=c->to_string;push_string=c->push_string;return 1;
}
CBMDS_API int CBMDS_LuaRows(void*L){
 if(!CBMDS_OnThread(binding))return 0;
 uint64_t actor=0,rules=0,old=0,kit=0;
 if(!parse(L,1,actor,16)||!parse(L,2,rules,16)||!parse(L,3,old)||!parse(L,4,kit)
  ||!actor||!rules||old==0||old>255||kit>UINT32_MAX)return 0;
 CBMDS_Row rows[7]{};auto status=CBMDS_Query(binding,reinterpret_cast<void*>(rules),reinterpret_cast<void*>(actor),
  static_cast<uint8_t>(old),static_cast<uint32_t>(kit),rows);
 std::string encoded=std::to_string(status)+";";
 if(status==CBMDS_OK)for(const auto&r:rows)encoded+=std::to_string(r.id)+","+std::to_string(r.name_strref)+","+
  std::to_string(r.base)+","+std::to_string(r.display)+","+std::to_string(r.limit)+","+std::to_string(r.percentage)+";";
 reinterpret_cast<void(*)(void*,const char*)>(push_string)(L,encoded.c_str());return 1;
}
