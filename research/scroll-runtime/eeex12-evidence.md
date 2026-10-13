# Installed EEex 1.2 decoder/lifecycle compatibility

2026-10-09. Read-only offline examination; no game or DLL entry point was
invoked. The executable/DLL files were not modified. Relocated mapping tests
use private copy-on-write pages and recheck source-file hashes on unmap.

The supported added pair is BG2EE **2.7.3.0** with the actual Combined EEex DLL:

- `%USERPROFILE%/CEBG-Tests/Combined-20260908/game/EEex.dll`
- SHA256 `adc09b72951a28fed7b56ca1eba530f54c90505a495432f97401ea3c9b19a4c9`
- PE timestamp `1786305876`, image size `1306624`, entry RVA `0xD3F80`.

This does not establish support for another EEex 1.2 binary or its 2.6 build.
The existing two 1.3.1 pairs remain supported. Decoder selection now matches
both native game and DLL timestamps, followed by the existing complete header,
span, route-target and initialized-native-pointer checks.

## Discovered registrations and bodies

Each label was located as a unique UTF16 string and traced through its actual
RIP-relative registration. These are not inferred symbol addresses.

| Boundary | Body RVA / size | Registration RVA / size |
|---|---|---|
| `CGameEffectList::Override_Unmarshal` | `0xDCB0` / `606` | `0x2B3BD` / `125` |
| `EEex::Opcode_Hook_OnCopy` | `0xD0F0` / `80` | `0x2E063` / `43` |
| `EEex::Opcode_Hook_OnDestruct` | `0xD140` / `64` | `0x2E08E` / `43` |
| `EEex::Sprite_Hook_OnDestruct` | `0xD390` / `64` | `0x2E190` / `43` |

`Override_Unmarshal` has five native runtime-function ranges, relative to
`0xDCB0`: `[0,184)`, `[184,235)`, `[235,570)`, `[570,578)`, `[578,606)`.
The full signature covers all five, including cold branches. The export's
`LEA R8` at `0x2B421` resolves exactly to `0xDCB0`.

The real V1 decoder call reads global pointer RVA **`0x1320A8`** at `0xDEB6`.
The unique `CGameEffect::DecodeEffectFromBase` label registration at `0xB0AEF`
calls resolver `0xB8020`; its store at `0xB8094` initializes that same pointer.
The live binder requires it to equal the certified game's native decoder entry.
An offline mapping must simulate that initialization and the existing native
Unmarshal jump before the binder can succeed; an uninitialized DLL is rejected.

## Comparison and ABI evidence

All four full primary bodies are byte-identical to the previous 2.7 / EEex
1.3.1 bodies after normalizing only RIP displacements and external direct-call
displacements. Constants, native branches, object offsets, parameter handling
and stack instructions remain identical. This comparison does not declare
every external dependency in the two DLLs identical; the original EEex body
and its own callbacks are still chained, rather than replaced.

The three lifecycle entry prefixes are exactly the existing trampoline recipe:
copy `4c8bdc49895310`; both destruction entries `4c8bdc49894b08`.
`eeex12-proof.py` executes each actual 1.2 body directly and through that same
trampoline in Unicorn. All three pairs preserve the native argument order,
nonvolatile state, stack and native callback arguments. Only the shared EEex
closure executor is substituted. The effect-copy closure's native captured
argument order remains destination then source; the exported wrapper ABI is
still `(source, destination)`, as its installed Lua patch states.

The V1 unmarshalling branch still takes `(list, rawData, byteSize, sprite,
versionByte)`, walks 264-byte effect records, dispatches X-BIV envelope records
to the original EEex reader, and invokes `DecodeEffectFromBase(rawRecord)` then
native `AddTail` for ordinary records. Existing UUID effect detection and field
offsets are unchanged. No custom decoder or lifetime policy was introduced.

Installed `EEex_scripts/EEex_Sprite.lua` function text matches the cached 1.3.1
source exactly for `EEex_Sprite_AddMarshalHandlers`,
`EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal`, and
`EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled`. The latter still invokes
UUID callbacks before loaded listeners. This is a narrow source comparison,
not a new proof of every UUID registration/native game-load path.

## Checks and artifacts

- `eeex12-audit.py`: pinned-file hash, unique label references, complete native
  disassembly and native unwind ranges in `eeex12-registration.*` and
  `eeex12-bodies.txt`.
- `eeex12-proof.py`: four normalized-body comparisons and three actual
  original/trampoline pairs; generated `eeex12-profiles.json` contains exact
  span hashes and native decoder pointer registration evidence.
- Both existing profile generators now reproduce all three supported pairs
  from the actual pinned files and verify each export label/function target.
- Focused decoder/lifecycle binder selection: **28 passed, 38 deselected**.
  This includes actual relocated 1.2 mapping acceptance, all its existing body,
  cold-path, registration, route/pointer/header refusals, unsupported pairing
  refusal, and existing 1.3 acceptance. No game functions were called.

No live gameplay, installation, save/load acceptance, or general support for
all EEex versions is claimed.
