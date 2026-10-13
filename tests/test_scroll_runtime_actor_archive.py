"""Real compiled archive ABI over allocated native-layout list/effect fixtures.

The filter/order oracle is separately exercised using both actual executable
Marshal bodies in test_scroll_runtime_effect_marshal.py. No game is loaded.
"""
import ctypes as C
import struct

import pytest

from test_scroll_runtime_native import native_api, native_scroll_build  # noqa: F401


def allocated(data):
    return C.create_string_buffer(data, len(data))


def native_list(timings):
    effects, nodes = [], []
    for i, timing in enumerate(timings):
        effect = bytearray(0x110)
        effect[8:16] = b"EFF V2.0"
        struct.pack_into("<I", effect, 0x24, timing)
        struct.pack_into("<I", effect, 0xC8, 12)
        struct.pack_into("<I", effect, 0x10, 146 + i)
        effects.append(allocated(bytes(effect)))
        nodes.append(allocated(bytes(0x18)))
    for i, node in enumerate(nodes):
        C.c_uint64.from_buffer(node, 0).value = C.addressof(nodes[i + 1]) if i + 1 < len(nodes) else 0
        C.c_uint64.from_buffer(node, 0x10).value = C.addressof(effects[i])
    linked = allocated(bytes(0x20))
    C.c_uint64.from_buffer(linked, 8).value = C.addressof(nodes[0]) if nodes else 0
    C.c_uint32.from_buffer(linked, 0x18).value = len(nodes)
    return linked, nodes, effects


def runtime_fixture(native_api):
    api, resolve_type, report_type = native_api
    calls, errors = [], []
    @resolve_type
    def resolve(reader, generation, spell, kind, output, _):
        calls.append((reader, generation, spell, kind))
        output.contents.count = 1
        output.contents.level[0] = 24
        output.contents.active[0] = 1
        return 1
    @report_type
    def report(message, _):
        errors.append(message.decode())
    runtime = api.CBMS_Create(resolve, report, None)
    assert runtime
    return api, runtime, resolve, report, calls, errors


@pytest.mark.parametrize("permanent,skip", [(0, 0), (0, 1), (1, 0), (1, 1)])
@pytest.mark.parametrize("reverse", [False, True])
def test_actor_archive_actual_list_filter_decode_association(native_api, permanent, skip, reverse):
    api, runtime, resolve, report, calls, errors = runtime_fixture(native_api)
    timings = [2, 9, 0] if not reverse else [0, 9, 2]
    linked, nodes, effects = native_list(timings)
    original = [bytes(effect) for effect in effects]
    assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
    uuid = 0xFEDCBA9876543210  # must not pass through a Lua double
    assert api.CBMS_ActorUUID(runtime, 0x1000, uuid) == 1
    use = C.c_uint64()
    assert api.CBMS_ItemBegin(runtime, 0x1000, b"SCROLL", 3, 0, C.byref(use)) == 1
    for i, effect in enumerate(effects):
        assert api.CBMS_Construct(runtime, 1, C.addressof(effect)) == 1
        assert api.CBMS_ItemChild(runtime, use, C.addressof(effect), i) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    assert api.CBMS_PrepareEffectExport(runtime, 0x1000, C.addressof(linked), 1, permanent, skip) == 1
    payload = api.CBMS_EffectExportText(runtime, 0x1000)
    assert payload.startswith(b"CBMSFX01:") and b"\0" not in payload
    included = [i for i, value in enumerate(timings) if (not permanent or value == 9) and (not skip or value != 2)]
    wire = b"".join(original[i][8:] for i in included)
    # Real EEex extra actor records follow the normal native record prefix.
    output = allocated(wire + b"X-BIV1.0" + bytes(256))
    assert api.CBMS_ValidateEffectExport(runtime, 0x1000, output, len(output)) == 1
    assert original == [bytes(effect) for effect in effects]
    for effect in effects:
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert api.CBMS_Destruct(runtime, 0, 0x1000) == 1
    assert api.CBMS_Construct(runtime, 0, 0x3000) == 1  # effect recipient, not reader
    assert api.CBMS_ActorUUID(runtime, 0x3000, 777) == 1
    assert api.CBMS_BeginEffectImport(runtime, 0x3000) == 1
    assert api.CBMS_Quiescent(runtime) == 0
    # Metadata may precede normal records; finish waits for all native decodes.
    assert api.CBMS_StageEffectImportText(runtime, 0x3000, payload, len(payload)) == 1
    decoded = []
    for i in included:
        effect, raw = allocated(original[i]), allocated(original[i][8:])
        decoded.append(effect)
        assert api.CBMS_ObserveEffectDecoded(runtime, 0x3000, C.addressof(effect), raw) == 1
    assert api.CBMS_FinishEffectImport(runtime, 0x3000) == 1
    frame, level = C.c_uint64(), C.c_uint32(91)
    for effect in decoded:
        assert api.CBMS_BeginCast(runtime, 1, C.addressof(effect), 0, 0xD000, b"SPELL", 0, 3, 4, 1, 2, C.byref(frame)) == 1
        assert api.CBMS_Select(runtime, frame, 0, 0xD000, C.byref(level)) == -1
        assert b"pending" in api.CBMS_LastError(runtime)
        assert level.value == 91 and calls == []
        assert api.CBMS_EndCast(runtime, frame) == 1
    assert api.CBMS_Construct(runtime, 0, 0x2000) == 1
    assert api.CBMS_ActorUUID(runtime, 0x2000, uuid) == 1
    for effect in decoded:
        assert api.CBMS_BeginCast(runtime, 1, C.addressof(effect), 0, 0xD000, b"SPELL", 0, 3, 4, 1, 2, C.byref(frame)) == 1
        assert api.CBMS_Select(runtime, frame, 0, 0xD000, C.byref(level)) == 1 and level.value == 12
        assert api.CBMS_EndCast(runtime, frame) == 1
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert all(call[0] == 0x2000 for call in calls)
    assert api.CBMS_Quiescent(runtime) == 1
    assert api.CBMS_Destroy(runtime) == 1


def test_native_archive_refusal_retains_pending_until_explicit_abort(native_api):
    api, runtime, resolve, report, calls, errors = runtime_fixture(native_api)
    assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
    linked, nodes, effects = native_list([9])
    assert api.CBMS_PrepareEffectExport(runtime, 0x1000, C.addressof(linked), 1, 0, 0) == 1
    assert api.CBMS_EffectExportText(runtime, 0x1000) == b""  # ordinary actor needs no envelope
    corrupt = allocated(bytes(264))
    assert api.CBMS_ValidateEffectExport(runtime, 0x1000, corrupt, len(corrupt)) == -1
    assert api.CBMS_Quiescent(runtime) == 0
    assert api.CBMS_Destroy(runtime) == -1
    assert api.CBMS_AbortEffectExport(runtime, 0x1000) == 1
    assert api.CBMS_BeginEffectImport(runtime, 0x1000) == 1
    unknown = b"CBMSFX99:012345"
    assert api.CBMS_StageEffectImportText(runtime, 0x1000, unknown, len(unknown)) == -1
    assert unknown == b"CBMSFX99:012345"  # caller must retain the actual actor envelope
    assert api.CBMS_FinishEffectImport(runtime, 0x1000) == -1
    assert api.CBMS_Quiescent(runtime) == 0
    assert api.CBMS_AbortEffectImport(runtime, 0x1000) == 1
    assert api.CBMS_Quiescent(runtime) == 1
    assert api.CBMS_Destroy(runtime) == 1


@pytest.mark.parametrize("damage", ["count", "cycle", "null", "version"])
def test_native_archive_list_refuses_malformed_structure(native_api, damage):
    api, runtime, resolve, report, calls, errors = runtime_fixture(native_api)
    assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
    linked, nodes, effects = native_list([9, 0])
    if damage == "count":
        C.c_uint32.from_buffer(linked, 0x18).value = 1
    if damage == "cycle":
        C.c_uint64.from_buffer(nodes[0], 0).value = C.addressof(nodes[0])
    if damage == "null":
        C.c_uint64.from_buffer(nodes[0], 0x10).value = 0
    assert api.CBMS_PrepareEffectExport(runtime, 0x1000, C.addressof(linked), 0 if damage == "version" else 1, 0, 0) == -1
    assert api.CBMS_Quiescent(runtime) == 1
    assert api.CBMS_Destroy(runtime) == 1
