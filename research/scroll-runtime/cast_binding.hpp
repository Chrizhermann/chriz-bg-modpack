#pragma once
#include "native_binder.hpp"
#include "decode_profiles.hpp"
#include "cast_profiles.hpp"
#include "cast_carrier_api.h"
namespace cbm::scroll::binding {
inline CBMS_CastFunctions bind_cast(uintptr_t base,std::string& detail) {
    std::string reader;const auto provider=bind(base,reader);Image image(base);
    const auto timestamp=image.object<IMAGE_FILE_HEADER>(image.object<IMAGE_DOS_HEADER>(0).e_lfanew+4).TimeDateStamp;
    const CastProfile* profile{};for(const auto& candidate:cast_profiles)if(candidate.timestamp==timestamp)profile=&candidate;
    if(!profile)throw std::runtime_error("cast carrier has no audited native build");
    for(const auto& span:profile->spans) {
        const auto digest=sha256(image.read(span.rva,span.size,true));
        if(!std::equal(digest.begin(),digest.end(),span.sha))throw std::runtime_error("native cast/selector/child ABI body or call edge changed");
    }
    // These four exact E9 boundaries are owned by the pinned EEex casting-glow
    // and direction fixes. Their dynamic caves remain EEex-owned, not bypassed.
    for(unsigned i=0;i<4;++i) {
        const auto head=image.read(profile->fixes[i],profile->fix_sizes[i],true);
        if(head[0]!=0xE9||std::any_of(head.begin()+5,head.end(),[](auto b){return b!=0x90;}))
            throw std::runtime_error("expected existing EEex casting direction/glow fix is absent or changed");
        std::int32_t displacement{};std::memcpy(&displacement,head.data()+1,4);
        const auto target=static_cast<uintptr_t>(static_cast<int64_t>(image.address(profile->fixes[i])+5)+displacement);
        MEMORY_BASIC_INFORMATION page{};
        if(VirtualQuery(reinterpret_cast<void*>(target),&page,sizeof page)!=sizeof page||page.State!=MEM_COMMIT||page.Protect&(PAGE_GUARD|PAGE_NOACCESS))
            throw std::runtime_error("EEex casting fix target is not mapped");
        const auto access=page.Protect&0xFF;
        if(access!=PAGE_EXECUTE_READ&&access!=PAGE_EXECUTE_READWRITE&&access!=PAGE_EXECUTE_WRITECOPY)
            throw std::runtime_error("EEex casting fix target is not readable executable memory");
        for(const auto& span:profile->spans)if(target>=image.address(span.rva)&&target<image.address(span.rva+span.size))
            throw std::runtime_error("EEex casting fix unexpectedly points inside a native cast body");
        for(unsigned j=0;j<4;++j)if(target>=image.address(profile->fixes[j])&&target<image.address(profile->fixes[j]+profile->fix_sizes[j]))
            throw std::runtime_error("EEex casting fix loops into a native hook site");
    }
    CBMS_CastFunctions out{};
    out.effect_fire=reinterpret_cast<CBMS_EffectFireOriginal>(image.address(profile->entries[0]));
    out.fire=reinterpret_cast<CBMS_FireOriginal>(image.address(profile->entries[1]));out.fire_point=reinterpret_cast<CBMS_FireOriginal>(image.address(profile->entries[2]));
    out.force=reinterpret_cast<CBMS_CastTargetOriginal>(image.address(profile->entries[3]));out.force_point=reinterpret_cast<CBMS_CastPointOriginal>(image.address(profile->entries[4]));
    out.spell=reinterpret_cast<CBMS_CastTargetOriginal>(image.address(profile->entries[5]));out.spell_point=reinterpret_cast<CBMS_CastPointOriginal>(image.address(profile->entries[6]));
    out.child=reinterpret_cast<CBMS_SpellEffectOriginal>(image.address(profile->entries[7]));out.caster_type=provider.caster_type;out.count_getter=image.address(profile->getter);
    for(unsigned i=0;i<7;++i){out.selection_calls[i]=image.address(profile->selection[i]);out.child_returns[i]=image.address(profile->children[i]);}
    for(unsigned i=0;i<2;++i)out.extra_returns[i]=image.address(profile->extras[i]);
    detail="certified eight cast/child entries, seven preselection calls, and exact child/extra-target attribution; EEex fix caves remain host-owned";return out;
}
}
