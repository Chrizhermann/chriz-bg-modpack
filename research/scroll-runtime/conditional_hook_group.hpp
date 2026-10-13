// Ten audited contingency cast/destructor CALLs. Same tested preserving stub as selectors.
#pragma once
#include "entry_hook_group.hpp"
#include "cast_selection_code.hpp"
#include "conditional_api.h"
namespace cbm::scroll::hooks {
class ConditionalGroup {
    Group writer_;
    std::unique_ptr<Group::State> active_;
#ifdef CBMS_OFFLINE_HARNESS
    int injected_{};
#endif
public:
    bool present()const noexcept{return bool(active_);}
    uintptr_t allocation()const noexcept{return active_?reinterpret_cast<uintptr_t>(active_->memory):0;}
    void install(const CBMS_ConditionalFunctions& functions) {
        if(active_)throw std::runtime_error("conditional calls already installed or rollback pending");
        if(!CBMS_ConditionalIdle())throw std::runtime_error("conditional installation needs idle configured entries");
        auto next=std::make_unique<Group::State>();next->idle=[]{return CBMS_ConditionalIdle()==1;};
        for(unsigned i=0;i<10;++i) { const auto site=functions.calls[i];
            auto before=Group::read(site,5);std::int32_t delta{};std::memcpy(&delta,before.data()+1,4);
            if(before[0]!=0xE8||static_cast<uintptr_t>(static_cast<int64_t>(site+5)+delta)!=functions.targets[i])
                throw std::runtime_error("conditional native call is no longer its certified callee CALL");
            for(const auto& prior:next->patches)if(site<prior.address+5&&prior.address<site+5)throw std::runtime_error("selector CALL sites overlap");
            next->patches.push_back({site,std::move(before),{},false,false,0});
        }
        active_=std::move(next);auto& state=*active_;
        try {
            constexpr unsigned count=static_cast<unsigned>(std::size(cbms_selection_unwind));
            constexpr unsigned info_start=10*0x200,table_offset=info_start+10*count*48;
            constexpr unsigned total=table_offset+10*count*sizeof(RUNTIME_FUNCTION);
            static_assert(sizeof(cbms_selection_code)<0x200&&total<0x10000);
            state.allocation_size=(total+0xFFF)&~std::size_t(0xFFF);
            state.memory=Group::allocate_near(functions.calls[0],state.allocation_size);
            auto* bytes=static_cast<unsigned char*>(state.memory);const auto base=reinterpret_cast<uintptr_t>(bytes);
            state.table=reinterpret_cast<RUNTIME_FUNCTION*>(bytes+table_offset);
            const auto callback=reinterpret_cast<uintptr_t>(CBMS_ConditionalBefore);
            for(unsigned i=0;i<10;++i) {
                const auto offset=i*0x200;std::memcpy(bytes+offset,cbms_selection_code,sizeof cbms_selection_code);
                std::memcpy(bytes+offset+cbms_selection_selector,&i,4);
                std::memcpy(bytes+offset+cbms_selection_callback,&callback,8);
                std::memcpy(bytes+offset+cbms_selection_getter,&functions.targets[i],8);
                for(unsigned j=0;j<count;++j) {
                    const auto& segment=cbms_selection_unwind[j];const auto info=info_start+(i*count+j)*48;
                    if(segment.size>48||segment.end>sizeof cbms_selection_code)throw std::logic_error("generated selector unwind bounds invalid");
                    std::memcpy(bytes+info,segment.info,segment.size);state.table[i*count+j]={offset+segment.begin,offset+segment.end,info};
                }
                auto& patch=state.patches[i];const auto distance=static_cast<int64_t>(base+offset)-static_cast<int64_t>(patch.address+5);
                if(distance<INT32_MIN||distance>INT32_MAX)throw std::runtime_error("conditional native call relay outside rel32 range");
                const auto relative=static_cast<int32_t>(distance);patch.after={0xE8,0,0,0,0};std::memcpy(patch.after.data()+1,&relative,4);
            }
            DWORD old{};
            if(!VirtualProtect(state.memory,state.allocation_size,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),state.memory,state.allocation_size))
                throw std::runtime_error("cannot finalize conditional native call bridge page");
            if(!RtlAddFunctionTable(state.table,10*count,base))throw std::runtime_error("cannot register conditional native call unwind ranges");
            state.registered=true;
            for(unsigned i=0;i<10;++i) {
                writer_.write(state.patches[i],true);
#ifdef CBMS_OFFLINE_HARNESS
                if(injected_==static_cast<int>(i+1)){injected_=0;throw std::runtime_error("injected partial selector installation failure");}
#endif
            }
        }catch(...) {
            bool restored=true;
            for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->written){try{writer_.write(*it,false);}catch(...){restored=false;}}
            if(restored&&Group::cleanup(state))active_.reset();throw;
        }
    }
    void ready_remove() const {
        if(!active_)throw std::runtime_error("native selection calls are not installed");auto& state=*active_;
        if(state.owner!=std::this_thread::get_id()||!state.idle())throw std::runtime_error("selector removal needs quiescent owner thread");
        for(const auto& patch:state.patches)if(patch.written&&Group::read(patch.address,5)!=patch.after)
            throw std::runtime_error("another owner changed a selector CALL; retain bridge and refuse overwrite");
    }
    void remove() {
        ready_remove();auto& state=*active_;
        for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->written)writer_.write(*it,false);
        if(!Group::cleanup(state))throw std::runtime_error("selector calls restored but safe cleanup remains pending");active_.reset();
    }
#ifdef CBMS_OFFLINE_HARNESS
    void inject_failure(int value)noexcept{injected_=value;writer_.injected_=value==100?100:0;}
#endif
};
}
