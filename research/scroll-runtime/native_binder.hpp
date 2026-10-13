// Read-only Windows mapped-image certification. Never patches/loads/executes a
// game image. Bind only while the host has excluded module unload/code mutation.
#pragma once
#include "native_api.h"
#include <algorithm>
#include <array>
#include <climits>
#include <cstring>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include "binder_profiles.hpp"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")

namespace cbm::scroll::binding {
class Image {
    std::uintptr_t base_;
    void bounds(std::size_t offset, std::size_t size) const {
        if (!size || offset > UINTPTR_MAX - base_ || size > UINTPTR_MAX - (base_ + offset))
            throw std::runtime_error("mapped-image address overflow or empty range");
    }
public:
    explicit Image(std::uintptr_t base) : base_(base) {
        if (!base || base % 0x1000) throw std::runtime_error("module base is null or not page aligned");
    }
    std::uintptr_t address(std::size_t rva) const { bounds(rva, 1); return base_ + rva; }
    void region(std::size_t offset, std::size_t size, bool readable, bool executable = false) const {
        bounds(offset, size);
        auto cursor = base_ + offset;
        const auto end = cursor + size;
        while (cursor < end) {
            MEMORY_BASIC_INFORMATION info{};
            if (VirtualQuery(reinterpret_cast<void*>(cursor), &info, sizeof info) != sizeof info ||
                reinterpret_cast<std::uintptr_t>(info.AllocationBase) != base_ || info.Type != MEM_IMAGE)
                throw std::runtime_error("range is outside this mapped PE image");
            const auto start = reinterpret_cast<std::uintptr_t>(info.BaseAddress);
            if (info.RegionSize > UINTPTR_MAX - start || start > cursor || start + info.RegionSize <= cursor)
                throw std::runtime_error("invalid mapped-image region extent");
            if (readable) {
                const auto access = info.Protect & 0xFF;
                const bool read = access == PAGE_READONLY || access == PAGE_READWRITE || access == PAGE_WRITECOPY ||
                    access == PAGE_EXECUTE_READ || access == PAGE_EXECUTE_READWRITE || access == PAGE_EXECUTE_WRITECOPY;
                const bool execute = access == PAGE_EXECUTE_READ || access == PAGE_EXECUTE_READWRITE || access == PAGE_EXECUTE_WRITECOPY;
                if (info.State != MEM_COMMIT || (info.Protect & (PAGE_GUARD | PAGE_NOACCESS)) || !read || (executable && !execute))
                    throw std::runtime_error(executable ? "native code page is not committed, readable and executable" : "PE range is not committed and readable");
            }
            cursor = (std::min)(end, start + info.RegionSize);
        }
    }
    std::vector<unsigned char> read(std::size_t offset, std::size_t size, bool code = false) const {
        region(offset, size, true, code);
        std::vector<unsigned char> output(size);
        SIZE_T copied{};
        // Does not fault the host if a mapping disappears between VirtualQuery
        // and this read. Lifetime/code-mutation exclusion remains a host duty.
        if (!ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<void*>(base_ + offset), output.data(), size, &copied) || copied != size)
            throw std::runtime_error("mapped PE changed or became unreadable during certification");
        return output;
    }
    template<class T> T object(std::size_t offset) const {
        auto bytes = read(offset, sizeof(T)); T output;
        std::memcpy(&output, bytes.data(), sizeof output); return output;
    }
};

inline std::array<unsigned char, 32> sha256(const std::vector<unsigned char>& bytes) {
    BCRYPT_ALG_HANDLE algorithm{};
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0)
        throw std::runtime_error("Windows SHA-256 provider unavailable");
    struct Close { BCRYPT_ALG_HANDLE value; ~Close() { BCryptCloseAlgorithmProvider(value, 0); } } close{algorithm};
    std::array<unsigned char, 32> digest{};
    if (bytes.size() > ULONG_MAX || BCryptHash(algorithm, nullptr, 0,
            const_cast<unsigned char*>(bytes.data()), static_cast<ULONG>(bytes.size()), digest.data(), static_cast<ULONG>(digest.size())) < 0)
        throw std::runtime_error("Windows SHA-256 certification failed");
    return digest;
}

inline CBMS_NativeFunctions bind(std::uintptr_t module, std::string& detail) {
    static_assert(sizeof(void*) == 8, "audited native provider requires x64");
    Image image(module);
    const auto dos = image.object<IMAGE_DOS_HEADER>(0);
    if (dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < static_cast<LONG>(sizeof dos) || dos.e_lfanew > 0x100000)
        throw std::runtime_error("invalid or out-of-range DOS/PE header");
    const auto nt = static_cast<std::size_t>(dos.e_lfanew);
    if (image.object<DWORD>(nt) != IMAGE_NT_SIGNATURE) throw std::runtime_error("missing PE signature");
    const auto file = image.object<IMAGE_FILE_HEADER>(nt + sizeof(DWORD));
    if (file.Machine != IMAGE_FILE_MACHINE_AMD64 || !(file.Characteristics & IMAGE_FILE_EXECUTABLE_IMAGE) ||
        (file.Characteristics & IMAGE_FILE_DLL) || file.SizeOfOptionalHeader < sizeof(IMAGE_OPTIONAL_HEADER64))
        throw std::runtime_error("unsupported native ABI: expected AMD64 executable PE32+");
    if (!file.NumberOfSections || file.NumberOfSections > 96) throw std::runtime_error("invalid PE section count");
    const auto optional_offset = nt + sizeof(DWORD) + sizeof(file);
    const auto optional = image.object<IMAGE_OPTIONAL_HEADER64>(optional_offset);
    if (optional.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC || optional.SectionAlignment < 0x1000 ||
        (optional.SectionAlignment & (optional.SectionAlignment - 1)) || !optional.SizeOfImage ||
        optional.SizeOfImage % optional.SectionAlignment || optional.SizeOfHeaders > optional.SizeOfImage)
        throw std::runtime_error("invalid PE32+ image size/alignment");
    const auto table = optional_offset + file.SizeOfOptionalHeader;
    if (table + std::size_t(file.NumberOfSections) * sizeof(IMAGE_SECTION_HEADER) > optional.SizeOfHeaders)
        throw std::runtime_error("section table exceeds mapped PE headers");
    image.region(0, optional.SizeOfImage, false);
    std::vector<IMAGE_SECTION_HEADER> sections;
    for (unsigned index = 0; index < file.NumberOfSections; ++index) {
        auto section = image.object<IMAGE_SECTION_HEADER>(table + index * sizeof(IMAGE_SECTION_HEADER));
        const auto size = (std::max)(section.Misc.VirtualSize, section.SizeOfRawData);
        if (!size || section.VirtualAddress < optional.SizeOfHeaders || section.VirtualAddress % optional.SectionAlignment ||
            section.VirtualAddress > optional.SizeOfImage || size > optional.SizeOfImage - section.VirtualAddress)
            throw std::runtime_error("PE section lies outside the declared image");
        for (const auto& prior : sections) {
            const auto prior_size = (std::max)(prior.Misc.VirtualSize, prior.SizeOfRawData);
            if (section.VirtualAddress < prior.VirtualAddress + prior_size && prior.VirtualAddress < section.VirtualAddress + size)
                throw std::runtime_error("overlapping PE sections");
        }
        sections.push_back(section);
    }
    const Profile* profile = nullptr;
    for (const auto& candidate : profiles) {
        if (candidate.timestamp == file.TimeDateStamp && candidate.image_size == optional.SizeOfImage && candidate.entry == optional.AddressOfEntryPoint) {
            if (profile) throw std::runtime_error("ambiguous audited native profile");
            profile = &candidate;
        }
    }
    if (!profile) throw std::runtime_error("unsupported executable build: no audited 2.6.6.0/2.7.3.0 native ABI profile");
    auto executable_section = [&](unsigned rva, unsigned size) {
        return std::any_of(sections.begin(), sections.end(), [&](const auto& section) {
            const auto extent = (std::max)(section.Misc.VirtualSize, section.SizeOfRawData);
            return rva >= section.VirtualAddress && rva - section.VirtualAddress <= extent && size <= extent - (rva - section.VirtualAddress) &&
                (section.Characteristics & (IMAGE_SCN_MEM_READ | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_CNT_CODE)) ==
                    (IMAGE_SCN_MEM_READ | IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_CNT_CODE);
        });
    };
    if (!executable_section(optional.AddressOfEntryPoint, 1)) throw std::runtime_error("entry point is outside an executable code section");
    for (std::size_t index = 0; index < profile->count; ++index) {
        const auto& signature = profile->signatures[index];
        if (!executable_section(signature.rva, signature.size))
            throw std::runtime_error(std::string(signature.name) + ": audited body is outside an executable code section");
        std::array<unsigned char, 32> digest;
        try { digest = sha256(image.read(signature.rva, signature.size, true)); }
        catch (const std::exception& error) { throw std::runtime_error(std::string(signature.name) + ": " + error.what()); }
        if (!std::equal(digest.begin(), digest.end(), signature.sha))
            throw std::runtime_error(std::string(signature.name) + ": native instruction signature differs; another patch/build requires an ABI audit");
    }
    // No output is exposed until every body, its in-body branch tables and the
    // mapped boundary/architecture checks pass. RVA rebasing handles ASLR.
    auto pointer = [&](std::size_t index) { return image.address(profile->signatures[index].rva); };
    CBMS_NativeFunctions functions{
        reinterpret_cast<decltype(CBMS_NativeFunctions::lookup)>(pointer(0)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::active_inactive)>(pointer(1)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::class_level)>(pointer(2)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::maximum_level)>(pointer(3)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::mage)>(pointer(4)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::priest)>(pointer(5)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::caster_type)>(pointer(6)),
        reinterpret_cast<decltype(CBMS_NativeFunctions::caster_level)>(pointer(7))};
    detail = std::string("certified native provider ") + profile->version + "; host must retain module lifetime and exclude later code changes";
    return functions;
}
} // namespace cbm::scroll::binding
#endif
