/* Source extension for the pinned EEex actor marshal boundaries. Uninstalled. */
#pragma once
#include "native_api.h"
struct lua_State;
#ifdef __cplusplus
extern "C" {
#endif
/* No process/module loading or detours. The caller owns runtime lifetime and
 * must have installed every required carrier hook before attaching. Current
 * legacy argument-free entry refuses because it has no verified policy. The
 * completed startup transaction attaches through CBMS_EEexAttachRuntime. */
CBMS_EXPORT int CBMS_EEexConfigureCurrent(void);
/* Completed startup transaction only, before any actor is loaded. */
int CBMS_EEexAttachRuntime(CBMS_Runtime*);
CBMS_EXPORT const char* CBMS_EEexBridgeError(void);
CBMS_EXPORT int CBMS_EEexBridgeHealthy(void);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT int CBMS_EEexAttachForTest(CBMS_Runtime*);
#endif
/* flags bit0=permanentOnly, bit1=skipEquipped; both normalized native bools.
 * Called in V1 OverrideSize before the existing Lua exporter. */
CBMS_EXPORT void CBMS_EEexBeforeEffectMarshal(void* actor, void* list, void** output, uint32_t flags);
/* Called immediately after native Marshal returns, preserving its RAX size. */
CBMS_EXPORT void CBMS_EEexAfterEffectMarshal(void* actor, uint32_t native_size);
CBMS_EXPORT void CBMS_EEexBeginEffectUnmarshal(void* actor, uint32_t version);
CBMS_EXPORT void CBMS_EEexEffectDecoded(void* actor, void* effect, const void* raw);
/* Called after EEex registers the real actor UUID, before loaded listeners. */
CBMS_EXPORT void CBMS_EEexAfterActorUUID(void* actor, uint64_t uuid);
CBMS_EXPORT void CBMS_EEexLiveEffectCopied(void* source,void* destination);
CBMS_EXPORT void CBMS_EEexEffectDestroyed(void* effect);
CBMS_EXPORT void CBMS_EEexActorDestroyed(void* actor);
/* An unsuccessful native operation must actually be cancelled by its owner
 * before this cleanup. It is not a way to continue a partially valid load. */
CBMS_EXPORT int CBMS_EEexCancelledActorIO(void* actor);
CBMS_EXPORT int CBMS_EEexDetachQuiescent(void);
CBMS_EXPORT const char* CBMS_EEexExportText(void* actor);
CBMS_EXPORT int CBMS_EEexStageText(void* actor, const char* text, uint32_t length);
CBMS_EXPORT int CBMS_EEexImportFinished(void* actor);
/* After a finished import only: why that actor's outdated envelope was dropped
 * for it alone (it no longer matched the actor's records), otherwise null. */
CBMS_EXPORT const char* CBMS_EEexImportDropped(void* actor);
CBMS_EXPORT void CBMS_EEexRejectEnvelope(const char* reason);
/* Actual InfinityLoader Lua-provider / tolua binding registration. */
void CBMS_EEexOpenLua(lua_State*);
#ifdef __cplusplus
}
#endif
