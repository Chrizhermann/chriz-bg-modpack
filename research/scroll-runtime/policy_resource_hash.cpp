#include "policy_resource_hash.h"
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <limits>
#include <vector>
#pragma comment(lib, "bcrypt.lib")

namespace {
struct Algorithm {
    BCRYPT_ALG_HANDLE value{};
    ~Algorithm() { if (value) BCryptCloseAlgorithmProvider(value, 0); }
};
struct Hash {
    BCRYPT_HASH_HANDLE value{};
    ~Hash() { if (value) BCryptDestroyHash(value); }
};
bool ok(NTSTATUS status) noexcept { return status >= 0; }
}
int CBMS_PolicyHashBytes(const void* data, std::size_t length, char* hex65) noexcept {
    if (!hex65) return 0;
    hex65[0] = '\0';
    if (!data && length) return 0;
    try {
        Algorithm algorithm;
        if (!ok(BCryptOpenAlgorithmProvider(&algorithm.value, BCRYPT_SHA256_ALGORITHM, nullptr, 0))) return 0;
        DWORD object_length{}, copied{}, digest_length{};
        if (!ok(BCryptGetProperty(algorithm.value, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_length),
            sizeof(object_length), &copied, 0)) || copied != sizeof(object_length) || !object_length) return 0;
        if (!ok(BCryptGetProperty(algorithm.value, BCRYPT_HASH_LENGTH, reinterpret_cast<PUCHAR>(&digest_length),
            sizeof(digest_length), &copied, 0)) || copied != sizeof(digest_length) || digest_length != 32) return 0;
        std::vector<UCHAR> storage(object_length);
        Hash hash;
        if (!ok(BCryptCreateHash(algorithm.value, &hash.value, storage.data(), object_length, nullptr, 0, 0))) return 0;
        auto* cursor = static_cast<const UCHAR*>(data);
        while (length) {
            const auto count = static_cast<ULONG>(std::min(length, std::size_t(std::numeric_limits<ULONG>::max())));
            if (!ok(BCryptHashData(hash.value, const_cast<PUCHAR>(cursor), count, 0))) return 0;
            cursor += count; length -= count;
        }
        std::array<UCHAR, 32> digest{};
        if (!ok(BCryptFinishHash(hash.value, digest.data(), static_cast<ULONG>(digest.size()), 0))) return 0;
        constexpr char digits[] = "0123456789abcdef";
        for (std::size_t i = 0; i < digest.size(); ++i) {
            hex65[i * 2] = digits[digest[i] >> 4]; hex65[i * 2 + 1] = digits[digest[i] & 15];
        }
        hex65[64] = '\0';
        return 1;
    } catch (...) { return 0; }
}
