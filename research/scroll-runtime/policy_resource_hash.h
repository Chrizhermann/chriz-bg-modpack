#pragma once
#include <cstddef>
#if defined(_WIN32)
#define CBMS_HASH_API extern "C" __declspec(dllexport)
#else
#define CBMS_HASH_API extern "C"
#endif
// Hash exactly length bytes, including embedded NULs and trailing resource data.
// The caller owns the demanded native buffer for the duration of this call.
CBMS_HASH_API int CBMS_PolicyHashBytes(const void* data, std::size_t length, char* hex65) noexcept;
