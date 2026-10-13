# Effective scroll resource hashes

The exporter inventories complete effective resource bytes. Runtime verification
must use the engine registry and demand buffer so KEY/BIF and override selection
have the same owner as actual casts. It must not hash only an override path,
header, or calculated effect range.

Pinned source: EEex `a6d21abe44e20509f5d0259ccc6c7e7f9d12b285`, InfinityLoader
`817925caab3eb9cf600cfaf38853da8d30c28247`, retained read-only under
`C:/tmp/scroll-hook-research-20261009`.

- `EEex/copy/EEex_scripts/EEex_Resource.lua:91` fetches from the engine resource
  registry by type and name. At line129 the convenience Demand helper calls the
  CRes method, then intentionally adds8 for EFF before returning CGameEffectBase.
  The policy adapter therefore uses `EEex_Resource_Fetch` and `res:Demand()`.
- The generated LuaBindings-v2.7.3.0 `EEexLua_generated.cpp:80001` binding wraps
  the actual `CRes::Demand()` return as `UnmappedUserType`. Lines79865 and79889
  expose raw pData and unsigned nSize. The hash binding consumes that actual
  returned userdata type and the complete nSize; no pointer is reconstructed
  from a saved string or numeric actor identifier.
- Native 2.6.6 CRes::Demand at RVA3f6390 and 2.7.3 at RVA3f6d50 check the loaded
  byte at51 and return raw pData at40, including their already-loaded path.
  The generated CRes header declares nSize after pData (offset48). The adapter
  reads the typed nSize property, not a hardcoded field offset.
- `policy_resource_hash.cpp` uses Windows CNG SHA256 and hashes all bytes,
  including NULs, external EFF signatures, padding and trailing data. It exports
  only the resulting hex digest after the complete operation succeeds.

Validation: compiled CNG output agrees with Python SHA256 on empty/binary,
large multi-block, reordered ITM, multi-ability SPL and EFF-with-tail samples.
Lua51/LuaJIT checks exercise the real adapter with explicit resource/hash boundary
fixtures, missing resources, changed digests, failed demand and signed provider
size normalization. They do not execute the engine resource loader or render a
game. The native Lua unit is built against the real loader headers/imports when
included by the independent DLL host; activation remains the host's responsibility.
