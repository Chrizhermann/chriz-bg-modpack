#pragma once
#include "native_binder.hpp"
#include "decode_profiles.hpp"
#include "item_profiles.hpp"
#include "item_carrier_api.h"
#ifdef _WIN32
namespace cbm::scroll::binding {
inline CBMS_ItemFunctions bind_items(uintptr_t base,std::string& detail) {
    std::string reader;(void)bind(base,reader);
    Image image(base);
    const auto nt=image.object<IMAGE_DOS_HEADER>(0).e_lfanew;
    const auto timestamp=image.object<IMAGE_FILE_HEADER>(nt+4).TimeDateStamp;
    const ItemProfile* profile{};
    for(const auto& candidate:item_profiles) if(candidate.timestamp==timestamp) profile=&candidate;
    if(!profile) throw std::runtime_error("item carrier has no audited supported-build profile");
    for(const auto& span:profile->spans) {
        const auto digest=sha256(image.read(span.rva,span.size,true));
        if(!std::equal(digest.begin(),digest.end(),span.sha))
            throw std::runtime_error("native item body/call edge changed; preserve existing code and refuse item hooks");
    }
    CBMS_ItemFunctions result{};
    result.use=reinterpret_cast<CBMS_UseItemOriginal>(image.address(profile->spans[0].rva));
    result.use_point=reinterpret_cast<CBMS_UsePointOriginal>(image.address(profile->spans[1].rva));
    result.fire=reinterpret_cast<CBMS_FireItemOriginal>(image.address(profile->spans[2].rva));
    result.fire_point=reinterpret_cast<CBMS_FireItemOriginal>(image.address(profile->spans[3].rva));
    result.effect=reinterpret_cast<CBMS_ItemEffectOriginal>(image.address(profile->spans[4].rva));
    result.item_type=reinterpret_cast<CBMS_ItemTypeOriginal>(image.address(profile->spans[5].rva));
    for(unsigned i=0;i<4;++i) result.root_returns[i]=image.address(profile->roots[i]);
    for(unsigned i=0;i<2;++i) result.continuation_returns[i]=image.address(profile->continuations[i]);
    detail="certified six item bodies, four root CALLs and two extra-target continuations; no native function invoked";
    return result;
}
}
#endif
