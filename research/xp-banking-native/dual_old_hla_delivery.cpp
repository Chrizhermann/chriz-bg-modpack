// Research-only delivery through the real native helper, never during preview.
#include "dual_old_hla.h"
#include "dual_manual_session.h"
#include <array>
#include <cstring>
#include <vector>
#include <unordered_map>
namespace {
CBMDHLA_DeliveryConfig config{};bool configured=false;
using Query=int(*)(const void*,CBMDS_View*);using Thread=int(*)();using Dormant=int(*)(const void*,uint8_t);
using Allocate=void*(*)(size_t);using Construct=void*(*)(void*);using Grow=void(*)(void*,int,void*);
using Assign=void*(*)(void*,const char*);using Destroy=void(*)(void*);using Release=void(*)(void*,size_t);
using Complete=void(*)(void*,void*);
template<class T>void put(void* p,size_t offset,T value){std::memcpy(static_cast<unsigned char*>(p)+offset,&value,sizeof value);}
struct Attempt{uint64_t session,incarnation;};
std::unordered_map<uintptr_t,Attempt> attempted;
bool scope(const void* actor,const char* owner,CBMDS_View& view){
 if(!configured||!reinterpret_cast<Thread>(config.is_engine_thread)()||!actor||!owner||std::strlen(owner)!=32)return false;
 if(!reinterpret_cast<Query>(config.session_query)(actor,&view)||view.phase!=CBMDS_COMMITTING
    ||view.sprite!=reinterpret_cast<uintptr_t>(actor)||std::memcmp(owner,view.owner,33))return false;
 return true;
}
void close(void* list){
 if(!list)return;alignas(8)std::array<unsigned char,0xA10> screen{};put(screen.data(),0x9E8,list);
 reinterpret_cast<Complete>(config.complete_abilities)(screen.data(),nullptr);
}
void free_row(void* row){
 for(size_t off:{size_t(0x10),size_t(0x28),size_t(0x30),size_t(0x38)})reinterpret_cast<Destroy>(config.cstring_destroy)(static_cast<unsigned char*>(row)+off);
 reinterpret_cast<Release>(config.release)(row,0x40);
}
void* row(const CBMDHLA_Row& d){
 void* r=reinterpret_cast<Allocate>(config.allocate)(0x40);if(!r)throw 1;
 reinterpret_cast<Construct>(config.ability_construct)(r);
 try {
  std::memcpy(r,d.icon,8);put(r,8,d.name_strref);put(r,0x18,d.min_level);put(r,0x1C,d.max_level);put(r,0x20,d.max_rank);
  const char* values[]={d.effect,d.prerequisite,d.excluded_by,d.alignment};size_t offsets[]={0x10,0x28,0x30,0x38};
  for(size_t i=0;i<4;++i)reinterpret_cast<Assign>(config.cstring_assign_chars)(static_cast<unsigned char*>(r)+offsets[i],values[i]);
  return r;
 }catch(...){free_row(r);throw;}
}
}
CBMDHLA_API int CBMDHLA_ConfigureDelivery(const CBMDHLA_DeliveryConfig* c){
 if(configured||!c||c->abi!=1||!c->session_query||!c->is_engine_thread||!c->is_dormant||!c->allocate
  ||!c->array_construct||!c->array_grow||!c->list_vtable||!c->ability_construct||!c->cstring_assign_chars
  ||!c->cstring_destroy||!c->release||!c->complete_abilities)return 0;
 config=*c;configured=true;return 1;
}
CBMDHLA_API int CBMDHLA_Deliver(void* actor,uint8_t old,const char* owner,const CBMDHLA_Row* rows,
 uint32_t count,CBMDHLA_DeliveryResult* result){
 CBMDS_View begin{};if(!result||!scope(actor,owner,begin)||(count&&!rows))return 0;*result={0,0};
 if(reinterpret_cast<Dormant>(config.is_dormant)(actor,old)!=0)return 0;
 const auto key=reinterpret_cast<uintptr_t>(actor);const auto previous=attempted.find(key);
 if(previous!=attempted.end()&&previous->second.session==begin.session&&previous->second.incarnation==begin.incarnation)return 0;
 for(uint32_t i=0;i<count;++i){const auto& d=rows[i];
  if(!d.effect||!d.prerequisite||!d.excluded_by||!d.alignment||std::strlen(d.effect)<=3
    ||(std::strncmp(d.effect,"GA",2)&&std::strncmp(d.effect,"AP",2)))return 0;
 }
 if(!count)return 1;
 std::vector<void*> lists;
 try {
  // Complete owns/frees its input list. Allocate every batch first so ordinary
  // allocation failure never leaves half of this receipt granted to the actor.
  for(uint32_t offset=0;offset<count;){
   void* list=reinterpret_cast<Allocate>(config.allocate)(0x20);if(!list)throw 1;
   reinterpret_cast<Construct>(config.array_construct)(list);put(list,0,config.list_vtable);lists.push_back(list);
   uint32_t size=count-offset<24?count-offset:24;
   for(uint32_t i=0;i<size;++i){void* r=row(rows[offset+i]);
    try{reinterpret_cast<Grow>(config.array_grow)(list,static_cast<int>(i),r);}
    catch(...){
     // SetAtGrow may have resized its array before throwing. Retain this native
     // allocation rather than risk freeing a possibly attached pointer twice.
     throw;
    }
   }offset+=size;
  }
 }catch(...){for(auto* list:lists)try{close(list);}catch(...){/* uncertain heap cleanup, no actor touched */}return 0;}
 attempted[key]={begin.session,begin.incarnation};
 for(size_t batch=0;batch<lists.size();++batch){
  alignas(8)std::array<unsigned char,0xA10> screen{};put(screen.data(),0x9E8,lists[batch]);
  const auto remaining=count-result->completed;const uint8_t size=static_cast<uint8_t>(remaining<24?remaining:24);
  screen[0xA08]=size;for(uint8_t i=0;i<size;++i)screen[0x9F0+i]=i;
  try {
   reinterpret_cast<Complete>(config.complete_abilities)(screen.data(),actor);
   lists[batch]=nullptr;result->completed+=size;
   CBMDS_View now{};
   if(!scope(actor,owner,now)||now.session!=begin.session||now.incarnation!=begin.incarnation
     ||reinterpret_cast<Dormant>(config.is_dormant)(actor,old)!=0)throw 1;
  }catch(...){
   result->uncertain=1;
   // Failed batch may already have fired some abilities and freed some input.
   // Quarantine it. Only future untouched batches may be safely cleaned up.
   for(size_t later=batch+1;later<lists.size();++later)try{close(lists[later]);}catch(...){}
   return -1;
  }
 }
 return 1;
}
