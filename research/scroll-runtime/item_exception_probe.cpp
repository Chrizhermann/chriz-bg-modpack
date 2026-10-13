// Our own compiled C++ callees only. Never invokes a game/EEex function.
#include "item_carrier_api.h"
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <vector>
namespace {
std::array<unsigned char,0x18> item{};
std::array<unsigned char,0x110> effect{};
bool root_throws{};
int resolve(uintptr_t,uint64_t,uintptr_t,uint32_t,CBMS_Stats* out,void*) {
    *out={};out->count=1;out->active[0]=1;out->level[0]=20;return 1;
}
void* root(void*,int,int,void*) {
    if(root_throws)throw std::runtime_error("original root failed before returning an effect");
    return effect.data();
}
uint16_t use(void* reader,void*) {
    if(CBMS_ItemCarriersIdle()!=0||CBMS_DetachItemCarriers()!=0)throw std::logic_error("active item carrier incorrectly removable");
    CBMS_TestItemEffectCarrier(100,item.data(),2,0,reader);
    throw std::runtime_error("original use failed after producing a root");
}
uint16_t point(void*){return 1;}
uint16_t fire(void*,void*,int,void*){return 1;}
uint16_t type(void*){return 11;}
int digest(const char*,const char*,unsigned char* out,void*){std::memset(out,0,32);return 1;}
void require(bool condition,const char* message){if(!condition)throw std::logic_error(message);}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"mode missing");root_throws=std::string_view(argv[1])=="root";
        std::memcpy(item.data()+0x10,"SCROLL12",8);
        std::vector<unsigned char> table(16+16+44);
        std::memcpy(table.data(),"CBMSPOL1",8);table[8]=1;table[12]=1;
        std::memcpy(table.data()+16,"SCROLL12",8);table[24]=2;
        std::memcpy(table.data()+32,"SCROLL12ITM",11);
        auto* runtime=CBMS_Create(resolve,nullptr,nullptr);require(runtime!=nullptr,"create failed");
        const CBMS_ItemFunctions functions{use,point,fire,fire,root,type,{100,101,102,103},{200,201}};
        require(CBMS_ConfigureItemCarriers(runtime,&functions,table.data(),static_cast<uint32_t>(table.size()),digest,nullptr)==1,"configuration failed");
        bool caught{};
        try {CBMS_UseItemCarrier(reinterpret_cast<void*>(0x1000),reinterpret_cast<void*>(0x2000));}
        catch(const std::runtime_error& error) {caught=std::string_view(error.what()).starts_with("original ");}
        require(caught,"original exception lost");require(CBMS_ItemCarriersIdle()==1,"scope remained busy after unwind");
        require(!*CBMS_ItemCarrierError(),"original exception incorrectly became policy fault");
        require(CBMS_DestructObserved(runtime,1,reinterpret_cast<uintptr_t>(effect.data()))==1,"effect cleanup failed");
        require(CBMS_Quiescent(runtime)==1,"unwind stranded an item use token");
        require(CBMS_DetachItemCarriers()==1,"detach failed");require(CBMS_Destroy(runtime)==1,"destroy failed");
        std::cout<<"PASS original "<<(root_throws?"root":"use")<<" exception cleanup\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
