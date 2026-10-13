#pragma once
#include "decode_binding.hpp"
#include "lifecycle_profiles.hpp"
#ifdef _WIN32
namespace cbm::scroll::binding {
inline std::vector<unsigned char> bank_code(uintptr_t address,size_t size) {
    if(!address||!size||size>64||size>UINTPTR_MAX-address)throw std::runtime_error("invalid bounded banking code range");
    auto cursor=address;const auto end=address+size;
    while(cursor<end){MEMORY_BASIC_INFORMATION region{};
        if(VirtualQuery(reinterpret_cast<void*>(cursor),&region,sizeof region)!=sizeof region||region.State!=MEM_COMMIT||
           (region.Protect&(PAGE_GUARD|PAGE_NOACCESS)))throw std::runtime_error("banking code is not committed/readable");
        const auto access=region.Protect&0xFF;
        if(access!=PAGE_EXECUTE_READ&&access!=PAGE_EXECUTE_READWRITE&&access!=PAGE_EXECUTE_WRITECOPY)
            throw std::runtime_error("banking code is not executable/readable");
        const auto start=reinterpret_cast<uintptr_t>(region.BaseAddress);
        if(start>cursor||region.RegionSize>UINTPTR_MAX-start||start+region.RegionSize<=cursor)
            throw std::runtime_error("invalid banking code region");
        cursor=(std::min)(end,start+region.RegionSize);
    }
    std::vector<unsigned char> bytes(size);SIZE_T read{};
    if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(address),bytes.data(),size,&read)||read!=size)
        throw std::runtime_error("banking code changed during certification");
    return bytes;
}
inline void authenticate_bank_actor(const CBMS_BankActorChain& chain,std::uintptr_t expected) {
    const auto module=GetModuleHandleW(L"cbmbank_identity.dll");
    if(chain.schema!=1||chain.entry!=expected||!module||
       reinterpret_cast<uintptr_t>(GetProcAddress(module,"CBMI_Destruct"))!=chain.handler||!chain.handler)
        throw std::runtime_error("banking actor destructor offer does not name its loaded native handler");
    constexpr unsigned char original[]{0x4C,0x8B,0xDC,0x49,0x89,0x4B,0x08};
    if(!std::equal(std::begin(original),std::end(original),chain.original)||
       chain.replacement[0]!=0xE9||chain.replacement[5]!=0x90||chain.replacement[6]!=0x90)
        throw std::runtime_error("banking actor destructor offer has an unexpected native prefix or entry jump");
    const auto current=bank_code(chain.entry,7);
    if(!std::equal(current.begin(),current.end(),chain.replacement))
        throw std::runtime_error("banking actor destructor entry changed after its offer");
    int32_t displacement{};std::memcpy(&displacement,chain.replacement+1,4);
    const auto relay=static_cast<uintptr_t>(static_cast<int64_t>(chain.entry+5)+displacement);
    const auto head=bank_code(relay,6);uintptr_t target{};
    if(head[0]==0xE9){int32_t delta{};std::memcpy(&delta,head.data()+1,4);target=static_cast<uintptr_t>(static_cast<int64_t>(relay+5)+delta);}
    else if(head[0]==0xFF&&head[1]==0x25&&!head[2]&&!head[3]&&!head[4]&&!head[5]){const auto pointer=bank_code(relay+6,8);std::memcpy(&target,pointer.data(),8);}
    if(target!=chain.handler)throw std::runtime_error("banking actor destructor relay no longer reaches its authenticated handler");
    (void)bank_code(chain.handler,1);
}
inline CBMS_LifecycleFunctions bind_lifecycle(std::uintptr_t game,std::uintptr_t eeex,std::string& message,
    CBMS_BankActorQuery query=nullptr,void* user=nullptr,CBMS_BankActorChain* accepted=nullptr) {
    (void)bind_decode(game,eeex,message); // also certifies actual EEex module/header/route
    Image image(eeex);const auto nt=image.object<IMAGE_DOS_HEADER>(0).e_lfanew;
    const auto timestamp=image.object<IMAGE_FILE_HEADER>(nt+4).TimeDateStamp;
    const LifecycleProfile* profile{};
    for(const auto& candidate:lifecycle_profiles) if(candidate.timestamp==timestamp) profile=&candidate;
    if(!profile) throw std::runtime_error("no supported shipped EEex lifecycle profile");
    CBMS_BankActorChain chained{};
    for(unsigned i=0;i<3;++i) for(const auto* signature:{&profile->bodies[i],&profile->registrations[i]}) {
        auto bytes=image.read(signature->rva,signature->size,true);
        if(i==2&&signature==&profile->bodies[2]&&bytes.size()>=7&&bytes[0]==0xE9) {
            const auto entry=image.address(signature->rva);
            if(!query||!accepted||query(entry,&chained,user)!=1)
                throw std::runtime_error("actor destructor already owned without the verified banking chain offer");
            authenticate_bank_actor(chained,entry);
            // Certify every original native body byte, including all tail
            // instructions; only the authenticated seven-byte entry differs.
            std::copy(std::begin(chained.original),std::end(chained.original),bytes.begin());
        }
        const auto digest=sha256(bytes);
        if(!std::equal(digest.begin(),digest.end(),signature->sha))
            throw std::runtime_error("EEex lifecycle entry or export registration changed; refuse to replace its owner");
    }
    if(accepted)*accepted=chained;
    message="certified shipped EEex lifecycle wrapper entries and export registrations; original EEex callbacks will remain chained";
    return {image.address(profile->bodies[0].rva),image.address(profile->bodies[1].rva),image.address(profile->bodies[2].rva)};
}
}
#endif
