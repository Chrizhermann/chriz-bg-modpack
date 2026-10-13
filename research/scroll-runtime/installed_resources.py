"""Read-only installed ITM/SPL/EFF graph inventory for the scroll runtime.

This resolves mechanics, not author intent. A typed cast is a candidate for the
reader rule; it is not proof that an author did not deliberately fix its level.
No resource is changed and no exception is inferred from a resref or parameter1.
"""
from dataclasses import asdict, dataclass, field
import hashlib
import struct


class ResourceError(ValueError):
    pass


# Explicit native protection-scroll family, corroborated by the installed
# resources and owning SR/SCS sources in resource-evidence.md. Values are
# semantic opcode anchors, not counts, old magnitudes, prefixes or CL values.
FIXED_FAMILIES = {
    "SCRL03": ("protection from acid", {27}),
    "SCRL04": ("protection from cold", {28}),
    "SCRL05": ("protection from electricity", {29}),
    "SCRL06": ("protection from fire", {30}),
    "SCRL07": ("protection from magic", {102}),
    "SCRL08": ("protection from poison", {101, 173}),
    "SCRL09": ("protection from undead", {100}),
    "SCRL15": ("protection from petrification", {101}),
}


def protection_anchor(name, mechanic, anchors):
    """Opcode101 protects its parameter2 opcode, not every condition."""
    opcode = mechanic["opcode"]
    if opcode not in anchors:
        return False
    if opcode == 101 and name in ("SCRL08", "SCRL15"):
        return mechanic["parameter2"] == {"SCRL08": 25, "SCRL15": 134}[name]
    return True


def checked(data, offset, length, label):
    if offset < 0 or length < 0 or offset > len(data) or length > len(data) - offset:
        raise ResourceError(f"{label}: indexed block outside resource")
    return data[offset:offset + length]


def word(data, offset):
    return struct.unpack("<H", checked(data, offset, 2, "word"))[0]


def dword(data, offset):
    return struct.unpack("<I", checked(data, offset, 4, "dword"))[0]


def resref(data):
    value = data.split(b"\0", 1)[0]
    # Do not decode unrelated effect bytes as resrefs; some opcodes use that
    # field as binary data. Only dispatch/learning opcodes reach this function.
    if not value or len(value) > 8 or any(c < 33 or c > 126 or c in b"/\\:" for c in value):
        raise ResourceError("dispatcher has empty/invalid resource reference")
    return value.decode("ascii").upper()


@dataclass(frozen=True)
class Effect:
    opcode: int
    parameter1: int
    parameter2: int
    resource: bytes
    index: int
    extra_resources: tuple = ()


@dataclass(frozen=True)
class Ability:
    index: int
    kind: int
    minimum_level: int
    effects: tuple


@dataclass(frozen=True)
class Resource:
    name: str
    extension: str
    sha256: str
    kind: int
    effects: tuple
    abilities: tuple


def parse(name, extension, data):
    """Declared indexes govern traversal, including reordered/padded blocks."""
    extension = extension.upper()
    digest = hashlib.sha256(data).hexdigest()
    if extension == "EFF":
        checked(data, 0, 0x110, name + ".EFF V2")
        # Bytes8..15 are the embedded CGameEffectBase version field. Vanilla
        # SPLESEAR has zeroes there; the external file signature is bytes0..7.
        if data[:8] != b"EFF V2.0":
            raise ResourceError(f"{name}.EFF: unsupported effect format")
        effect = Effect(dword(data, 0x10), dword(data, 0x1C), dword(data, 0x20), data[0x30:0x38], 0,
                        (data[0x70:0x78], data[0x78:0x80]))
        return Resource(name, extension, digest, -1, (effect,), ())
    if extension not in ("ITM", "SPL"):
        raise ResourceError("unsupported resource extension")
    checked(data, 0, 0x72, name + "." + extension)
    if data[:8] != extension.encode() + b" V1  ":
        raise ResourceError(f"{name}.{extension}: unsupported resource format")
    ao, ac, fo = dword(data, 0x64), word(data, 0x68), dword(data, 0x6A)
    stride = 56 if extension == "ITM" else 40
    checked(data, ao, ac * stride, name + " abilities")
    if ac and ao < 0x72:
        raise ResourceError(f"{name}: abilities overlap file header")

    def effects(first, count):
        if count:
            start, end = fo + first * 48, fo + (first + count) * 48
            checked(data, start, end - start, name + " effects")
            if start < 0x72 or (ac and start < ao + ac * stride and end > ao):
                raise ResourceError(f"{name}: effects overlap header/abilities")
        return tuple(Effect(word(data, fo + i * 48), dword(data, fo + i * 48 + 4),
                            dword(data, fo + i * 48 + 8), data[fo + i * 48 + 20:fo + i * 48 + 28], i)
                     for i in range(first, first + count))

    global_effects = effects(word(data, 0x6E), word(data, 0x70))
    abilities = []
    for i in range(ac):
        a = ao + i * stride
        abilities.append(Ability(i, word(data, a), word(data, a + 16) if extension == "SPL" else 0,
                                 effects(word(data, a + 32), word(data, a + 30))))
    return Resource(name, extension, digest, word(data, 0x1C), global_effects, tuple(abilities))


@dataclass
class AbilityReport:
    item: str
    ability: int
    classification: str = "unresolved"
    spells: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    learned: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    resources: dict = field(default_factory=dict)
    mechanics: list = field(default_factory=list)
    exception: str | None = None
    # No runtime enable flag: fixed author/provider intent needs separate proof.
    def as_dict(self):
        return asdict(self)


class Inventory:
    """`load(name, extension)` must return the effective installed bytes.

    All SPL ability headers are visited (the original native selector remains
    responsible for choosing one). Repeated edges retain their graph record,
    including native repeating spell chains; each resource is expanded once.
    Budgets constrain hostile or pathological
    graphs rather than requiring reference-install counts/order.
    """
    def __init__(self, load, *, max_nodes=4096, max_depth=64):
        if max_nodes < 1 or max_depth < 1:
            raise ValueError("resource traversal budgets must be positive")
        self.load, self.max_nodes, self.max_depth = load, max_nodes, max_depth
        self.cache = {}

    def get(self, name, extension):
        key = (name.upper(), extension.upper())
        if key not in self.cache:
            self.cache[key] = parse(*key, self.load(*key))
        return self.cache[key]

    def item(self, name):
        root = self.get(name, "ITM")
        if root.kind != 11:
            return []  # Ordinary item casting is outside this feature.
        result = []
        for ability in root.abilities:
            if ability.kind != 3:
                continue
            report = AbilityReport(root.name, ability.index)
            report.resources[root.name + ".ITM"] = root.sha256
            visited = set()
            saw_dispatch = False

            def visit(target, extension, path):
                key = (target, extension)
                if key in path:
                    report.diagnostics.append("native repeating edge (already inspected): " +
                                              " -> ".join(n + "." + e for n, e in (*path, key)))
                if key in visited:
                    return
                if len(path) >= self.max_depth:
                    raise ResourceError(f"{target}.{extension}: dispatch depth exceeds {self.max_depth}")
                if len(visited) >= self.max_nodes:
                    raise ResourceError(f"{target}.{extension}: graph exceeds {self.max_nodes} resources")
                resource = self.get(target, extension)
                visited.add(key)
                report.resources[target + "." + extension] = resource.sha256
                if extension == "SPL":
                    if resource.kind not in (0, 1, 2, 3, 4, 5):
                        raise ResourceError(f"{target}.SPL: unknown installed spell type {resource.kind}")
                    report.spells[target] = {"installed_type": resource.kind,
                                             "policy": {1: "arcane", 2: "divine"}.get(resource.kind, "native_untyped"),
                                             "ability_levels": [a.minimum_level for a in resource.abilities]}
                examine(resource.effects, target + "." + extension + ":global", (*path, key))
                for child_ability in resource.abilities:
                    examine(child_ability.effects, target + f".{extension}:ability{child_ability.index}", (*path, key))

            def examine(effects, owner, path):
                nonlocal saw_dispatch
                for effect in effects:
                    op = effect.opcode
                    report.mechanics.append({"owner": owner, "index": effect.index, "opcode": op,
                                             "parameter1": effect.parameter1, "parameter2": effect.parameter2})
                    if op == 147:
                        report.learned.append(resref(effect.resource))
                    elif op in (146, 148, 177, 232, 272, 326):
                        if op in (146, 148) and effect.parameter2 not in (0, 1, 2):
                            raise ResourceError(f"{owner}: opcode{op} unsupported mode {effect.parameter2}")
                        extension = "EFF" if op in (177, 272) else "SPL"
                        references = (effect.resource, *effect.extra_resources) if op == 232 else (effect.resource,)
                        for reference in references:
                            if op == 232 and not reference.split(b"\0", 1)[0]:
                                continue  # Native contingent spell slots may be empty.
                            target = resref(reference)
                            report.edges.append({"owner": owner, "index": effect.index, "opcode": op,
                                             "parameter1": effect.parameter1, "parameter2": effect.parameter2,
                                             "target": target + "." + extension})
                            saw_dispatch = True
                            visit(target, extension, path)

            try:
                examine(ability.effects, root.name + f".ITM:ability{ability.index}", ())
                if report.learned:
                    report.classification = "mixed_learning_cast" if saw_dispatch else "learning"
                    if saw_dispatch:
                        report.diagnostics.append("learning and casting share an ability; preserve until attribution is resolved")
                elif any(s["policy"] in ("arcane", "divine") for s in report.spells.values()):
                    report.classification = "typed_cast_candidate"
                else:
                    report.classification = "native_only"
                fixed = FIXED_FAMILIES.get(root.name)
                if fixed and not report.learned:
                    family, anchors = fixed
                    if any(protection_anchor(root.name, e, anchors) for e in report.mechanics):
                        report.classification = "native_exception"
                        report.exception = family
                    else:
                        report.classification = "unresolved"
                        report.diagnostics.append(f"known {family} scroll lacks its protection mechanic; provider review required")
            except (ResourceError, FileNotFoundError, KeyError) as error:
                report.diagnostics.append(str(error))
            result.append(report)
        return result
