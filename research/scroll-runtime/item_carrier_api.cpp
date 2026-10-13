#include "item_carrier_api.h"
#include "policy_table.hpp"
#include "item_binding.hpp"
#include <array>
#include <cstring>
#include <memory>
#include <thread>
#include <vector>
#include <intrin.h>
namespace {
CBMS_Runtime* runtime{};
CBMS_ItemFunctions native{};
std::unique_ptr<cbm::scroll::PolicyTable> policy;
std::thread::id owner;
std::array<char,256> fault{};
unsigned busy{};
int (*admission)(void){};
void fail(const char* message) noexcept {
    if(fault[0]) return;
    if(!message) message="unknown native item carrier failure";
    const auto n=(std::min)(std::strlen(message),fault.size()-1);
    std::memcpy(fault.data(),message,n);fault[n]=0;
}
bool check(int result) noexcept {if(result==1)return true;fail(CBMS_LastError(runtime));return false;}
template<class F> void safely(F&& body) noexcept {
    if(fault[0]) return;
    try {body();} catch(const std::exception& error) {fail(error.what());}
    catch(...) {fail("unexpected item ownership failure");}
}
struct RootUse {void* item;int ability;uint64_t token;};
struct UseState {
    std::vector<RootUse> roots;
    void close() noexcept {for(auto& root:roots) if(root.token) {check(CBMS_ItemEnd(runtime,root.token));root.token=0;}}
    ~UseState() {close();}
};
struct Invocation;
Invocation* current{};
struct Invocation {
    unsigned kind;void* reader;void* item;int ability;Invocation* parent;
    UseState owned;UseState* state;
    Invocation(unsigned k,void* r,void* i=nullptr,int a=0,uintptr_t caller=0)
        :kind(k),reader(r),item(i),ability(a),parent(current),state(&owned) {
        if(!runtime || owner!=std::this_thread::get_id())
            throw std::logic_error("native item carrier called without owner-thread configuration");
        // A real native extra-target loop, not arbitrary nested/reentrant use.
        if(k>=2 && parent && parent->kind==k-2 && parent->reader==r &&
           caller==native.continuation_returns[k-2]) state=parent->state;
        ++busy;current=this;
        if(k<2) safely([&] {check(CBMS_ActorObserved(runtime,reinterpret_cast<uintptr_t>(r),0));});
    }
    ~Invocation() {owned.close();current=parent;--busy;}
};
void attach_root(uintptr_t caller,void* item,int ability,int index,void* reader,void* effect) noexcept {
    if((admission&&!admission()) || !effect || !current || current->reader!=reader ||
       caller!=native.root_returns[current->kind]) return;
    safely([&] {
        if(!item || ability<0 || index<0) throw std::logic_error("invalid native item root identity");
        if(current->kind>=2 && (current->item!=item || current->ability!=ability))
            throw std::logic_error("native FireItem root disagrees with its item/ability arguments");
        // Native CItem::GetAbilityEffect has completed its own resource demand.
        // Query the same engine item category; no resource-prefix heuristics.
        if(native.item_type(item)!=11) return;
        std::array<std::uint8_t,8> name{};
        std::memcpy(name.data(),static_cast<unsigned char*>(item)+0x10,8);
        const auto classification=policy->lookup(name,static_cast<unsigned>(ability));
        if(!classification) throw std::logic_error("used scroll ability is absent from verified installed policy inventory");
        // Explicit reviewed inventory rows (e.g. cyclic helper graphs) remain
        // native, with their precise installer diagnostics. An absent key is
        // still a runtime fault: it was never part of that inventory decision.
        if(classification->policy!=cbm::scroll::ItemPolicy::OrdinaryScroll) return;
        // Direct FireItem accepts generic AI objects. Only previously observed
        // sprites may reach the sprite reader provider; never cast the target.
        if(CBMS_ActorIsObserved(runtime,reinterpret_cast<uintptr_t>(reader))!=1)
            throw std::logic_error("scroll's original FireItem reader has no observed sprite lifetime");
        auto& roots=current->state->roots;
        auto found=std::find_if(roots.begin(),roots.end(),[&](const auto& value){return value.item==item && value.ability==ability;});
        if(found==roots.end()) {
            // Reserve before creating a core token, so a vector allocation
            // failure cannot strand a completed ItemBegin.
            roots.push_back({item,ability,0});found=roots.end()-1;
            if(!check(CBMS_ItemBegin(runtime,reinterpret_cast<uintptr_t>(reader),
                reinterpret_cast<const char*>(name.data()),static_cast<unsigned>(ability),0,&found->token))) return;
        }
        check(CBMS_ItemRootObserved(runtime,found->token,reinterpret_cast<uintptr_t>(effect),static_cast<unsigned>(index)));
    });
}
uint16_t fire(uintptr_t caller,unsigned kind,void* reader,void* item,int ability,void* target) {
    Invocation invocation(kind,reader,item,ability,caller);
    return (kind==2?native.fire:native.fire_point)(reader,item,ability,target);
}
void* root(uintptr_t caller,void* item,int ability,int index,void* reader) {
    // Original native code retains sole ownership of allocation, effect bytes,
    // targets and charge handling. Null/early returns are forwarded unchanged.
    void* result=native.effect(item,ability,index,reader);
    attach_root(caller,item,ability,index,reader,result);return result;
}
}
int CBMS_BindItemModule(uintptr_t module,CBMS_ItemFunctions* output,char* text,uint32_t capacity) {
    if(!output||!text||capacity<2)return 0;
    auto diagnostic=[&](const char* value){const auto n=(std::min)(std::strlen(value),std::size_t(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try {std::string message;const auto result=cbm::scroll::binding::bind_items(module,message);*output=result;diagnostic(message.c_str());return 1;}
    catch(const std::exception& error){diagnostic(error.what());return 0;}
    catch(...){diagnostic("unexpected native item binding failure");return 0;}
}
int CBMS_ConfigureItemCarriers(CBMS_Runtime* value,const CBMS_ItemFunctions* functions,const void* bytes,uint32_t size,CBMS_PolicyDigest digest,void* user) {
    if(runtime || !value || !functions || !bytes || !digest) return 0;
    fault.fill(0);
    try {
        const auto& f=*functions;
        if(!f.use||!f.use_point||!f.fire||!f.fire_point||!f.effect||!f.item_type ||
           f.use==CBMS_UseItemCarrier||f.use_point==CBMS_UsePointCarrier||f.fire==CBMS_FireItemCarrier||
           f.fire_point==CBMS_FireItemPointCarrier||f.effect==CBMS_ItemEffectCarrier)
            throw std::invalid_argument("native item originals are missing or recursive");
        for(auto pc:f.root_returns) if(!pc) throw std::invalid_argument("native item root return PC is missing");
        for(auto pc:f.continuation_returns) if(!pc) throw std::invalid_argument("native item continuation PC is missing");
        auto table=std::make_unique<cbm::scroll::PolicyTable>(std::span(static_cast<const uint8_t*>(bytes),size));
        table->verify([&](std::string_view name,std::string_view extension)->std::optional<cbm::scroll::PolicyTable::Digest> {
            cbm::scroll::PolicyTable::Digest result{};
            const std::string n(name),e(extension);
            return digest(n.c_str(),e.c_str(),result.data(),user)==1?std::optional(result):std::nullopt;
        });
        native=f;policy=std::move(table);owner=std::this_thread::get_id();runtime=value;return 1;
    } catch(const std::exception& error) {fail(error.what());return 0;}
    catch(...) {fail("unexpected item carrier configuration failure");return 0;}
}
int CBMS_ItemCarriersIdle() {return runtime && owner==std::this_thread::get_id() && !busy && !current?1:0;}
int CBMS_DetachItemCarriers() {
    if(!CBMS_ItemCarriersIdle()) return 0;
    policy.reset();native={};runtime=nullptr;return 1;
}
const char* CBMS_ItemCarrierError() {return fault.data();}
void CBMS_ItemAdmission(int (*allowed)(void)){admission=allowed;}
uint16_t CBMS_UseItemCarrier(void* reader,void* target) noexcept(false) {Invocation scope(0,reader);return native.use(reader,target);}
uint16_t CBMS_UsePointCarrier(void* reader) noexcept(false) {Invocation scope(1,reader);return native.use_point(reader);}
uint16_t CBMS_FireItemCarrier(void* reader,void* item,int ability,void* target) noexcept(false) {return fire(reinterpret_cast<uintptr_t>(_ReturnAddress()),2,reader,item,ability,target);}
uint16_t CBMS_FireItemPointCarrier(void* reader,void* item,int ability,void* target) noexcept(false) {return fire(reinterpret_cast<uintptr_t>(_ReturnAddress()),3,reader,item,ability,target);}
void* CBMS_ItemEffectCarrier(void* item,int ability,int index,void* reader) noexcept(false) {return root(reinterpret_cast<uintptr_t>(_ReturnAddress()),item,ability,index,reader);}
#ifdef CBMS_OFFLINE_HARNESS
uint16_t CBMS_TestFireItemCarrier(uintptr_t caller,int point,void* reader,void* item,int ability,void* target) noexcept(false) {return fire(caller,point?3:2,reader,item,ability,target);}
void* CBMS_TestItemEffectCarrier(uintptr_t caller,void* item,int ability,int index,void* reader) noexcept(false) {return root(caller,item,ability,index,reader);}
#endif
