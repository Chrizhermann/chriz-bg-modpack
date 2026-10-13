#include "action_hook_host.h"
#include "action_profiles.hpp"
#include "entry_hook_group.hpp"
namespace cbm::scroll::hooks {
class ActionGroup {
    Group writer_;
    std::unique_ptr<Group::State> active_;
#ifdef CBMS_OFFLINE_HARNESS
    int injected_{};
#endif
public:
    uintptr_t allocation()const noexcept{return active_?reinterpret_cast<uintptr_t>(active_->memory):0;}
    void install(const CBMS_ActionFunctions& functions,CBMS_Runtime* runtime) {
        if(active_)throw std::runtime_error("action lifecycle already installed or rollback pending");
        if(!runtime||functions.profile>=std::size(actions::profiles))throw std::invalid_argument("invalid action runtime or certified profile");
        const auto& profile=actions::profiles[functions.profile];
        auto next=std::make_unique<Group::State>();
        next->idle=[]{return CBMS_ActionCarriersIdle()==1;};next->detach=[]{return CBMS_DetachActionCarriers()==1;};
        for(unsigned i=0;i<3;++i) {
            const auto& site=profile.sites[i];const auto address=functions.sites[i];
            auto observed=Group::read(address,site.patch_size);
            if(!std::equal(observed.begin(),observed.end(),site.original))throw std::runtime_error("native action boundary changed after certification");
            for(const auto& prior:next->patches)if(address<prior.address+prior.before.size()&&prior.address<address+observed.size())
                throw std::runtime_error("native action boundaries overlap");
            next->patches.push_back({address,std::move(observed),{},false,false,0});
        }
        active_=std::move(next);auto& state=*active_;
        try {
            state.allocation_size=(std::size_t(profile.payload_size)+0xFFF)&~std::size_t(0xFFF);
            state.memory=Group::allocate_near(functions.sites[0],state.allocation_size);
            auto* bytes=static_cast<unsigned char*>(state.memory);const auto base=reinterpret_cast<uintptr_t>(bytes);
            std::memcpy(bytes,profile.payload,profile.payload_size);
            state.table=reinterpret_cast<RUNTIME_FUNCTION*>(bytes+profile.table_offset);
            for(unsigned i=0;i<3;++i) {
                const auto& site=profile.sites[i];auto& patch=state.patches[i];
                auto* code=bytes+site.code_offset;
                const auto callback=i==2?reinterpret_cast<uintptr_t>(CBMS_ActionDestroyCarrier):reinterpret_cast<uintptr_t>(CBMS_ActionCopiedCarrier);
                const auto resume=patch.address+site.patch_size;
                const auto lo=static_cast<uint32_t>(resume),hi=static_cast<uint32_t>(resume>>32);
                std::memcpy(code+site.runtime,&runtime,8);std::memcpy(code+site.callback,&callback,8);
                std::memcpy(code+site.resume_lo,&lo,4);std::memcpy(code+site.resume_hi,&hi,4);
                const auto distance=static_cast<int64_t>(base+site.code_offset)-static_cast<int64_t>(patch.address+5);
                if(distance<INT32_MIN||distance>INT32_MAX)throw std::runtime_error("action relay outside rel32 range");
                const auto relative=static_cast<int32_t>(distance);patch.after.assign(site.patch_size,0x90);patch.after[0]=0xE9;
                std::memcpy(patch.after.data()+1,&relative,4);
            }
            DWORD old{};
            if(!VirtualProtect(state.memory,state.allocation_size,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),state.memory,state.allocation_size))
                throw std::runtime_error("cannot finalize action bridge page");
            if(!RtlAddFunctionTable(state.table,profile.count,base))throw std::runtime_error("cannot register action bridge unwind table");
            state.registered=true;
            if(!CBMS_ConfigureActionCarriers(runtime))throw std::runtime_error("action carrier configuration refused");
            state.configured=true;
            for(unsigned i=0;i<3;++i) {
                writer_.write(state.patches[i],true);
#ifdef CBMS_OFFLINE_HARNESS
                if(injected_==static_cast<int>(i+1)){injected_=0;throw std::runtime_error("injected partial action installation failure");}
#endif
            }
        }catch(...) {
            bool restored=true;
            for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->written){try{writer_.write(*it,false);}catch(...){restored=false;}}
            if(restored&&Group::cleanup(state))active_.reset();throw;
        }
    }
    void ready_remove()const {
        if(!active_)throw std::runtime_error("native action lifecycle is not installed");const auto& state=*active_;
        if(state.owner!=std::this_thread::get_id()||(state.configured&&!state.idle()))throw std::runtime_error("action removal needs quiescent owner thread");
        for(const auto& patch:state.patches)if(patch.written&&Group::read(patch.address,patch.after.size())!=patch.after)
            throw std::runtime_error("another owner changed an action boundary; retain bridge and refuse overwrite");
    }
    void remove() {
        ready_remove();auto& state=*active_;
        for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->written)writer_.write(*it,false);
        if(!Group::cleanup(state))throw std::runtime_error("action boundaries restored but safe cleanup remains pending");active_.reset();
    }
#ifdef CBMS_OFFLINE_HARNESS
    void inject_failure(int value)noexcept{injected_=value;writer_.injected_=value==100?100:0;}
#endif
};
}
namespace {
cbm::scroll::hooks::ActionGroup group;std::array<char,256> error{};
void fail(const char* text)noexcept {const auto n=(std::min)(std::strlen(text),error.size()-1);std::memcpy(error.data(),text,n);error[n]=0;}
template<class F> int guarded(F&& body)noexcept {
    try{body();error.fill(0);return 1;}catch(const std::exception& issue){fail(issue.what());}catch(...){fail("unexpected action hook failure");}return 0;
}
}
int CBMS_InstallActionHooks(uintptr_t game,CBMS_Runtime* runtime) {
    return guarded([&]{
        CBMS_ActionFunctions functions{};std::array<char,512> diagnostic{};
        if(!CBMS_BindActionModule(game,&functions,diagnostic.data(),static_cast<uint32_t>(diagnostic.size())))throw std::runtime_error(diagnostic.data());
        group.install(functions,runtime);
    });
}
int CBMS_ActionHooksReadyRemove(){return guarded([]{group.ready_remove();});}
int CBMS_RemoveActionHooks(){return guarded([]{group.remove();});}
const char* CBMS_ActionHookError(){return error[0]?error.data():CBMS_ActionCarrierError();}
extern "C" int CBMS_ActionHooksPresent(){return group.allocation()?1:0;}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestInstallActionHooks(const CBMS_ActionFunctions* functions,CBMS_Runtime* runtime) {
    return guarded([&]{if(!functions)throw std::invalid_argument("null private action functions");group.install(*functions,runtime);});
}
uintptr_t CBMS_TestActionHookAllocation(){return group.allocation();}
void CBMS_TestActionHookFailure(int point){group.inject_failure(point);}
#endif
