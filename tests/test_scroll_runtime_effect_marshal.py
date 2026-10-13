"""Actual native serializer proves order/filtering, including identical records."""
import importlib.util
import struct
import sys

import pytest
from test_scroll_runtime_detours import action_image, SOURCE

spec = importlib.util.spec_from_file_location("effect_marshal_native", SOURCE / "effect_marshal_native.py")
native = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = native
spec.loader.exec_module(native)


@pytest.mark.parametrize("timings", [[], [2], [9, 2, 0, 9, 4], [4, 9, 2, 9, 0]])
@pytest.mark.parametrize("permanent_only,skip_equipped", [(False, False), (False, True), (True, False), (True, True)])
def test_native_v1_serialized_ordinal_is_after_real_filters(action_image, timings, permanent_only, skip_equipped):
    pe, _, names = action_image
    records = []
    for timing in timings:
        # Repeated timing9 records are intentionally byte-identical: fingerprints
        # cannot distinguish their original per-effect contexts, native ordinals can.
        record = bytearray((i*17 + 31) % 256 for i in range(0x108))
        struct.pack_into("<I", record, 0x1C, timing)
        records.append(bytes(record))
    expected_indices = [i for i, timing in enumerate(timings)
                        if (not permanent_only or timing == 9) and (not skip_equipped or timing != 2)]
    result = native.marshal(pe, names, records, permanent_only=permanent_only, skip_equipped=skip_equipped)
    assert result["length"] == len(expected_indices)*0x108
    assert result["buffer"] == b"".join(records[i] for i in expected_indices)
    assert [entry["ordinal"] for entry in result["emitted"]] == list(range(len(expected_indices)))
    assert [entry["effect"] for entry in result["emitted"]] == [result["source_effect_base"]+i*0x200 for i in expected_indices]
    assert [entry["bytes"] for entry in result["emitted"]] == [records[i] for i in expected_indices]
    assert result["allocations"] == ([result["length"]] if expected_indices else [])
