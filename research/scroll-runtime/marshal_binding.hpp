#pragma once
#include "native_binder.hpp"
#include "decode_profiles.hpp"
#include "marshal_profiles.hpp"
#ifdef _WIN32
namespace cbm::scroll::binding {
inline std::uintptr_t bind_marshal(std::uintptr_t base,std::string& detail) {
    std::string reader;(void)bind(base,reader);
    Image image(base);
    const auto nt=image.object<IMAGE_DOS_HEADER>(0).e_lfanew;
    const auto timestamp=image.object<IMAGE_FILE_HEADER>(nt+4).TimeDateStamp;
    const MarshalProfile* profile{};
    for(const auto& candidate:marshal_profiles) if(candidate.timestamp==timestamp) profile=&candidate;
    if(!profile) throw std::runtime_error("native Marshal has no audited supported-build profile");
    for(const auto& signature:profile->spans) {
        const auto digest=sha256(image.read(signature.rva,signature.size,true));
        if(!std::equal(digest.begin(),digest.end(),signature.sha))
            throw std::runtime_error("native Marshal ABI/filter/writer instructions changed; preserve existing code and refuse hook");
    }
    // Preserve, rather than reinstall, the two stock EEex hook sites. This
    // checks their required branch form and mapped target; it does not certify
    // every dynamically generated cave instruction or later third-party hook.
    for(auto rva:{profile->branch_rva,profile->call_rva}) {
        const auto head=image.read(rva,rva==profile->branch_rva?6:5,true);
        if(head[0]!=0xE9 || (head.size()==6&&head[5]!=0x90))
            throw std::runtime_error("native Marshal requires existing EEex size/write hook routes before scroll installation");
        std::int32_t delta{};std::memcpy(&delta,head.data()+1,4);
        const auto target=static_cast<std::uintptr_t>(static_cast<std::int64_t>(image.address(rva)+5)+delta);
        MEMORY_BASIC_INFORMATION page{};
        if(VirtualQuery(reinterpret_cast<void*>(target),&page,sizeof page)!=sizeof page||page.State!=MEM_COMMIT||
           (page.Protect&(PAGE_GUARD|PAGE_NOACCESS))) throw std::runtime_error("existing EEex Marshal hook target is not mapped");
        const auto access=page.Protect&0xFF;
        if(access!=PAGE_EXECUTE_READ&&access!=PAGE_EXECUTE_READWRITE&&access!=PAGE_EXECUTE_WRITECOPY)
            throw std::runtime_error("existing EEex Marshal hook target is not readable executable memory");
        if(target>=image.address(profile->rva)&&target<image.address(profile->rva+0x3A0))
            throw std::runtime_error("EEex Marshal hook points back inside the native serializer");
    }
    detail="certified native Marshal prologue/filter/writer spans; existing external size/write hook cave semantics remain host-owned";
    return image.address(profile->rva);
}
}
#endif
