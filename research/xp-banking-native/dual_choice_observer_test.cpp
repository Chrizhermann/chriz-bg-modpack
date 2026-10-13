// Protocol-only simulated setters; game instruction callsites checked separately.
#include "dual_choice_observer.h"
#include <cassert>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <iostream>
namespace {
int active=1,inactive=5,calls=0;bool fail=false;
void setA(void* s,uint32_t stat,int32_t p,int immediate){assert(s==reinterpret_cast<void*>(123)&&stat==101&&immediate==1);++calls;if(fail)throw std::runtime_error("native");active=p;}
void setI(void* s,uint32_t stat,int32_t p,int immediate){assert(s==reinterpret_cast<void*>(123)&&stat==101&&immediate==1);++calls;inactive=p;}
int32_t getA(void*,uint32_t){return active;}int32_t getI(void*,uint32_t){return inactive;}
}
int main(){
 CBMDC_Config c{1,reinterpret_cast<uintptr_t>(&setA),reinterpret_cast<uintptr_t>(&setI),reinterpret_cast<uintptr_t>(&getA),reinterpret_cast<uintptr_t>(&getI)};
 assert(CBMDC_Configure(&c));assert(!CBMDC_Configure(&c));
 unsigned char screen[0xa10]{};uint32_t mode=25;std::memcpy(screen+0x768,&mode,4);screen[0xa0c]=2;
 CBMDC_Active(reinterpret_cast<void*>(123),101,2,1,screen);CBMDC_Active(reinterpret_cast<void*>(123),101,1,1,screen);
 CBMDC_Inactive(reinterpret_cast<void*>(123),101,6,1,screen);
 CBMDC_Event e{};assert(CBMDC_Peek(&e)&&e.before==1&&e.after==2&&e.status==1&&!e.inactive&&e.screen_mode==25&&e.screen_selected_class==2);
 const auto first=e.sequence;assert(!CBMDC_Acknowledge(first+1));
 std::thread other([&]{CBMDC_Event x{};assert(!CBMDC_Peek(&x));assert(!CBMDC_Acknowledge(first));assert(CBMDC_Faulted());});other.join();
 assert(CBMDC_Acknowledge(first));assert(CBMDC_Peek(&e)&&e.before==2&&e.after==1&&!e.inactive);assert(CBMDC_Acknowledge(e.sequence));
 assert(CBMDC_Peek(&e)&&e.before==5&&e.after==6&&e.inactive);assert(CBMDC_Acknowledge(e.sequence));
 assert(!CBMDC_Faulted()&&calls==3&&!CBMDC_Peek(&e));
 fail=true;bool threw=false;try{CBMDC_Active(reinterpret_cast<void*>(123),101,2,1,screen);}catch(const std::runtime_error&){threw=true;}
 assert(threw&&CBMDC_Faulted()&&calls==4&&CBMDC_Peek(&e)&&e.status==2&&e.before==1);
 std::cout<<"Manual choice observer protocol checks passed (simulated setters)\n";
}
