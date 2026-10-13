// Research-only Lua C API transport. Lua/provider addresses are resolved by
// the explicit local binder; no hard-coded Lua DLL or global EEex replacement.
#include "dual_old_hla.h"
#include <charconv>
#include <string>
#include <vector>
#include <cstring>
namespace {
uintptr_t to_string=0,push_string=0;
bool text(void* L,int index,std::string& out){
 size_t size=0;const auto* s=reinterpret_cast<const char*(*)(void*,int,size_t*)>(to_string)(L,index,&size);
 if(!s)return false;out.assign(s,size);return out.find('\0')==std::string::npos;
}
bool parse(const std::string& s,uint64_t& out,int base=10){
 if(s.empty())return false;auto r=std::from_chars(s.data(),s.data()+s.size(),out,base);
 return r.ec==std::errc{}&&r.ptr==s.data()+s.size();
}
bool number(void* L,int index,uint64_t& out,int base=10){std::string s;return text(L,index,s)&&parse(s,out,base);}
void push(void* L,const char* s){reinterpret_cast<void(*)(void*,const char*)>(push_string)(L,s);}
void push(void* L,int64_t n){push(L,std::to_string(n).c_str());}
void hex(void* L,uint64_t n){char s[17];auto r=std::to_chars(s,s+16,n,16);*r.ptr=0;push(L,s);}
bool unpack(void* L,int index,std::vector<std::string>& out){
 std::string s;if(!text(L,index,s))return false;size_t at=0;
 while(at<s.size()){
  auto colon=s.find(':',at);if(colon==s.npos)return false;uint64_t len=0;
  if(!parse(s.substr(at,colon-at),len)||len>s.size()-colon-1)return false;
  at=colon+1;out.emplace_back(s.substr(at,static_cast<size_t>(len)));at+=static_cast<size_t>(len);
 }
 return out.size()<=UINT32_MAX;
}
bool rows(const std::vector<std::string>& fields,std::vector<CBMDHLA_Row>& out){
 if(fields.size()%9)return false;out.resize(fields.size()/9);
 for(size_t i=0;i<out.size();++i){auto& r=out[i];const auto* f=&fields[i*9];uint64_t values[4]{};
  if(f[0].size()>8)return false;std::memcpy(r.icon,f[0].data(),f[0].size());
  for(size_t j=0;j<4;++j)if(!parse(f[j+1],values[j])||values[j]>UINT32_MAX)return false;
  r.name_strref=static_cast<uint32_t>(values[0]);r.min_level=static_cast<int32_t>(static_cast<uint32_t>(values[1]));
  r.max_level=static_cast<int32_t>(static_cast<uint32_t>(values[2]));r.max_rank=static_cast<int32_t>(static_cast<uint32_t>(values[3]));
  r.effect=f[5].c_str();r.prerequisite=f[6].c_str();r.excluded_by=f[7].c_str();r.alignment=f[8].c_str();
 }return true;
}
}
CBMDHLA_API int CBMDHLA_ConfigureLua(const CBMDHLA_LuaConfig* c){
 if(to_string||!c||c->abi!=1||!c->to_string||!c->push_string)return 0;
 to_string=c->to_string;push_string=c->push_string;return 1;
}
CBMDHLA_API int CBMDHLA_LuaOpen(void* L){
 if(!to_string)return 0;
 uint64_t actor=0,cls=0,kit=0,before=0,after=0;
 if(!number(L,1,actor,16)||!number(L,2,cls)||!number(L,3,kit)||!number(L,4,before)||!number(L,5,after)
  ||!actor||cls>255||kit>UINT32_MAX||before>255||after>255)return 0;
 CBMDHLA_View v{};int ok=CBMDHLA_Open(reinterpret_cast<void*>(actor),static_cast<uint8_t>(cls),
  static_cast<uint32_t>(kit),static_cast<uint8_t>(before),static_cast<uint8_t>(after),&v);
 push(L,ok);if(!ok){push(L,CBMDHLA_LastStatus());return 2;}
 hex(L,v.handle);push(L,v.points);push(L,v.native_capped_points);push(L,v.row_count);push(L,v.eligibility_flags);return 6;
}
CBMDHLA_API int CBMDHLA_LuaRow(void* L){
 if(!to_string)return 0;uint64_t handle=0,index=0;
 if(!number(L,1,handle,16)||!number(L,2,index)||index>UINT32_MAX)return 0;
 CBMDHLA_Row r{};const int ok=CBMDHLA_ReadRow(handle,static_cast<uint32_t>(index),&r);push(L,ok);if(!ok)return 1;
 push(L,r.icon);push(L,r.name_strref);push(L,r.min_level);push(L,r.max_level);push(L,r.max_rank);
 push(L,r.effect);push(L,r.prerequisite);push(L,r.excluded_by);push(L,r.alignment);return 10;
}
CBMDHLA_API int CBMDHLA_LuaChoose(void* L){
 if(!to_string)return 0;uint64_t handle=0,actor=0,index=0;
 std::vector<std::string> chosen,pending;
 if(!number(L,1,handle,16)||!number(L,2,actor,16)||!actor||!number(L,3,index)||index>UINT32_MAX
  ||!unpack(L,4,chosen)||!unpack(L,5,pending))return 0;
 std::vector<uint32_t> indices;for(const auto& s:chosen){uint64_t n=0;if(!parse(s,n)||n>UINT32_MAX)return 0;indices.push_back(static_cast<uint32_t>(n));}
 std::vector<CBMDHLA_Row> deferred(pending.size());for(size_t i=0;i<pending.size();++i)deferred[i].effect=pending[i].c_str();
 push(L,CBMDHLA_CanChoose(handle,reinterpret_cast<void*>(actor),static_cast<uint32_t>(index),indices.data(),static_cast<uint32_t>(indices.size()),
  deferred.data(),static_cast<uint32_t>(deferred.size())));return 1;
}
CBMDHLA_API int CBMDHLA_LuaClose(void* L){
 if(!to_string)return 0;uint64_t id=0;if(!number(L,1,id,16))return 0;push(L,CBMDHLA_Close(id));return 1;
}
CBMDHLA_API int CBMDHLA_LuaDeliver(void* L){
 if(!to_string)return 0;uint64_t actor=0,cls=0;std::string owner;std::vector<std::string> fields;std::vector<CBMDHLA_Row> descriptors;
 if(!number(L,1,actor,16)||!actor||!number(L,2,cls)||cls>255||!text(L,3,owner)||!unpack(L,4,fields)||!rows(fields,descriptors))return 0;
 CBMDHLA_DeliveryResult result{};const int ok=CBMDHLA_Deliver(reinterpret_cast<void*>(actor),static_cast<uint8_t>(cls),owner.c_str(),descriptors.data(),static_cast<uint32_t>(descriptors.size()),&result);
 push(L,ok);push(L,result.completed);push(L,result.uncertain);return 3;
}
CBMDHLA_API int CBMDHLA_LuaPrepareManual(void* L){
 if(!to_string)return 0;uint64_t actor=0,token=0;std::string owner;std::vector<std::string> effects;
 if(!number(L,1,actor,16)||!actor||!text(L,2,owner)||!unpack(L,3,effects))return 0;
 std::vector<CBMDHLA_Row> pending(effects.size());for(size_t i=0;i<effects.size();++i)pending[i].effect=effects[i].c_str();
 push(L,CBMDHLA_PrepareManual(reinterpret_cast<void*>(actor),owner.c_str(),pending.data(),static_cast<uint32_t>(pending.size()),&token));hex(L,token);return 2;
}
CBMDHLA_API int CBMDHLA_LuaClearManual(void* L){
 if(!to_string)return 0;uint64_t token=0;if(!number(L,1,token,16))return 0;push(L,CBMDHLA_ClearManual(token));return 1;
}
