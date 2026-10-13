// Lua ABI/argument protocol only. Native resolver is simulated in THIS test;
// dual_proficiency_probe.py executes its actual instructions separately.
#include "dual_native_proficiency.h"
#include <cassert>
#include <charconv>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
struct CBMDP_LuaConfig{uint32_t abi;uintptr_t image;size_t size;uintptr_t to_string,push_string;};
extern "C" int CBMDP_ConfigureLua(const CBMDP_LuaConfig*);
extern "C" int CBMDP_LuaOldTarget(void*);
extern "C" int CBMDP_LuaOldPlan(void*);
extern "C" int CBMDP_LuaOldCap(void*);
extern "C" int CBMDP_LuaOldRoll(void*);
namespace{
 const auto mainThread=std::this_thread::get_id();int calls=0,queries=0,status=0;
 struct Lua{std::vector<std::string> args,out;};
 const char* tostring(void*p,int i,size_t*n){++calls;auto&l=*static_cast<Lua*>(p);
  if(i<1||size_t(i)>l.args.size())return nullptr;auto&s=l.args[i-1];*n=s.size();return s.c_str();}
 void pushstring(void*p,const char*s){++calls;static_cast<Lua*>(p)->out.emplace_back(s);}
}
int CBMDP_Bind(const void*,size_t,CBMDP_Binding**o){*o=reinterpret_cast<CBMDP_Binding*>(1);return 0;}
int CBMDP_IsEngineThread(){return std::this_thread::get_id()==mainThread;}
int CBMDP_GetOldTarget(CBMDP_Binding*,void*r,const void*t,const void*b,uint8_t a,uint8_t o,uint32_t xp,CBMDP_OldTarget*out){
 ++queries;assert(r==reinterpret_cast<void*>(0x20000)&&t==reinterpret_cast<void*>(0x14b68)&&b==reinterpret_cast<void*>(0x11120));
 assert(a==4&&o==2&&xp==550000);*out={xp,10,11,a,o};return status;
}
int CBMDP_GetOldPlan(CBMDP_Binding*b,void*r,const void*t,const void*s,uint8_t a,uint8_t o,uint32_t xp,uint32_t kit,CBMDP_OldPlan*out){
 assert(kit==0x4001);int n=CBMDP_GetOldTarget(b,r,t,s,a,o,xp,&out->levels);out->prof_points=1;out->skill_points=75;return n;}
int CBMDP_GetOldCap(CBMDP_Binding*b,void*r,const void*t,const void*s,uint8_t a,uint8_t o,uint32_t xp,uint32_t kit,uint32_t stat,CBMDP_ChoiceCap*out){
 assert(kit==0x4001&&stat==89);CBMDP_OldTarget levels{};int n=CBMDP_GetOldTarget(b,r,t,s,a,o,xp,&levels);*out={5,4,4};return n;}
int CBMDP_RollOldPlan(CBMDP_Binding*,void*r,const void*t,const void*b,uint8_t a,uint8_t o,uint32_t xp,uint32_t kit,uint8_t constitution,CBMDP_HPRolls*out){
 ++queries;assert(r==reinterpret_cast<void*>(0x20000)&&static_cast<const unsigned char*>(t)-0x4b68==static_cast<const unsigned char*>(b)-0x1120);
 assert(a==4&&o==2&&xp==550000&&kit==16385&&constitution==25);out->count=2;out->total=7;
 out->samples[0]={11,3};out->samples[1]={12,4};return status;
}
int CBMDP_ApplyOldPlanSkills(CBMDP_Binding*,void*,void*,uint8_t,uint8_t,uint32_t,uint32_t,const CBMDP_SkillChoices*,uint32_t*){assert(false);return 0;}
int main(){
 CBMDP_LuaConfig c{1,1,1,(uintptr_t)&tostring,(uintptr_t)&pushstring};
 assert(CBMDP_ConfigureLua(&c)&&!CBMDP_ConfigureLua(&c));
 Lua good{{"10000","20000","4","2","550000"},{}};
 assert(CBMDP_LuaOldTarget(&good)==3&&good.out==std::vector<std::string>({"0","10","11"}));
 status=6;good.out.clear();assert(CBMDP_LuaOldTarget(&good)==1&&good.out==std::vector<std::string>({"6"}));status=0;
 for(auto bad:std::vector<std::string>{"-1","4294967296","550000x","","1.5"}){
  Lua l=good;l.args[4]=bad;l.out.clear();int n=queries;assert(!CBMDP_LuaOldTarget(&l)&&l.out.empty()&&queries==n);
 }
 good.args.push_back("16385");good.out.clear();assert(CBMDP_LuaOldPlan(&good)==5&&good.out==std::vector<std::string>({"0","10","11","1","75"}));
 good.args.push_back("89");good.out.clear();assert(CBMDP_LuaOldCap(&good)==2&&good.out==std::vector<std::string>({"0","4"}));
 std::vector<unsigned char> actor(0x5000);actor[0x795]=25;
 char address[24]{};*std::to_chars(address,address+23,reinterpret_cast<uintptr_t>(actor.data()),16).ptr=0;
 Lua roll{{address,"20000","4","2","550000","16385"},{}};
 assert(CBMDP_LuaOldRoll(&roll)==3&&roll.out==std::vector<std::string>({"0","7","11:3;12:4;"}));
 status=6;roll.out.clear();assert(CBMDP_LuaOldRoll(&roll)==1&&roll.out==std::vector<std::string>({"6"}));status=0;
 auto saved=calls;std::thread wrong([&]{assert(!CBMDP_LuaOldTarget(&good)&&!CBMDP_LuaOldPlan(&good)&&!CBMDP_LuaOldCap(&good)&&!CBMDP_LuaOldRoll(&good));});wrong.join();assert(calls==saved);
 std::cout<<"Native Lua target bridge protocol checks passed, including no off-thread provider calls\n";
}
