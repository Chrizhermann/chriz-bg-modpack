// Internal implementation shared by concrete certified entry groups. This is
// not an exported arbitrary-hook API. Callers supply their audited recipes.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <functional>
#include <memory>
#include <span>
#include <stdexcept>
#include <thread>
#include <vector>
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
namespace cbm::scroll::hooks {
struct Entry {
    uintptr_t address,callback;
    std::span<const unsigned char> prefix,unwind;
    bool allocated_frame;
    bool call_site{}; // Exact five-byte E8: wrap its callee; retain native return PC.
};
class Group {
    friend class SelectionGroup; // Shares the exact guarded write/rollback machinery.
    friend class ActionGroup;
    friend class ConditionalGroup;
    struct Patch {uintptr_t address;std::vector<unsigned char> before,after;bool written{},pending{};DWORD protection{};};
    struct State {
        std::thread::id owner{std::this_thread::get_id()};
        void* memory{};std::size_t allocation_size{};RUNTIME_FUNCTION* table{};bool registered{},configured{};
        std::vector<Patch> patches;
        std::function<bool()> detach,idle;
    };
    std::unique_ptr<State> active_;
#ifdef CBMS_OFFLINE_HARNESS
    int injected_{};
#endif
    static std::vector<unsigned char> read(uintptr_t address,std::size_t size) {
        if(!address||size>UINTPTR_MAX-address)throw std::runtime_error("invalid native entry range");
        std::vector<unsigned char> out(size);SIZE_T length{};
        if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),out.data(),size,&length)||length!=size)
            throw std::runtime_error("native entry became unreadable");
        return out;
    }
    static bool finalize(Patch& patch) {
        DWORD ignored{};
        const bool protect=VirtualProtect(reinterpret_cast<void*>(patch.address),patch.before.size(),patch.protection,&ignored)!=0;
        const bool cache=FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(patch.address),patch.before.size())!=0;
        patch.pending=!protect||!cache;return !patch.pending;
    }
    void write(Patch& patch,bool forward) {
        const auto& expected=forward?patch.before:patch.after;const auto& replacement=forward?patch.after:patch.before;
        if(expected.empty()||expected.size()!=replacement.size()||read(patch.address,expected.size())!=expected)
            throw std::runtime_error("another owner changed a native entry; refusing overwrite");
        SYSTEM_INFO system{};GetSystemInfo(&system);
        if(patch.address/system.dwPageSize!=(patch.address+expected.size()-1)/system.dwPageSize)
            throw std::runtime_error("native entry patch crosses a page boundary");
        DWORD old{};
        if(!VirtualProtect(reinterpret_cast<void*>(patch.address),expected.size(),PAGE_EXECUTE_READWRITE,&old))
            throw std::runtime_error("cannot change native entry protection");
        if(!patch.protection)patch.protection=old;
        patch.pending=true;std::memcpy(reinterpret_cast<void*>(patch.address),replacement.data(),replacement.size());patch.written=forward;
#ifdef CBMS_OFFLINE_HARNESS
        if(forward&&injected_==100){injected_=0;throw std::runtime_error("injected native entry protection-finalization failure");}
#endif
        if(!finalize(patch))throw std::runtime_error("native entry written but cache/protection restoration pending; retain relay");
    }
    static void* allocate_near(uintptr_t address,std::size_t size) {
        SYSTEM_INFO system{};GetSystemInfo(&system);
        const auto step=uintptr_t(system.dwAllocationGranularity),center=address&~(step-1);
        for(uintptr_t distance=step;distance<0x7FFF0000;distance+=step)for(int direction:{1,-1}) {
            if((direction<0&&distance>=center)||(direction>0&&distance>UINTPTR_MAX-center))continue;
            const auto at=direction>0?center+distance:center-distance;MEMORY_BASIC_INFORMATION page{};
            if(VirtualQuery(reinterpret_cast<void*>(at),&page,sizeof page)!=sizeof page||page.State!=MEM_FREE)continue;
            if(auto* memory=VirtualAlloc(reinterpret_cast<void*>(at),size,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE))return memory;
        }
        throw std::runtime_error("no relay allocation within native entry rel32 reach");
    }
    static void absolute_jump(unsigned char* out,uintptr_t target) {
        const unsigned char prefix[]{0xFF,0x25,0,0,0,0};std::memcpy(out,prefix,6);std::memcpy(out+6,&target,8);
    }
    static bool cleanup(State& state) {
        for(auto& patch:state.patches)if(patch.written)return false;
        for(auto& patch:state.patches)if(patch.pending&&!finalize(patch))return false;
        if(state.configured){if(!state.detach())return false;state.configured=false;}
        if(state.registered){if(!RtlDeleteFunctionTable(state.table))return false;state.registered=false;}
        if(state.memory){if(!VirtualFree(state.memory,0,MEM_RELEASE))return false;state.memory=nullptr;}
        return true;
    }
public:
    bool present()const noexcept{return active_!=nullptr;}
    using Configure=std::function<bool(std::span<const uintptr_t>)>;
    void install(std::span<const Entry> entries,const Configure& configure,std::function<bool()> detach,std::function<bool()> idle) {
        if(active_)throw std::runtime_error("native entry group already installed or rollback pending");
        if(entries.empty()||entries.size()>32||!configure||!detach||!idle)throw std::invalid_argument("invalid certified entry group");
        auto next=std::make_unique<State>();next->detach=std::move(detach);next->idle=std::move(idle);
        for(const auto& entry:entries) {
            if(!entry.callback||entry.prefix.size()<5||entry.prefix.size()>64||entry.unwind.size()<4||entry.unwind.size()>64)
                throw std::invalid_argument("entry recipe exceeds bounded trampoline layout");
            if(entry.call_site&&(entry.prefix.size()!=5||entry.prefix[0]!=0xE8||entry.allocated_frame))
                throw std::invalid_argument("callee wrapper requires one exact native CALL");
            auto observed=read(entry.address,entry.prefix.size());
            if(!std::equal(observed.begin(),observed.end(),entry.prefix.begin()))throw std::runtime_error("native entry changed after certification");
            for(const auto& prior:next->patches)if(entry.address<prior.address+prior.before.size()&&prior.address<entry.address+observed.size())
                throw std::runtime_error("native entry patches overlap");
            next->patches.push_back({entry.address,std::move(observed),{},false,false,0});
        }
        active_=std::move(next);auto& state=*active_;
        try {
            const auto table_offset=static_cast<unsigned>(entries.size()*0x100);
            state.allocation_size=(table_offset+entries.size()*sizeof(RUNTIME_FUNCTION)+0xFFF)&~std::size_t(0xFFF);
            state.memory=allocate_near(entries[0].address,state.allocation_size);
            auto* bytes=static_cast<unsigned char*>(state.memory);const auto base=reinterpret_cast<uintptr_t>(bytes);
            state.table=reinterpret_cast<RUNTIME_FUNCTION*>(bytes+table_offset);std::vector<uintptr_t> trampolines;
            for(unsigned i=0;i<entries.size();++i) {
                const auto offset=i*0x100;const auto& entry=entries[i];auto& patch=state.patches[i];
                const auto relay=base+offset,trampoline=relay+0x20,resume=entry.address+entry.prefix.size();
                trampolines.push_back(trampoline);absolute_jump(bytes+offset,entry.callback);
                std::memcpy(bytes+offset+0x20,entry.prefix.data(),entry.prefix.size());auto* tail=bytes+offset+0x20+entry.prefix.size();
                if(entry.call_site) {
                    int32_t delta{};std::memcpy(&delta,entry.prefix.data()+1,4);
                    const auto target=static_cast<uintptr_t>(static_cast<int64_t>(entry.address+5)+delta);
                    absolute_jump(bytes+offset+0x20,target);
                }else if(entry.allocated_frame) {
                    const unsigned char lo[]{0xC7,0x04,0x24},hi[]{0xC7,0x44,0x24,0x04},jump[]{0xFF,0x64,0x24,0x00};
                    const auto lower=static_cast<uint32_t>(resume),upper=static_cast<uint32_t>(resume>>32);
                    std::memcpy(tail,lo,3);std::memcpy(tail+3,&lower,4);std::memcpy(tail+7,hi,4);std::memcpy(tail+11,&upper,4);std::memcpy(tail+15,jump,4);
                }else absolute_jump(tail,resume);
                std::memcpy(bytes+offset+0x80,entry.unwind.data(),entry.unwind.size());
                state.table[i]={offset+0x20,offset+0x20+(entry.call_site?6u:static_cast<unsigned>(entry.prefix.size())+(entry.allocated_frame?19u:6u)),offset+0x80};
                const auto delta=static_cast<int64_t>(relay)-static_cast<int64_t>(entry.address+5);
                if(delta<INT32_MIN||delta>INT32_MAX)throw std::runtime_error("entry relay outside rel32 range");
                const auto relative=static_cast<int32_t>(delta);patch.after.assign(entry.prefix.size(),0x90);patch.after[0]=entry.call_site?0xE8:0xE9;std::memcpy(patch.after.data()+1,&relative,4);
            }
            DWORD old{};
            if(!VirtualProtect(state.memory,state.allocation_size,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),state.memory,state.allocation_size))
                throw std::runtime_error("cannot finalize native trampoline page");
            if(!RtlAddFunctionTable(state.table,static_cast<DWORD>(entries.size()),base))throw std::runtime_error("cannot register native entry unwind table");
            state.registered=true;
            if(!configure(trampolines))throw std::runtime_error("typed native entry configuration refused");
            state.configured=true;
            for(unsigned i=0;i<entries.size();++i) {
                write(state.patches[i],true);
#ifdef CBMS_OFFLINE_HARNESS
                if(injected_==static_cast<int>(i+1)){injected_=0;throw std::runtime_error("injected partial native entry installation failure");}
#endif
            }
        }catch(...) {
            bool restored=true;
            for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->written){try{write(*it,false);}catch(...){restored=false;}}
            if(restored&&cleanup(state))active_.reset();throw;
        }
    }
    void ready_remove() const {
        if(!active_)throw std::runtime_error("native entry group is not installed");auto& state=*active_;
        if(state.owner!=std::this_thread::get_id()||(state.configured&&!state.idle()))throw std::runtime_error("native entry removal requires quiescent owner thread");
        for(const auto& patch:state.patches)if(patch.written&&read(patch.address,patch.after.size())!=patch.after)
            throw std::runtime_error("another owner changed a native entry; retain group and refuse overwrite");
    }
    void remove() {
        ready_remove();auto& state=*active_;
        for(auto it=state.patches.rbegin();it!=state.patches.rend();++it)if(it->written)write(*it,false);
        if(!cleanup(state))throw std::runtime_error("native entries restored but safe cleanup remains pending");active_.reset();
    }
#ifdef CBMS_OFFLINE_HARNESS
    uintptr_t allocation()const noexcept{return active_?reinterpret_cast<uintptr_t>(active_->memory):0;}
    void inject_failure(int point)noexcept{injected_=point;}
#endif
};
}
