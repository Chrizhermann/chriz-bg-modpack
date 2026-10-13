// Read-only certification of the existing EEex route, before scroll hooks.
#pragma once
#include "native_binder.hpp"
#include "decode_profiles.hpp"

#ifdef _WIN32
namespace cbm::scroll::binding {
// EEex_JITAt assembles `jmp CGameEffectList::Override_Unmarshal` over the
// native entry. A near target is E9 rel32 (5 bytes). A far target is
// `jmp qword ptr [rip+disp32]` whose 8-byte target sits in asmjit's aligned
// address table right after the instruction, so disp32 is that padding (0-7)
// and the jump spans 14-21 bytes. Observed live on 2.7.3.0 with EEex 1.2:
// FF 25 02 00 00 00, two padding bytes, the target: 16 bytes, so EEex's jump
// overwrites the first two bytes after the native 14-byte head.
struct ExistingJump { std::uintptr_t target; std::size_t length; };
inline constexpr std::size_t existing_jump_window = 22;
inline ExistingJump existing_eeex_jump(const std::vector<unsigned char>& code, std::uintptr_t entry) {
    if (code.size() < existing_jump_window) throw std::runtime_error("native Unmarshal entry window is incomplete");
    if (code[0] == 0xE9) {
        std::int32_t displacement{}; std::memcpy(&displacement, code.data()+1, 4);
        return {static_cast<std::uintptr_t>(static_cast<std::int64_t>(entry+5) + displacement), 5};
    }
    std::uint32_t padding{}; std::memcpy(&padding, code.data()+2, 4);
    if (code[0] == 0xFF && code[1] == 0x25 && padding < 8) {
        // Padding bytes are never executed; the decoded target is what counts.
        std::uintptr_t target{}; std::memcpy(&target, code.data()+6+padding, 8);
        return {target, 14 + padding};
    }
    throw std::runtime_error("native Unmarshal has no recognized existing EEex jump; do not bypass another hook");
}
inline CBMS_DecodeFunctions bind_decode(std::uintptr_t game_base, std::uintptr_t eeex_base, std::string& detail) {
    std::string reader_detail;
    (void)bind(game_base, reader_detail); // complete existing engine/header ABI checks
    Image game(game_base), eeex(eeex_base);
    const auto game_nt = game.object<IMAGE_DOS_HEADER>(0).e_lfanew;
    const auto timestamp = game.object<IMAGE_FILE_HEADER>(game_nt + 4).TimeDateStamp;
    const auto dos = eeex.object<IMAGE_DOS_HEADER>(0);
    if (dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < static_cast<LONG>(sizeof dos) || dos.e_lfanew > 0x100000)
        throw std::runtime_error("invalid EEex module DOS header");
    const auto nt = static_cast<std::size_t>(dos.e_lfanew);
    if (eeex.object<DWORD>(nt) != IMAGE_NT_SIGNATURE) throw std::runtime_error("invalid EEex PE signature");
    const auto file = eeex.object<IMAGE_FILE_HEADER>(nt + 4);
    if (file.Machine != IMAGE_FILE_MACHINE_AMD64 || !(file.Characteristics & IMAGE_FILE_DLL) ||
        !(file.Characteristics & IMAGE_FILE_EXECUTABLE_IMAGE) || file.SizeOfOptionalHeader < sizeof(IMAGE_OPTIONAL_HEADER64) ||
        !file.NumberOfSections || file.NumberOfSections > 96)
        throw std::runtime_error("EEex decoder requires a mapped AMD64 PE32+ DLL");
    const DecodeProfile* profile = nullptr;
    for (const auto& candidate : decode_profiles)
        if (candidate.game_timestamp == timestamp && candidate.eeex_timestamp == file.TimeDateStamp) {
            if (profile) throw std::runtime_error("ambiguous audited game/EEex decoder pair");
            profile = &candidate;
        }
    if (!profile) throw std::runtime_error("missing audited game/EEex decoder pair");
    const auto optional_at = nt + 4 + sizeof file;
    const auto optional = eeex.object<IMAGE_OPTIONAL_HEADER64>(optional_at);
    if (optional.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC || file.TimeDateStamp != profile->eeex_timestamp ||
        optional.SizeOfImage != profile->eeex_size || optional.AddressOfEntryPoint != profile->eeex_entry ||
        optional.SectionAlignment < 0x1000 || (optional.SectionAlignment & (optional.SectionAlignment-1)) ||
        optional.SizeOfImage % optional.SectionAlignment || optional.SizeOfHeaders > optional.SizeOfImage)
        throw std::runtime_error("unsupported EEex DLL build/header; decoder ABI review required");
    eeex.region(0, optional.SizeOfImage, false);
    const auto table = optional_at + file.SizeOfOptionalHeader;
    if (table + file.NumberOfSections * sizeof(IMAGE_SECTION_HEADER) > optional.SizeOfHeaders)
        throw std::runtime_error("EEex section table outside headers");
    std::vector<IMAGE_SECTION_HEADER> sections;
    for (unsigned i = 0; i < file.NumberOfSections; ++i) {
        auto section = eeex.object<IMAGE_SECTION_HEADER>(table + i * sizeof(IMAGE_SECTION_HEADER));
        const auto size = (std::max)(section.Misc.VirtualSize, section.SizeOfRawData);
        if (!size || section.VirtualAddress < optional.SizeOfHeaders || section.VirtualAddress % optional.SectionAlignment ||
            section.VirtualAddress > optional.SizeOfImage || size > optional.SizeOfImage-section.VirtualAddress)
            throw std::runtime_error("EEex section outside declared image");
        for (const auto& prior : sections) {
            const auto extent = (std::max)(prior.Misc.VirtualSize, prior.SizeOfRawData);
            if (section.VirtualAddress < prior.VirtualAddress + extent && prior.VirtualAddress < section.VirtualAddress + size)
                throw std::runtime_error("overlapping EEex sections");
        }
        sections.push_back(section);
    }
    const auto in_code = [&](unsigned rva, unsigned length) {
        return std::any_of(sections.begin(), sections.end(), [&](const auto& section) {
            const auto size = (std::max)(section.Misc.VirtualSize, section.SizeOfRawData);
            return rva >= section.VirtualAddress && rva-section.VirtualAddress <= size && length <= size-(rva-section.VirtualAddress) &&
                (section.Characteristics & (IMAGE_SCN_MEM_READ|IMAGE_SCN_MEM_EXECUTE|IMAGE_SCN_CNT_CODE)) ==
                    (IMAGE_SCN_MEM_READ|IMAGE_SCN_MEM_EXECUTE|IMAGE_SCN_CNT_CODE);
        });
    };
    const auto certify = [](const Image& image, const DecodeSignature& signature) {
        const auto actual = sha256(image.read(signature.rva, signature.size, true));
        if (!std::equal(actual.begin(), actual.end(), signature.sha))
            throw std::runtime_error("decoder/EEex instruction signature differs; preserve existing route and refuse installation");
    };
    for (const auto* signature : {&profile->eeex_override, &profile->eeex_registration}) {
        if (!in_code(signature->rva, signature->size)) throw std::runtime_error("EEex decoder span is not executable code");
        certify(eeex, *signature);
    }
    certify(game, profile->decoder);
    // Put back only the bytes EEex's decoded jump occupies; every other byte of
    // the audited native Unmarshal must still be its shipped original.
    const auto entry_rva = profile->unmarshal_tail.rva - 14;
    const auto entry = game.address(entry_rva);
    const auto previous = eeex.address(profile->eeex_override.rva);
    auto function = game.read(entry_rva, 14 + profile->unmarshal_tail.size, true);
    const auto jump = existing_eeex_jump(function, entry);
    std::copy(profile->unmarshal_original, profile->unmarshal_original + jump.length, function.begin());
    if (!std::equal(function.begin(), function.begin() + 14, profile->unmarshal_original))
        throw std::runtime_error("unexpected bytes beyond existing EEex jump");
    const auto tail = sha256(std::vector<unsigned char>(function.begin() + 14, function.end()));
    if (!std::equal(tail.begin(), tail.end(), profile->unmarshal_tail.sha))
        throw std::runtime_error("decoder/EEex instruction signature differs; preserve existing route and refuse installation");
    if (jump.target != previous) throw std::runtime_error("existing Unmarshal jump does not target certified EEex override");
    const auto decoder = game.address(profile->decoder.rva);
    if (profile->pointer_rva > optional.SizeOfImage - sizeof(std::uintptr_t) ||
        eeex.object<std::uintptr_t>(profile->pointer_rva) != decoder)
        throw std::runtime_error("EEex native decoder pointer is uninitialized or changed by another owner");
    detail = std::string("certified independent decoder carrier ") + profile->version +
        "; chain existing EEex target; decoder entry needs its separately audited trampoline";
    return {entry, previous, decoder};
}
}
#endif
