#pragma once
#include "native_binder.hpp"
#include "action_profiles.hpp"
#include "action_carrier_api.h"
namespace cbm::scroll::binding {
inline CBMS_ActionFunctions bind_action(uintptr_t base,std::string& detail) {
    std::string reader;(void)bind(base,reader);Image image(base);
    const auto nt=image.object<IMAGE_DOS_HEADER>(0).e_lfanew;
    const auto timestamp=image.object<IMAGE_FILE_HEADER>(nt+4).TimeDateStamp;
    const auto size=image.object<IMAGE_OPTIONAL_HEADER64>(nt+4+sizeof(IMAGE_FILE_HEADER)).SizeOfImage;
    unsigned index=0;
    for(const auto& profile:actions::profiles) {
        if(profile.timestamp==timestamp&&profile.image_size==size) {
            CBMS_ActionFunctions result{};result.profile=index;
            for(unsigned i=0;i<3;++i) {
                const auto& site=profile.sites[i];
                const auto digest=sha256(image.read(site.function,site.body_size,true));
                if(!std::equal(digest.begin(),digest.end(),site.sha))
                    throw std::runtime_error("native action copy/assignment/destruction body changed; action ABI audit required");
                result.sites[i]=image.address(site.site);
            }
            detail="certified completed CAIAction copy/assignment and destructor entry";return result;
        }
        ++index;
    }
    throw std::runtime_error("action lifecycle has no supported audited native build");
}
}
