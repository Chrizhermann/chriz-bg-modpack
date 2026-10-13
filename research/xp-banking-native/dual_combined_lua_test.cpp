// Real Lua bridge parser/thread protocol; native reward helpers are explicit
// doubles in this file. Their real instructions are checked separately.
#include "dual_combined_preview.h"
#include "dual_entry.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <sstream>
#include <thread>
#include <vector>
#include <string>
extern "C" int CBMDS_ConfigureLua(uintptr_t,uintptr_t);
extern "C" int CBMDL_LuaSelect(void*);
extern "C" int CBMDL_LuaReadOld(void*);
extern "C" int CBMDL_LuaReadSkill(void*);
extern "C" int CBMDL_LuaDormant(void*);
namespace{
 const auto owner=std::this_thread::get_id();unsigned char sprite[0x6000]{};int providerCalls=0,selections=0,profs=0,skills=0;
 struct Lua{std::vector<std::string> args,out;};
 const char* get(void* p,int i,size_t*n){++providerCalls;auto&v=static_cast<Lua*>(p)->args;
  if(i<1||size_t(i)>v.size())return nullptr;*n=v[i-1].size();return v[i-1].c_str();}
 void push(void*p,const char*s){++providerCalls;static_cast<Lua*>(p)->out.emplace_back(s);}
}
int CBMDS_IsEngineThread(){return std::this_thread::get_id()==owner;}
int CBMDS_Query(const void*,CBMDS_View*){return 0;}
int CBMDS_BindOwner(const void*,const char*){return 0;}
int CBMDS_GetHP(const void*,CBMDH_Batch*){return 0;}
int CBMDS_GetChoice(const void*,uint32_t,CBMDC_Event*){return 0;}
int CBMDE_Check(void*,void*,uint64_t,uint8_t,uint8_t){return 0;}
int CBMDE_Open(void*,void*,uint64_t,uint8_t,uint8_t){return 0;}
int CBMDL_ReadOld(const void*s,uint32_t n,uint32_t*v){assert(s==sprite&&n==89);*v=3;return 1;}
int CBMDL_IsDormant(const void*s,uint8_t n){assert(s==sprite&&n==2);return 1;}
int CBMDL_Select(void*s,uint64_t session,uint64_t inc,uint8_t a,uint8_t o,uint8_t before,uint8_t after,const CBMDP_HPRolls*h){
 assert(s==sprite&&session==12&&inc==UINT64_MAX&&a==1&&o==2&&before==8&&after==11);
 assert(h->total==12&&h->count==3&&h->samples[2].level==11&&h->samples[2].contribution==5);++selections;return 1;
}
int CBMDL_SelectProficiencies(void*s,uint64_t,uint64_t,const CBMDL_ProfChoice*r,uint32_t n){assert(s==sprite&&n==1&&r[0].stat==89&&r[0].delta==1);++profs;return 1;}
int CBMDL_SelectSkills(void*s,uint64_t,uint64_t,uint32_t xp,uint32_t kit,const CBMDP_SkillChoices*c){
 assert(s==sprite&&xp==550000&&kit==16385&&c->before[0]==10&&c->selected[0]==11&&c->selected[6]==70);++skills;return 1;
}
int main(){
 assert(CBMDS_ConfigureLua((uintptr_t)&get,(uintptr_t)&push));std::ostringstream stream;stream<<std::hex<<(uintptr_t)sprite;
 Lua good{{stream.str(),"12","18446744073709551615","1","2","8","11","9:3;10:4;11:5;","89:1;","550000","16385",
  "0:10;1:20;2:30;3:40;4:50;5:60;6:70;","0:11;1:20;2:30;3:40;4:50;5:60;6:70;"},{}};
 assert(CBMDL_LuaSelect(&good)==1&&good.out==std::vector<std::string>({"1"})&&selections==1&&profs==1&&skills==1);
 for(const auto& bad:std::vector<std::pair<int,std::string>>{{1,"0x12"},{6,"256"},{7,"9:-1;"},{7,"9:2147483648;"},{11,"0:1;0:2;2:3;3:4;4:5;5:6;6:7;"},{12,"0:256;1:2;2:3;3:4;4:5;5:6;6:7;"}}){
  auto v=good;v.args[bad.first]=bad.second;v.out.clear();assert(!CBMDL_LuaSelect(&v)&&v.out.empty()&&selections==1);}
 Lua read{{stream.str(),"89"},{}};assert(CBMDL_LuaReadOld(&read)==1&&read.out[0]=="3");
 read.args[1]="0";read.out.clear();sprite[0x5c2]=222;assert(CBMDL_LuaReadSkill(&read)==1&&read.out[0]=="222");
 read.args[1]="2";read.out.clear();assert(CBMDL_LuaDormant(&read)==1&&read.out[0]=="1");
 int previous=providerCalls;std::thread wrong([&]{assert(!CBMDL_LuaSelect(&good)&&!CBMDL_LuaReadOld(&read)&&!CBMDL_LuaReadSkill(&read)&&!CBMDL_LuaDormant(&read));});wrong.join();assert(previous==providerCalls);
 std::cout<<"Combined Lua parser/thread protocol passed; native helpers explicitly simulated\n";
}
