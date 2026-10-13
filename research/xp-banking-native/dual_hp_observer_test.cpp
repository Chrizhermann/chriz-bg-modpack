// Protocol tests with a simulated original. Actual thunk instructions are tested
// separately in dual_hp_probe.py; this file makes no native reward claims.
#include "dual_hp_observer.h"
#include <cassert>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <iostream>
namespace {
int mode=0,calls=0;
int32_t original(void* rules,void* type,void*,void*,unsigned char constitution) {
    ++calls;assert(rules==reinterpret_cast<void*>(11));assert(type==reinterpret_cast<void*>(12));assert(constitution==19);
    if(mode==1)throw std::runtime_error("native failure");
    CBMDH_Record(11,7);CBMDH_Record(12,5);
    if(mode==2)CBMDH_Record(12,9);
    return mode==3 ? 13 : 12;
}
}
int main() {
    CBMDH_Config c{1,reinterpret_cast<uintptr_t>(&original)};
    assert(CBMDH_Configure(&c));assert(!CBMDH_Configure(&c));
    unsigned char before[128]{},after[128]{};
    uint16_t levels[3]{10,10,0};std::memcpy(before+0x46,levels,6);
    levels[1]=12;std::memcpy(after+0x46,levels,6);
    CBMDH_Batch out{};
    auto capture=[&] {return CBMDH_Capture(reinterpret_cast<void*>(11),reinterpret_cast<void*>(12),before,after,19,reinterpret_cast<void*>(123));};
    CBMDH_Record(4,99);assert(!CBMDH_Peek(&out));
    assert(capture()==12);assert(calls==1);assert(CBMDH_Peek(&out));
    assert(out.status==1 && out.count==2 && out.native_total==12 && out.actor==123);
    assert(out.before_levels[1]==10 && out.after_levels[1]==12);
    assert(out.samples[0].level==11 && out.samples[0].rolled_hp==7);
    assert(out.samples[1].level==12 && out.samples[1].rolled_hp==5);
    const auto first=out.serial;
    std::thread wrong([&]{CBMDH_Batch blocked{};assert(!CBMDH_Configure(&c));assert(!CBMDH_Peek(&blocked));assert(!CBMDH_Acknowledge(first));CBMDH_Record(1,99);});wrong.join();
    assert(CBMDH_Peek(&out)&&out.count==2&&out.status==1);
    assert(!CBMDH_Acknowledge(first+1));assert(CBMDH_Acknowledge(first));assert(!CBMDH_Peek(&out));
    mode=2;assert(capture()==12);assert(CBMDH_Peek(&out)&&out.status==2);assert(CBMDH_Acknowledge(out.serial));
    mode=3;assert(capture()==13);assert(CBMDH_Peek(&out)&&out.status==2);assert(CBMDH_Acknowledge(out.serial));
    mode=0;assert(capture()==12);assert(CBMDH_Peek(&out));const auto held=out.serial;
    assert(capture()==12);assert(CBMDH_Peek(&out)&&out.serial==held&&out.status==2);assert(CBMDH_Acknowledge(held));
    mode=1;bool threw=false;try{capture();}catch(const std::runtime_error&){threw=true;}assert(threw);
    assert(CBMDH_Peek(&out)&&out.status==2&&out.count==0);assert(CBMDH_Acknowledge(out.serial));
    assert(calls==6);std::cout<<"HP capture observer protocol checks passed (simulated original)\n";
}
