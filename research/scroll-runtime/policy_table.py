"""Deterministic installed-ability policy export. Does not change resources.

The native consumer must verify every dependency against effective installed
bytes before using this table. Full diagnostics remain in the JSON report.
This is mechanical classification; deliberately fixed author/provider intent
still needs the owning component's explicit exception, not a numeric heuristic.
"""
import hashlib
import json
import struct

MAGIC = b"CBMSPOL1"
MAX_ENTRIES = 131072
MAX_RESOURCES = 262144
# policy, reason: OrdinaryScroll=0, PreserveNative=1, Unresolved=2.
CLASSIFICATIONS = {
    "typed_cast_candidate": (0, 0),
    "learning": (1, 1),
    "native_only": (1, 2),
    "native_exception": (1, 3),
    "mixed_learning_cast": (2, 4),
    "unresolved": (2, 5),
}


def name_bytes(value):
    if not isinstance(value, str):
        raise ValueError("resource reference must be text")
    try:
        raw = value.encode("ascii").upper()
    except UnicodeEncodeError as error:
        raise ValueError("resource reference must be ASCII") from error
    if not 1 <= len(raw) <= 8 or any(c < 33 or c > 126 or c in b"/\\:" for c in raw):
        raise ValueError("invalid resource reference")
    return raw.ljust(8, b"\0")


def build(reports):
    """Return (binary table, detached JSON-ready diagnostic manifest).

    Duplicated abilities are ambiguous even if their current policy agrees;
    callers must inventory each installed item once. Shared graph dependencies
    are legal, but conflicting bytes indicate a changed inventory snapshot.
    """
    entries, dependencies, diagnostics = {}, {}, []
    for report in reports:
        data = report.as_dict() if hasattr(report, "as_dict") else report
        item = name_bytes(data["item"])
        ability = data["ability"]
        if type(ability) is not int or not 0 <= ability < 65535:
            raise ValueError("ability index is outside the ITM header count range")
        key = item, ability
        if key in entries:
            raise ValueError("duplicate installed item/ability")
        classification = data["classification"]
        if classification not in CLASSIFICATIONS:
            raise ValueError("unknown ability classification")
        policy, reason = CLASSIFICATIONS[classification]
        resources = data["resources"]
        root = item.rstrip(b"\0").decode() + ".ITM"
        normalized = {}
        for resource, digest in resources.items():
            name, separator, extension = resource.rpartition(".")
            extension = extension.upper()
            if not separator or extension not in ("ITM", "SPL", "EFF"):
                raise ValueError("unsupported dependency resource")
            dep = name_bytes(name), extension.encode().ljust(4, b"\0")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("dependency requires SHA256")
            try:
                raw_digest = bytes.fromhex(digest)
            except ValueError as error:
                raise ValueError("dependency requires SHA256") from error
            if len(raw_digest) != 32:
                raise ValueError("dependency requires SHA256")
            if dep in dependencies and dependencies[dep] != raw_digest:
                raise ValueError("conflicting installed dependency bytes")
            if dep in normalized:
                raise ValueError("duplicate dependency after resource normalization")
            dependencies[dep] = raw_digest
            normalized[dep] = raw_digest
        if (item, b"ITM\0") not in normalized:
            raise ValueError(f"missing root dependency {root}")
        entries[key] = policy, reason
        # Roundtrip creates detached, deterministic diagnostic data; callers
        # cannot later mutate an already exported report by retaining a dict.
        diagnostic = json.loads(json.dumps(data, sort_keys=True))
        diagnostic["item"] = item.rstrip(b"\0").decode()
        diagnostics.append(diagnostic)
        if len(entries) > MAX_ENTRIES or len(dependencies) > MAX_RESOURCES:
            raise ValueError("installed policy table exceeds resource budget")
    binary = bytearray(MAGIC + struct.pack("<II", len(entries), len(dependencies)))
    for (item, ability), (policy, reason) in sorted(entries.items()):
        binary.extend(struct.pack("<8sIBBH", item, ability, policy, reason, 0))
    for (name, extension), digest in sorted(dependencies.items()):
        binary.extend(name + extension + digest)
    manifest = {"format": MAGIC.decode(), "table_sha256": hashlib.sha256(binary).hexdigest(),
                "entries": len(entries), "dependencies": len(dependencies),
                "abilities": sorted(diagnostics, key=lambda d: (d["item"], d["ability"]))}
    return bytes(binary), manifest
