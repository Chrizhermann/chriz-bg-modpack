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


def native_effect(timing, opcode):
    effect = bytearray(0x110)
    effect[8:16] = b"EFF V2.0"
    struct.pack_into("<I", effect, 0x24, timing)
    struct.pack_into("<I", effect, 0xC8, 12)
    struct.pack_into("<I", effect, 0x10, opcode)
    return allocated(bytes(effect))


def linked_list(effects):
    """Pinned CTypedPtrList layout over these live effect objects."""
    nodes = [allocated(bytes(0x18)) for _ in effects]
    for i, node in enumerate(nodes):
        C.c_uint64.from_buffer(node, 0).value = C.addressof(nodes[i + 1]) if i + 1 < len(nodes) else 0
        C.c_uint64.from_buffer(node, 0x10).value = C.addressof(effects[i])
    linked = allocated(bytes(0x20))
    C.c_uint64.from_buffer(linked, 8).value = C.addressof(nodes[0]) if nodes else 0
    C.c_uint32.from_buffer(linked, 0x18).value = len(nodes)
    return linked, nodes


def native_list(timings):
    effects = [native_effect(timing, 146 + i) for i, timing in enumerate(timings)]
    linked, nodes = linked_list(effects)
    return linked, nodes, effects


ROW = 264
CONTEXT = struct.Struct("<QQ8sIIIBI")  # origin, reader UUID, item, ability, root, depth, has level, level


def decode_envelope(text):
    """Rows of a CBMSFX01 actor envelope as [wire, context fields or None]."""
    assert text.startswith(b"CBMSFX01:")
    data = bytes.fromhex(text[9:].decode())
    (count,), cursor, rows = struct.unpack_from("<I", data), 4, []
    for _ in range(count):
        wire, owned = data[cursor:cursor + ROW], data[cursor + ROW]
        cursor += ROW + 1
        context = None
        if owned:
            context = list(CONTEXT.unpack_from(data, cursor))
            cursor += CONTEXT.size
        rows.append([wire, context])
    assert cursor == len(data)
    return rows


def encode_envelope(rows):
    data = bytearray(struct.pack("<I", len(rows)))
    for wire, context in rows:
        data += wire + bytes([context is not None])
        if context is not None:
            data += CONTEXT.pack(*context)
    return b"CBMSFX01:" + data.hex().upper().encode()


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


def finish(api, runtime, actor):
    """(status, reason): 1 restored, 2 outdated envelope dropped, -1 error."""
    reason = C.create_string_buffer(256)
    status = api.CBMS_FinishEffectImport(runtime, actor, reason, len(reason))
    return status, reason.value.decode()


def export(api, runtime, actor, effects):
    """Native V1 save of this actor's live effects: envelope text and records."""
    linked, nodes = linked_list(effects)
    assert api.CBMS_PrepareEffectExport(runtime, actor, C.addressof(linked), 1, 0, 0) == 1
    text = api.CBMS_EffectExportText(runtime, actor)
    records = [bytes(effect)[8:] for effect in effects]
    output = allocated(b"".join(records))
    assert api.CBMS_ValidateEffectExport(runtime, actor, output, len(output)) == 1
    return text, records


def read_scroll(api, runtime, reader, effects, ability=1):
    """These new effects come from a scroll this reader used."""
    use = C.c_uint64()
    assert api.CBMS_ItemBegin(runtime, reader, b"SCROLL", ability, 0, C.byref(use)) == 1
    for i, effect in enumerate(effects):
        assert api.CBMS_Construct(runtime, 1, C.addressof(effect)) == 1
        assert api.CBMS_ItemChild(runtime, use, C.addressof(effect), i) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1


def saved_actor(api, runtime, reader, uuid, timings):
    """An actor saved after reading a scroll whose effects it keeps."""
    assert api.CBMS_ActorObserved(runtime, reader, uuid) == 1
    linked, nodes, effects = native_list(timings)
    read_scroll(api, runtime, reader, effects)
    text, records = export(api, runtime, reader, effects)
    assert text.startswith(b"CBMSFX01:")
    for effect in effects:
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert api.CBMS_Destruct(runtime, 0, reader) == 1
    return text, records


def load(api, runtime, actor, uuid, records, text):
    """One actor's native decode: every record, its envelope, UUID, finish."""
    assert api.CBMS_ActorObserved(runtime, actor, 0) == 1
    assert api.CBMS_BeginEffectImport(runtime, actor) == 1
    decoded = []
    for wire in records:
        effect, raw = allocated(b"EFF V2.0" + wire), allocated(wire)
        decoded.append(effect)
        assert api.CBMS_ObserveEffectDecoded(runtime, actor, C.addressof(effect), raw) == 1
    if text:
        assert api.CBMS_StageEffectImportText(runtime, actor, text, len(text)) == 1
    assert api.CBMS_ActorObserved(runtime, actor, uuid) == 1
    status, reason = finish(api, runtime, actor)
    return status, reason, decoded


def selected(api, runtime, effect):
    """A typed cast from this effect: (1, reader level) owned, (0, 90) native."""
    frame, level = C.c_uint64(), C.c_uint32(90)
    assert api.CBMS_BeginCast(runtime, 1, C.addressof(effect), 0, 0xD000, b"SPELL", 0, 3, 4, 1, 2, C.byref(frame)) == 1
    status = api.CBMS_Select(runtime, frame, 0, 0xD000, C.byref(level))
    assert api.CBMS_EndCast(runtime, frame) == 1
    return status, level.value


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("permanent,skip", [(0, 0), (0, 1), (1, 0), (1, 1)])
@pytest.mark.parametrize("reverse", [False, True])
def test_actor_archive_actual_list_filter_decode_association(native_api, permanent, skip, reverse, pending):
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
    assert finish(api, runtime, 0x3000) == (1, "")
    frame, level = C.c_uint64(), C.c_uint32(91)
    if pending:
        # The original reader is not loaded yet. The cast is refused with a
        # report, which disables every override, also after the reader loads.
        assert api.CBMS_BeginCast(runtime, 1, C.addressof(decoded[0]), 0, 0xD000, b"SPELL", 0, 3, 4, 1, 2, C.byref(frame)) == 1
        assert api.CBMS_Select(runtime, frame, 0, 0xD000, C.byref(level)) == -1
        assert b"pending" in api.CBMS_LastError(runtime)
        assert level.value == 91 and calls == [] and api.CBMS_OverridesDisabled(runtime) == 1
        assert api.CBMS_EndCast(runtime, frame) == 1
    assert api.CBMS_Construct(runtime, 0, 0x2000) == 1
    assert api.CBMS_ActorUUID(runtime, 0x2000, uuid) == 1
    for effect in decoded:
        assert api.CBMS_BeginCast(runtime, 1, C.addressof(effect), 0, 0xD000, b"SPELL", 0, 3, 4, 1, 2, C.byref(frame)) == 1
        status = api.CBMS_Select(runtime, frame, 0, 0xD000, C.byref(level))
        assert (status, level.value) == ((0, 91) if pending else (1, 12))
        assert api.CBMS_EndCast(runtime, frame) == 1
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert all(call[0] == 0x2000 for call in calls) and (calls == []) == pending
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
    assert finish(api, runtime, 0x1000)[0] == -1
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


OUTDATED = {
    "added": "saved effect record count mismatch (saved 3, loaded 4)",
    "removed": "saved effect record count mismatch (saved 3, loaded 2)",
    "bytes": "saved effect record identity mismatch (record 2 of 3, byte 0x20)",
}


def outdated(records, change):
    """This actor's records after a process with overrides off kept its
    envelope unparsed, the records changed, and that process saved again."""
    records = list(records)
    if change == "added":
        records.append(bytes(native_effect(0, 300))[8:])  # e.g. a potion
    if change == "removed":
        records.pop()  # e.g. an expired effect
    if change == "bytes":
        records[1] = records[1][:0x20] + bytes([records[1][0x20] ^ 1]) + records[1][0x21:]
    return records


def unload(api, runtime, actor, effects):
    """The engine ends every object's lifetime before the next load."""
    for effect in effects:
        assert api.CBMS_DestructObserved(runtime, 1, C.addressof(effect)) == 1
    assert api.CBMS_DestructObserved(runtime, 0, actor) == 1


@pytest.mark.parametrize("change", sorted(OUTDATED))
def test_outdated_envelope_is_dropped_for_its_actor_only(native_api, change):
    api, runtime, resolve, report, calls, errors = runtime_fixture(native_api)
    stale_text, stale_records = saved_actor(api, runtime, 0x1000, 0x1111, [9, 0, 0])
    valid_text, valid_records = saved_actor(api, runtime, 0x2000, 0x2222, [9, 0])
    status, reason, dropped = load(api, runtime, 0x3000, 0x1111, outdated(stale_records, change), stale_text)
    assert (status, reason) == (2, OUTDATED[change])
    status, reason, kept = load(api, runtime, 0x4000, 0x2222, valid_records, valid_text)
    assert (status, reason) == (1, "")
    # Nothing is turned off: no report, no latch, no error text.
    assert errors == [] and api.CBMS_OverridesDisabled(runtime) == 0 and api.CBMS_LastError(runtime) == b""
    # The dropped actor's records keep their own levels but no saved ancestry.
    # The other actor keeps its saved scroll ancestry and its reader.
    assert [selected(api, runtime, effect) for effect in dropped] == [(0, 90)] * len(dropped)
    assert [selected(api, runtime, effect) for effect in kept] == [(1, 12)] * len(kept)
    assert {call[0] for call in calls} == {0x4000}
    # Its next save carries nothing stale: no envelope at all...
    assert export(api, runtime, 0x3000, dropped)[0] == b""
    # ...until a new scroll, which uses the reader's level and is saved alone.
    fresh = native_effect(0, 400)
    read_scroll(api, runtime, 0x3000, [fresh])
    assert selected(api, runtime, fresh) == (1, 12) and calls[-1][0] == 0x3000
    text, records = export(api, runtime, 0x3000, dropped + [fresh])
    rows = decode_envelope(text)
    assert [wire for wire, _ in rows] == records
    assert [context is not None for _, context in rows] == [False] * len(dropped) + [True]
    assert rows[-1][1][1] == 0x1111  # its own reader
    for effect in dropped + [fresh] + kept:
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert api.CBMS_Quiescent(runtime) == 1 and errors == []
    assert api.CBMS_Destroy(runtime) == 1


def test_outdated_drop_repeats_identically_and_the_next_save_ends_it(native_api):
    api, runtime, resolve, report, calls, errors = runtime_fixture(native_api)
    stale_text, stale_records = saved_actor(api, runtime, 0x1000, 0x1111, [9, 0, 0])
    valid_text, valid_records = saved_actor(api, runtime, 0x2000, 0x2222, [9, 0])
    loaded = outdated(stale_records, "added")
    # The same outdated save, loaded again and again: the same actor drops
    # with the same reason, the other restores, and nothing accumulates.
    for _ in range(3):
        status, reason, dropped = load(api, runtime, 0x3000, 0x1111, loaded, stale_text)
        assert (status, reason) == (2, OUTDATED["added"])
        status, reason, kept = load(api, runtime, 0x4000, 0x2222, valid_records, valid_text)
        assert (status, reason) == (1, "")
        assert [selected(api, runtime, effect) for effect in dropped + kept] == [(0, 90)] * 4 + [(1, 12)] * 2
        fresh = native_effect(0, 400)
        read_scroll(api, runtime, 0x3000, [fresh])
        resaved, records = export(api, runtime, 0x3000, dropped + [fresh])
        unload(api, runtime, 0x3000, dropped + [fresh])
        unload(api, runtime, 0x4000, kept)
        assert api.CBMS_Quiescent(runtime) == 1
    assert errors == [] and api.CBMS_OverridesDisabled(runtime) == 0
    # The save written after the drop holds no stale data: its reloads drop
    # nothing, only the new scroll keeps its saved ancestry.
    for _ in range(2):
        status, reason, again = load(api, runtime, 0x5000, 0x1111, records, resaved)
        assert (status, reason) == (1, "")
        assert [selected(api, runtime, effect) for effect in again] == [(0, 90)] * 4 + [(1, 12)]
        assert calls[-1][0] == 0x5000
        unload(api, runtime, 0x5000, again)
    assert errors == [] and api.CBMS_Quiescent(runtime) == 1
    assert api.CBMS_Destroy(runtime) == 1


def damaged_rows(text, damage):
    rows = decode_envelope(text)
    if damage == "scalar":
        rows[0][1][6:8] = [1, 13]  # saved level 13 for a record at level 12
    if damage == "ancestry":
        rows[0][1][1] = 0  # no original-reader UUID
    if damage == "origins":
        rows[1][1][3] += 1  # same origin, another ability
    return encode_envelope(rows)


DAMAGE = {
    "scalar": "saved effect scalar mismatch",
    "ancestry": "invalid saved effect ancestry",
    "origins": "conflicting saved scroll origin definitions",
    "lifetime": "decoded effect acquired ancestry before import",
    "version": "unknown/malformed effect envelope; retain original actor data",
    "hex": "invalid effect envelope hex",
    "truncated": "truncated effect envelope",
    "trailing": "trailing bytes in effect envelope",
    "duplicate": "duplicate actor effect envelope",
}


@pytest.mark.parametrize("damage", sorted(DAMAGE))
def test_damaged_envelope_still_turns_every_override_off(native_api, damage):
    api, runtime, resolve, report, calls, errors = runtime_fixture(native_api)
    text, records = saved_actor(api, runtime, 0x1000, 0x1111, [9, 0, 0])
    valid_text, valid_records = saved_actor(api, runtime, 0x2000, 0x2222, [9, 0])
    staged = {"version": b"CBMSFX02:" + text[9:], "hex": text[:-2] + b"ZZ", "truncated": text[:-2],
              "trailing": text + b"00"}.get(damage, text)
    if damage in ("scalar", "ancestry", "origins"):
        staged = damaged_rows(text, damage)
    assert api.CBMS_ActorObserved(runtime, 0x3000, 0) == 1
    assert api.CBMS_BeginEffectImport(runtime, 0x3000) == 1
    decoded = []
    # The records changed too: damage is never taken for an outdated envelope.
    for wire in outdated(records, "added"):
        effect, raw = allocated(b"EFF V2.0" + wire), allocated(wire)
        decoded.append(effect)
        assert api.CBMS_ObserveEffectDecoded(runtime, 0x3000, C.addressof(effect), raw) == 1
    if damage == "lifetime":
        assert api.CBMS_ActorObserved(runtime, 0x7000, 0x7777) == 1
        use = C.c_uint64()
        assert api.CBMS_ItemBegin(runtime, 0x7000, b"SCROLL", 1, 0, C.byref(use)) == 1
        assert api.CBMS_ItemChild(runtime, use, C.addressof(decoded[0]), 0) == 1
        assert api.CBMS_ItemEnd(runtime, use) == 1
    if damage == "duplicate":
        assert api.CBMS_StageEffectImportText(runtime, 0x3000, text, len(text)) == 1
    stage = api.CBMS_StageEffectImportText(runtime, 0x3000, staged, len(staged))
    assert stage == (1 if damage in ("scalar", "ancestry", "origins", "lifetime") else -1)
    if stage == 1:
        assert api.CBMS_ActorObserved(runtime, 0x3000, 0x1111) == 1
        assert finish(api, runtime, 0x3000)[0] == -1
    assert errors == [DAMAGE[damage]] and api.CBMS_LastError(runtime) == DAMAGE[damage].encode()
    assert api.CBMS_OverridesDisabled(runtime) == 1
    # Everything is off, as before: a valid envelope loaded afterwards stays native.
    status, reason, kept = load(api, runtime, 0x4000, 0x2222, valid_records, valid_text)
    assert (status, reason) == (1, "")
    assert [selected(api, runtime, effect) for effect in kept] == [(0, 90)] * len(kept)
    # The refused load stays pending until its host cancels it.
    assert finish(api, runtime, 0x3000)[0] == -1 and api.CBMS_Quiescent(runtime) == 0
    assert api.CBMS_AbortEffectImport(runtime, 0x3000) == 1
    for effect in decoded + kept:
        assert api.CBMS_DestructObserved(runtime, 1, C.addressof(effect)) == 1
    assert api.CBMS_Quiescent(runtime) == 1 and api.CBMS_Destroy(runtime) == 1
