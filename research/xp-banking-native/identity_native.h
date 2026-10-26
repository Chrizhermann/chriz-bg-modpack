// UNINSTALLED research bridge. Loading this DLL installs no hooks.
#pragma once
#include <cstdint>
#include <cstddef>
#ifdef _WIN32
#define CBMI_API extern "C" __declspec(dllexport)
#else
#define CBMI_API extern "C"
#endif

enum CBMI_Reason : unsigned {
    CBMI_WORLD, CBMI_SAVE, CBMI_CHR_EXPORT, CBMI_CHR_IMPORT,
    CBMI_MAGICAL_CLONE, CBMI_PREVIEW, CBMI_OTHER_COPY
};
// Copy and raw CRE Marshal are five-argument Win64 methods. CharacterExport
// and CharacterImport are four-argument methods; register/stack arguments are
// forwarded unchanged. The two lifetime methods are actual EEex native hooks,
// reached by BOTH sprite constructors and the destructor.
enum CBMI_Slot { CBMI_COPY, CBMI_MARSHAL, CBMI_EXPORT, CBMI_IMPORT,
                 CBMI_CONSTRUCT, CBMI_DESTRUCT, CBMI_SLOT_COUNT };
struct CBMI_Config {
    uint64_t abi;
    uintptr_t originals[CBMI_SLOT_COUNT];
    uintptr_t lua_tolstring, lua_pushstring, lua_pushboolean;
    uintptr_t strip_uuid, no_uuid;
};
struct CBMI_View {
    CBMI_Reason birth, current;
    uint64_t incarnation;
    bool serializing, eligible;
    char owner_token[33];
};

CBMI_API int CBMI_Configure(const CBMI_Config*);
CBMI_API int CBMI_Query(const void* sprite, CBMI_View*);
CBMI_API int CBMI_LuaQuery(void* L);
CBMI_API void* CBMI_Copy(void*, int, int, int, int);
CBMI_API uintptr_t CBMI_Marshal(void*, void*, void*, void*, unsigned char);
CBMI_API uintptr_t CBMI_CharacterExport(void*, int, void*, int);
CBMI_API int CBMI_CharacterImport(void*, void*, void*, unsigned char);
CBMI_API void CBMI_Construct(void*);
CBMI_API void CBMI_Destruct(void*);
// Observational only: callers must not infer an atomic reset/save transaction
// from this guard. No native XP or saved metadata is changed by this module.
CBMI_API int CBMI_CanMutate(const void* sprite, uint64_t incarnation);
// The game's own code (a fallback where the bank could not take an XP change,
// or a change the bank passed on unowned) replaced this lifetime's XP word.
// Same-DLL, host thread only; a new lifetime starts without it. CBMI_LuaQuery
// reports it as its eighth value; CBMI_LuaAckReplaced(address, incarnation)
// clears it once the bank matches.
void CBMI_NoteReplaced(const void* sprite);
CBMI_API int CBMI_LuaAckReplaced(void* L);
// Whether the lifetime CBMI_Query reported as this incarnation is still the
// actor's: 1 it is; -1 it provably ended (destroyed, or constructed again, on
// the host thread since); 0 unknown: another thread constructed or destroyed an
// actor at this address (or at more addresses than the bounded record holds),
// which proves nothing ended, nor that it goes on. Another thread's event at
// another address leaves 1. Any such event makes CBMI_Query fail for the rest of
// the process. Same-DLL, host thread only.
int CBMI_Lifetime(const void* sprite, uint64_t incarnation);
