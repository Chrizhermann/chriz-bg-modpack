#pragma once
#include "native_binder.hpp"
#include "decode_profiles.hpp"
#include "dispatch_profiles.hpp"
#include "dispatch_carrier_api.h"
#ifdef _WIN32
namespace cbm::scroll::binding {
inline CBMS_DispatchFunctions bind_dispatch(uintptr_t base,std::string& detail) {
    std::string reader;(void)bind(base,reader);Image image(base);
    const auto nt=image.object<IMAGE_DOS_HEADER>(0).e_lfanew;
    const auto timestamp=image.object<IMAGE_FILE_HEADER>(nt+4).TimeDateStamp;
    const DispatchProfile* profile{};
    for(const auto& candidate:dispatch_profiles)if(candidate.timestamp==timestamp)profile=&candidate;
    if(!profile)throw std::runtime_error("dispatch carrier has no supported audited build");
    for(const auto& s:profile->spans) {
        const auto digest=sha256(image.read(s.rva,s.size,true));
        if(!std::equal(digest.begin(),digest.end(),s.sha))throw std::runtime_error("native dispatch/lifetime body or attribution call edge changed");
    }
    for(unsigned i=0;i<7;++i)if(image.object<uintptr_t>(profile->vtable+i*8)!=image.address(profile->slots[i]))
        throw std::runtime_error("native FireSpell message vtable ownership changed");
    // The value-carried action witness relies on these exact CString bodies
    // (shared copies, counted release, copy before any write) and on the
    // CMessageInsertAction class the owned mode0 producer builds.
    for(const auto& s:profile->strings) {
        const auto digest=sha256(image.read(s.rva,s.size,true));
        if(!std::equal(digest.begin(),digest.end(),s.sha))throw std::runtime_error("native CString reference-count body changed");
    }
    for(unsigned i=0;i<7;++i)if(image.object<uintptr_t>(profile->insert_vtable+i*8)!=image.address(profile->insert_slots[i]))
        throw std::runtime_error("native CMessageInsertAction vtable ownership changed");
    for(auto rva:profile->routes) {
        const auto head=image.read(rva,5,true);
        if(head[0]!=0xE9)throw std::runtime_error("dispatch requires the existing EEex mode0 route before scroll hooks");
        std::int32_t delta{};std::memcpy(&delta,head.data()+1,4);
        const auto target=static_cast<uintptr_t>(static_cast<int64_t>(image.address(rva)+5)+delta);
        MEMORY_BASIC_INFORMATION page{};
        if(VirtualQuery(reinterpret_cast<void*>(target),&page,sizeof page)!=sizeof page||page.State!=MEM_COMMIT||
           (page.Protect&(PAGE_GUARD|PAGE_NOACCESS)))throw std::runtime_error("EEex dispatch route target is not mapped");
        const auto access=page.Protect&0xFF;
        if(access!=PAGE_EXECUTE_READ&&access!=PAGE_EXECUTE_READWRITE&&access!=PAGE_EXECUTE_WRITECOPY)
            throw std::runtime_error("EEex dispatch route target is not readable executable memory");
        for(const auto& s:profile->spans)if(target>=image.address(s.rva)&&target<image.address(s.rva+s.size))
            throw std::runtime_error("EEex dispatch route points inside an audited native body");
        for(auto route:profile->routes)if(target>=image.address(route)&&target<image.address(route+5))
            throw std::runtime_error("EEex dispatch route points back into a native route site");
    }
    CBMS_DispatchFunctions out{};
    out.apply146=reinterpret_cast<CBMS_ApplyOriginal>(image.address(profile->entries[0]));
    out.apply148=reinterpret_cast<CBMS_ApplyOriginal>(image.address(profile->entries[1]));
    out.action_default=reinterpret_cast<CBMS_ActionDefaultOriginal>(image.address(profile->entries[2]));
    out.add_message=reinterpret_cast<CBMS_AddMessageOriginal>(image.address(profile->entries[3]));
    out.fire_run=reinterpret_cast<CBMS_MessageRunOriginal>(image.address(profile->entries[4]));
    out.fire_destroy=reinterpret_cast<CBMS_MessageDestroyOriginal>(image.address(profile->entries[5]));
    for(unsigned i=0;i<2;++i)out.action_default_returns[i]=image.address(profile->ctors[i]);
    out.fire_add_return=image.address(profile->add_return);out.fire_run_return=image.address(profile->run_return);
    out.effect_fire_return=image.address(profile->effect_return);out.point_fire_return=image.address(profile->point_return);out.fire_vtable=image.address(profile->vtable);
    out.insert_vtable=image.address(profile->insert_vtable);out.empty_string=image.address(profile->empty_string);
    detail="certified native producers/message lifetime, CString witness ABI and attribution PCs; existing external EEex mode0 caves remain host-owned";
    return out;
}
}
#endif
