#define _CRT_SECURE_NO_WARNINGS
#include "dual_old_hla.h"
#include "dual_manual_session.h"
#include <array>
#include <cstring>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <cctype>
#include <vector>
#include <iostream>
#include <sstream>
#include <cstdlib>
namespace {
int checks=0,expected_capped=3,closes=0,catalog_calls=0;bool on_thread=true,throw_close=false;
std::array<unsigned char,0x4000> rules{};
const char* columns[]={"FIRST_LEVEL","RATE","CHANGE_LEVEL","NEW_RATE"};
const char* cells[]={"20","1","40","1"};
std::array<unsigned char,0x40> row{};
std::array<unsigned char,0x20> catalog{};
void* rows[]={row.data()};
template<class T>void put(void* p,size_t off,T v){std::memcpy(static_cast<unsigned char*>(p)+off,&v,sizeof v);}
template<class T>T get(void* p,size_t off){T v;std::memcpy(&v,static_cast<unsigned char*>(p)+off,sizeof v);return v;}
void require(bool ok){++checks;if(!ok)throw std::runtime_error("HLA native adapter assertion "+std::to_string(checks));}
int thread(){return on_thread?1:0;}
void set_level(void* p,uint8_t cls,uint8_t sub,uint8_t level){require(cls==2&&sub==2);put<uint8_t>(p,0x50,level);}
int number(void* r,void* ai,void*,void*,uint8_t* flags){require(r==rules.data());require(get<uint8_t>(ai,0xB)==2&&get<uint32_t>(ai,0xC)==0xFFFFFFFF);*flags=1;return expected_capped;}
void* class_string(void* r,void* out,uint8_t cls,uint32_t kit){require(r==rules.data()&&cls==2&&kit==0x4000);put(out,0,"FIGHTER");return out;}
void destroy_string(void*){}
void* cell(void* r,const void* col,const void* cls){require(r==rules.data()+0x3008);require(std::strcmp(*static_cast<const char* const*>(cls),"FIGHTER")==0);for(int i=0;i<4;++i)if(col==&columns[i])return &cells[i];throw 1;}
void* abilities(void* r,void* actor){++catalog_calls;require(r==rules.data()&&get<uint8_t>(actor,0x4B5B)==2&&get<uint32_t>(actor,0x4B5C)==0xFFFFFFFF);require(get<uint16_t>(actor,0x79C)==0x3456&&get<uint16_t>(actor,0x79E)==0x8000);return catalog.data();}
void complete(void* screen,void* actor){require(!actor&&get<uint8_t>(screen,0xA08)==0&&get<void*>(screen,0x9E8)==catalog.data());++closes;if(throw_close)throw 1;}
struct Lua{std::vector<std::string> args,out;};
const char* to_string(void* p,int index,size_t* length){auto& l=*static_cast<Lua*>(p);if(index<1||static_cast<size_t>(index)>l.args.size())return nullptr;
 const auto& s=l.args[index-1];*length=s.size();return s.c_str();}
void push_string(void* p,const char* s){static_cast<Lua*>(p)->out.emplace_back(s);}
void* construct_row(void* out){std::memset(out,0,0x40);for(size_t off:{size_t(0x10),size_t(0x28),size_t(0x30),size_t(0x38)})put(out,off,"*");return out;}
void* assign_chars(void* out,const char* value){put(out,0,value);return out;}
void* resref(void* out,const void* value){const auto* text=*static_cast<const char* const*>(value);std::memset(out,0,8);for(size_t i=0;i<8&&text[i];++i)static_cast<char*>(out)[i]=static_cast<char>(std::toupper(static_cast<unsigned char>(text[i])));return out;}
void* ai_type(void* actor){return static_cast<unsigned char*>(actor)+0x30;}
int expected_rank=0,expected_representatives=0,expected_markers=0;
int check_enabled(void* screen,void* actor,void* candidate){
    require(get<uint8_t>(screen,0x9E0)==1&&get<int32_t>(candidate,0x20)==expected_rank);
    require(get<uint8_t>(screen,0xA08)==expected_representatives);
    int count=0;auto* node=get<void*>(actor,0x4A08);
    while(node){auto* effect=get<void*>(node,0x10);require(get<uint32_t>(effect,0x10)==313);++count;node=get<void*>(node,0);}
    require(count==expected_markers);return 1;
}
CBMDS_View manual{};bool dormant=false,throw_delivery=false;int delivery_calls=0;std::vector<uint32_t> delivered;
int query(const void* actor,CBMDS_View* out){if(reinterpret_cast<uintptr_t>(actor)!=manual.sprite)return 0;*out=manual;return 1;}
int is_dormant(const void*,uint8_t old){require(old==2);return dormant?1:0;}
void* allocate(size_t bytes){return std::calloc(1,bytes);}
void* array_construct(void* p){std::memset(p,0,0x20);return p;}
void grow(void* p,int index,void* value){
 auto* array=get<void**>(p,8);array=static_cast<void**>(std::realloc(array,(static_cast<size_t>(index)+1)*8));require(array!=nullptr);
 array[index]=value;put(p,8,array);put<int32_t>(p,0x10,index+1);
}
void release(void* p,size_t){std::free(p);}
void delivery_complete(void* screen,void* actor){
 auto* list=get<void*>(screen,0x9E8);auto* array=get<void**>(list,8);auto count=get<int32_t>(list,0x10);
 if(actor){++delivery_calls;const auto selected=get<uint8_t>(screen,0xA08);require(selected<=24&&selected==count);
  for(uint8_t i=0;i<selected;++i){require(get<uint8_t>(screen,0x9F0+i)==i);delivered.push_back(get<uint32_t>(array[i],8));
   if(throw_delivery)throw 1;
  }
 }
 for(int i=0;i<count;++i)std::free(array[i]);std::free(array);std::free(list);put<void*>(screen,0x9E8,nullptr);
}
}
int main(){
    put(catalog.data(),8,rows);put<int32_t>(catalog.data(),0x10,1);
    std::memcpy(row.data(),"ICONTEST",8);put<uint32_t>(row.data(),8,12345);put(row.data(),0x10,"GA_CBMTST");
    put<int32_t>(row.data(),0x18,1);put<int32_t>(row.data(),0x1C,99);put<int32_t>(row.data(),0x20,5);
    put(row.data(),0x28,"*");put(row.data(),0x30,"AP_OTHER");put(row.data(),0x38,"*");
    CBMDHLA_Config c{1,reinterpret_cast<uintptr_t>(rules.data()),reinterpret_cast<uintptr_t>(&thread),
        reinterpret_cast<uintptr_t>(&number),reinterpret_cast<uintptr_t>(&set_level),reinterpret_cast<uintptr_t>(&class_string),
        reinterpret_cast<uintptr_t>(&cell),reinterpret_cast<uintptr_t>(&std::sscanf),reinterpret_cast<uintptr_t>(&destroy_string),
        reinterpret_cast<uintptr_t>(&columns[0]),reinterpret_cast<uintptr_t>(&columns[1]),reinterpret_cast<uintptr_t>(&columns[2]),reinterpret_cast<uintptr_t>(&columns[3]),
        reinterpret_cast<uintptr_t>(&abilities),reinterpret_cast<uintptr_t>(&complete),
        reinterpret_cast<uintptr_t>(&construct_row),reinterpret_cast<uintptr_t>(&assign_chars),reinterpret_cast<uintptr_t>(&assign_chars),
        reinterpret_cast<uintptr_t>(&resref),reinterpret_cast<uintptr_t>(&check_enabled),reinterpret_cast<uintptr_t>(&ai_type)};
    require(CBMDHLA_Configure(&c)==1);require(CBMDHLA_Configure(&c)==0);
    std::array<unsigned char,0x5000> actor{};actor[0x4B5B]=7;put<uint32_t>(actor.data(),0x4B5C,42);
    auto unchanged=actor;CBMDHLA_View view{};
    require(CBMDHLA_Open(actor.data(),2,0x34568000,18,22,&view)==1);
    require(view.points==3&&view.native_capped_points==3&&view.row_count==1&&view.eligibility_flags==1);
    require(actor==unchanged);CBMDHLA_Row descriptor{};
    require(CBMDHLA_ReadRow(view.handle,0,&descriptor)==1);
    require(descriptor.name_strref==12345&&std::strcmp(descriptor.effect,"GA_CBMTST")==0&&descriptor.max_rank==5);
    require(std::strcmp(descriptor.excluded_by,"AP_OTHER")==0&&std::strcmp(descriptor.icon,"ICONTEST")==0);
    expected_rank=5;expected_representatives=0;expected_markers=0;
    require(CBMDHLA_CanChoose(view.handle,actor.data(),0,nullptr,0,nullptr,0)==1);
    uint32_t prefix[]={0,0,0,0,0};expected_rank=1;
    require(CBMDHLA_CanChoose(view.handle,actor.data(),0,prefix,4,nullptr,0)==1);
    require(CBMDHLA_CanChoose(view.handle,actor.data(),0,prefix,5,nullptr,0)==0);
    expected_markers=1;require(CBMDHLA_CanChoose(view.handle,actor.data(),0,prefix,4,&descriptor,1)==1);
    put<int32_t>(row.data(),0x20,200);put(row.data(),0x28,"GA_CBMTST");
    std::vector<uint32_t> long_prefix(100,0);expected_rank=101;expected_representatives=1;expected_markers=0;
    require(CBMDHLA_CanChoose(view.handle,actor.data(),0,long_prefix.data(),100,nullptr,0)==1);
    require(get<int32_t>(row.data(),0x20)==200&&actor==unchanged); // no catalog/actor mutation
    put<int32_t>(row.data(),0x20,5);put(row.data(),0x28,"*");
    require(CBMDHLA_Close(view.handle)==1&&closes==1);require(CBMDHLA_Close(view.handle)==0);
    expected_capped=24;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,0,70,&view)==1);
    require(view.points==51&&view.native_capped_points==24);require(CBMDHLA_Close(view.handle)==1);
    cells[0]="5";cells[1]="0.5";cells[2]="8";cells[3]="1.5";expected_capped=6;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,4,10,&view)==1&&view.points==6);require(CBMDHLA_Close(view.handle)==1);
    expected_capped=1;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,4,6,&view)==1&&view.points==1);require(CBMDHLA_Close(view.handle)==1);
    expected_capped=0;int before_catalog=catalog_calls,before_close=closes;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,0,1,&view)==1&&view.points==0&&view.row_count==0);
    require(catalog_calls==before_catalog&&CBMDHLA_Close(view.handle)==1&&closes==before_close);
    expected_capped=1;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,4,6,&view)==1);throw_close=true;
    require(CBMDHLA_Close(view.handle)==-1&&CBMDHLA_LastStatus()==4);before_close=closes;
    require(CBMDHLA_Close(view.handle)==0&&closes==before_close);throw_close=false;
    CBMDHLA_LuaConfig lc{1,reinterpret_cast<uintptr_t>(&to_string),reinterpret_cast<uintptr_t>(&push_string)};
    require(CBMDHLA_ConfigureLua(&lc)==1&&CBMDHLA_ConfigureLua(&lc)==0);
    std::ostringstream address;address<<std::hex<<reinterpret_cast<uintptr_t>(actor.data());
    Lua open{{address.str(),"2","878084096","4","6"},{}}; //0x34568000
    require(CBMDHLA_LuaOpen(&open)==6&&open.out[0]=="1"&&open.out[2]=="1"&&open.out[4]=="1");
    Lua row_query{{open.out[1],"0"},{}};
    require(CBMDHLA_LuaRow(&row_query)==10&&row_query.out[6]=="GA_CBMTST"&&row_query.out[2]=="12345");
    expected_rank=4;expected_representatives=0;expected_markers=1;
    Lua chosen{{open.out[1],address.str(),"0","1:0","9:GA_CBMTST"},{}};
    require(CBMDHLA_LuaChoose(&chosen)==1&&chosen.out==std::vector<std::string>{"1"});
    chosen.args[3]="99:0";chosen.out.clear();require(CBMDHLA_LuaChoose(&chosen)==0&&chosen.out.empty());
    chosen.args[3]="2:-1";require(CBMDHLA_LuaChoose(&chosen)==0);
    Lua shut{{open.out[1]},{}};require(CBMDHLA_LuaClose(&shut)==1&&shut.out[0]=="1");
    alignas(8)std::array<unsigned char,0xA10> manual_screen{};manual_screen[0x9E0]=1;
    manual.session=17;manual.incarnation=99;manual.phase=CBMDS_PREPARING;
    manual.screen=reinterpret_cast<uintptr_t>(manual_screen.data());manual.sprite=reinterpret_cast<uintptr_t>(actor.data());
    std::memcpy(manual.owner,"1234567890abcdef1234567890abcdef",33);
    CBMDHLA_ProjectionConfig pc{1,reinterpret_cast<uintptr_t>(&query)};require(CBMDHLA_ConfigureProjection(&pc)==1);
    uint64_t context=0;require(CBMDHLA_PrepareManual(actor.data(),manual.owner,&descriptor,1,&context)==1);
    manual.phase=CBMDS_PREVIEW;expected_markers=1;expected_rank=5;
    require(CBMDHLA_CheckAbilityEnabled(manual_screen.data(),actor.data(),row.data())==1&&actor==unchanged);
    manual.phase=CBMDS_COMMITTING;expected_markers=0;
    require(CBMDHLA_CheckAbilityEnabled(manual_screen.data(),actor.data(),row.data())==1);
    require(CBMDHLA_ClearManual(context)==1&&CBMDHLA_ClearManual(context)==1);
    manual.phase=CBMDS_PREVIEW;bool stale=false;try{CBMDHLA_CheckAbilityEnabled(manual_screen.data(),actor.data(),row.data());}catch(...){stale=true;}require(stale);
    manual.owner[0]=0;require(CBMDHLA_CheckAbilityEnabled(manual_screen.data(),actor.data(),row.data())==1);
    manual.owner[0]='1';
    CBMDHLA_DeliveryConfig dc{1,reinterpret_cast<uintptr_t>(&query),reinterpret_cast<uintptr_t>(&thread),reinterpret_cast<uintptr_t>(&is_dormant),
      reinterpret_cast<uintptr_t>(&allocate),reinterpret_cast<uintptr_t>(&array_construct),reinterpret_cast<uintptr_t>(&grow),1,
      reinterpret_cast<uintptr_t>(&construct_row),reinterpret_cast<uintptr_t>(&assign_chars),reinterpret_cast<uintptr_t>(&destroy_string),
      reinterpret_cast<uintptr_t>(&release),reinterpret_cast<uintptr_t>(&delivery_complete)};
    require(CBMDHLA_ConfigureDelivery(&dc)==1);std::vector<CBMDHLA_Row> rewards(51,descriptor);
    for(size_t i=0;i<rewards.size();++i)rewards[i].name_strref=static_cast<uint32_t>(i);
    CBMDHLA_DeliveryResult receipt{};
    require(CBMDHLA_Deliver(actor.data(),2,manual.owner,rewards.data(),51,&receipt)==0&&delivered.empty());
    manual.phase=CBMDS_COMMITTING;dormant=true;
    require(CBMDHLA_Deliver(actor.data(),2,manual.owner,rewards.data(),51,&receipt)==0&&delivered.empty());dormant=false;
    require(CBMDHLA_Deliver(actor.data(),2,manual.owner,rewards.data(),51,&receipt)==1&&receipt.completed==51&&receipt.uncertain==0);
    require(delivery_calls==3&&delivered.size()==51);for(size_t i=0;i<delivered.size();++i)require(delivered[i]==i);
    require(CBMDHLA_Deliver(actor.data(),2,manual.owner,rewards.data(),51,&receipt)==0&&delivery_calls==3);
    ++manual.session;throw_delivery=true;
    require(CBMDHLA_Deliver(actor.data(),2,manual.owner,rewards.data(),51,&receipt)==-1&&receipt.completed==0&&receipt.uncertain==1);
    require(CBMDHLA_Deliver(actor.data(),2,manual.owner,rewards.data(),51,&receipt)==0&&delivery_calls==4);throw_delivery=false;
    cells[1]="not-a-rate";view.handle=123;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,4,6,&view)==0&&view.handle==123&&actor==unchanged);
    on_thread=false;require(CBMDHLA_Open(actor.data(),2,0x34568000,4,6,&view)==0);on_thread=true;
    require(CBMDHLA_Open(actor.data(),2,0x34568000,7,6,&view)==0);
    std::cout<<checks<<" HLA native-provider synthetic assertions passed.\n";
}
