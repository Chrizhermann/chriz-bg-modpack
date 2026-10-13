"""Render the uninstalled source integration against the audited EEex snapshots.

Returns changed text only. Never changes a source cache, game, project build or
save. In particular, do NOT build upstream vcxproj: it has COPY_TO_GAME events.
The current native ConfigureCurrent refuses enablement; this is reviewed source
integration for subsequent completion, not an install script.
"""
from pathlib import Path


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("audited EEex source anchor missing or ambiguous: " + before[:100])
    return text.replace(before, after, 1)


def render(infinity_loader: Path, eeex: Path):
    result = {}
    path = Path("EEex-Core-Shared-Files/source/EEex.cpp")
    source = (infinity_loader / path).read_text(encoding="utf-8-sig")
    source = once(source, '#include "EEex.h"', '#include "EEex.h"\n#include "scroll_runtime/eeex_save_bridge.h"')
    source = once(source,
        'void CGameEffectList::Override_Unmarshal(byte* pData, uint nSize, CGameSprite* pSprite, byte version) {',
        'void CGameEffectList::Override_Unmarshal(byte* pData, uint nSize, CGameSprite* pSprite, byte version) {\n'
        '\tif (pSprite != nullptr && version == 1) CBMS_EEexBeginEffectUnmarshal(pSprite, version);')
    source = once(source,
        'CGameEffect *const pEffect = CGameEffect::DecodeEffectFromBase(pEffectBase);\n\t\t\t\tthis->AddTail(pEffect);',
        'CGameEffect *const pEffect = CGameEffect::DecodeEffectFromBase(pEffectBase);\n'
        '\t\t\t\tif (pSprite != nullptr && version == 1) CBMS_EEexEffectDecoded(pSprite, pEffect, pEffectBase);\n'
        '\t\t\t\tthis->AddTail(pEffect);')
    source = once(source,
        'exUUIDData.pSprite = pSprite;\n\tupdateUUIDLocal(pSprite, exData);',
        'exUUIDData.pSprite = pSprite;\n\tupdateUUIDLocal(pSprite, exData);\n'
        '\tCBMS_EEexAfterActorUUID(pSprite, exData.uuid);')
    result["InfinityLoader/" + str(path).replace("\\", "/")] = source

    path = Path("EEex-Core-Shared-Files/source/main.cpp")
    source = (infinity_loader / path).read_text(encoding="utf-8-sig")
    source = once(source, '#include "EEex.h"', '#include "EEex.h"\n#include "scroll_runtime/eeex_save_bridge.h"')
    source = once(source, 'static void exportPatterns() {', 'static void exportPatterns() {\n'
        '\texportPattern(TEXT("CBMS_EEexBeforeEffectMarshal"), CBMS_EEexBeforeEffectMarshal);\n'
        '\texportPattern(TEXT("CBMS_EEexAfterEffectMarshal"), CBMS_EEexAfterEffectMarshal);')
    source = once(source, '\tOpenBindingsInternal(luaState());',
        '\tOpenBindingsInternal(luaState());\n\tCBMS_EEexOpenLua(luaState());')
    result["InfinityLoader/" + str(path).replace("\\", "/")] = source

    path = Path("EEex/copy/EEex_scripts/EEex_Sprite_Patch.lua")
    source = (eeex / path).read_text(encoding="utf-8-sig")
    # V1 native Marshal at OverrideSize: RDI list, R13 output**, R12D
    # permanentOnly, ESI skipEquipped, RBX normal byte count. Existing EEex
    # shadow space and ignored-volatiles cover this extra four-argument call.
    source = once(source,
        '\t\t\t\tcontinue:\n\t\t\t\t#MAKE_SHADOW_SPACE(40)\n\t\t\t]]},\n'
        '\t\t\tEEex_GenLuaCall("EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize", {',
        '\t\t\t\tcontinue:\n\t\t\t\t#MAKE_SHADOW_SPACE(40)\n'
        '\t\t\t\tmov rcx, qword ptr ds:[#$(1)] ]], {CGameEffectList_Marshal_SavedSpritePtrMem}, [[ #ENDL\n'
        '\t\t\t\tmov rdx, rdi\n\t\t\t\tmov r8, r13\n'
        '\t\t\t\txor r9d, r9d\n\t\t\t\ttest r12d, r12d\n\t\t\t\tsetne r9b\n'
        '\t\t\t\txor eax, eax\n\t\t\t\ttest esi, esi\n\t\t\t\tsetne al\n'
        '\t\t\t\tshl eax, 1\n\t\t\t\tor r9d, eax\n'
        '\t\t\t\tcall #L(CBMS_EEexBeforeEffectMarshal)\n\t\t\t]]},\n'
        '\t\t\tEEex_GenLuaCall("EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize", {')
    source = once(source,
        '\t\t{"mov qword ptr ds:[#$(1)], 0 #ENDL", {CGameEffectList_Marshal_SavedSpritePtrMem}}',
        '\t\t{[[\n\t\t\t#MAKE_SHADOW_SPACE(8)\n'
        '\t\t\tmov qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)], rax\n'
        '\t\t\tmov edx, eax\n\t\t\tmov rcx, r13\n'
        '\t\t\tcall #L(CBMS_EEexAfterEffectMarshal)\n'
        '\t\t\tmov rax, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)]\n'
        '\t\t\t#DESTROY_SHADOW_SPACE\n'
        '\t\t\tmov qword ptr ds:[#$(1)], 0 ]], {CGameEffectList_Marshal_SavedSpritePtrMem}, [[ #ENDL\n\t\t]]}')
    # Post-call RCX/RDX/R8/R9 are native volatile registers, and this added call
    # may overwrite them. Explicitly declare that rather than relaxing RAX/RSP.
    source = once(source,
        '\t\t{"hook_integrity_watchdog_ignore_registers_0", {\n'
        '\t\t\tEEex_HookIntegrityWatchdogRegister.R10, EEex_HookIntegrityWatchdogRegister.R11\n\t\t}}},',
        '\t\t{"hook_integrity_watchdog_ignore_registers_0", {\n'
        '\t\t\tEEex_HookIntegrityWatchdogRegister.R10, EEex_HookIntegrityWatchdogRegister.R11\n\t\t}},\n'
        '\t\t{"hook_integrity_watchdog_ignore_registers_1", {\n'
        '\t\t\tEEex_HookIntegrityWatchdogRegister.RCX, EEex_HookIntegrityWatchdogRegister.RDX,\n'
        '\t\t\tEEex_HookIntegrityWatchdogRegister.R8, EEex_HookIntegrityWatchdogRegister.R9,\n'
        '\t\t\tEEex_HookIntegrityWatchdogRegister.R10, EEex_HookIntegrityWatchdogRegister.R11\n\t\t}}},')
    result["EEex/" + str(path).replace("\\", "/")] = source
    path = Path("EEex/copy/EEex_scripts/EEex_Sprite.lua")
    source = (eeex / path).read_text(encoding="utf-8-sig")
    source += '\n-- Uninstalled scroll actor-envelope integration; native enablement remains refused.\nEEex_Require("CBMS_ScrollMarshal")\n'
    result["EEex/" + str(path).replace("\\", "/")] = source
    return result
