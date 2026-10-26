#!/usr/bin/env python3
"""Main-thread audit for Baldur's Gate II: Enhanced Edition 2.7.3.0 (static and read-only).

Claim checked: in the 2.7.3.0 engine no thread other than the game's main thread has a resolved path
to these functions (the targets):
  * CGameSprite::SetAtOffset (0x1403727d0), whose stat-44 branch writes the XP field,
  * CGameEffectXP::ApplyEffect (0x1401cb370), the opcode-104 (XP) effect,
  * the effect and AI paths into them: CGameEffectList::HandleList, CGameSprite::ProcessEffectList,
    CGameAIBase::ExecuteAction, CGameSprite::AIUpdate and CGameArea::AIUpdate,
  * the CGameSprite constructors and destructors, where EEex calls EEex::Sprite_Hook_OnConstruct and
    EEex::Sprite_Hook_OnDestruct (the hooks the XP bank's identity registry relies on).
A resolved path follows only resolved edges: direct calls, jumps, switch targets and fall-through
(and, in the main-loop chains of section C, the virtual calls matched there). Indirect calls and
jumps that stay unresolved are counted and listed as open routes, not followed, so a route through
them is not excluded. The Beamdog internet lobby (libjingle and its glue, including
DPProviderJingle::OnNicknameCollision, which reads the engine's Lua state, possibly on the lobby's
network thread) is not covered.

The listing has these sections. Every check prints [ok] or [FAIL]. The RESULT line before section F
counts the checks, repeats every failed one and lists every open route with its count. It reads PASS
only when no check failed and no route stays unresolved, FAIL when a check failed, and INCONCLUSIVE
otherwise. Exit status is 1 on FAIL and 0 otherwise: the RESULT line, not the exit status, says
whether the claim is proven.
  A  every thread or work creation site in Baldur.exe, its start routine and who starts it;
  B  forward: no non-main start routine reaches a target or any game-named function through
     resolved edges; the same holds for the resolved closure of all libjingle and glue code
     together, which covers virtual dispatch to any named libjingle or glue function; each closure's
     unresolved indirect calls/jumps are counted;
  C  reverse: no start routine is among the callers of any target in the resolved graph (up to
     their roots), no code the decoder missed refers to a target or any of those callers, a chain
     from the main loop (CChitin::Update) reaches every target, and EEex's sprite construct/destruct
     hook sites (found with the loader's own patterns) lie in the target constructors and destructor;
  D  SearchThreadMain and CNetwork::ThreadLoop are plain calls from CChitin::Update, not threads;
  E  EEex.dll: its only CreateThread starts the debug window and is reached only through the Lua
     binding OpenDebugWindow (the indirect call sites of that thread are counted, not followed); no
     EEex or loader binary binds SDL thread, timer or audio functions;
  F  the remaining uncertainties as found by the analysis (printed, not checked).

Method: Baldur.exe is decoded by recursive descent per .pdata function (unwind chains joined),
following MSVC switch tables, fall-through into adjacent chunks, and leaf functions without .pdata.
The leaf set is computed as a fixed point, so the result does not depend on decoding order.
Direct calls, jumps, switch targets and fall-through are the edges of the call graph; indirect
calls and jumps are counted but not followed. Byte scans of all code check that the decoder missed
no call, jump or address load of the thread-creation functions and of the targets and their callers.
The virtual calls in the main-loop chains of section C are matched by vtable slot against the vtable
that the class constructor installs. Function names come from EEex's function_names.db. Nothing is
executed and no file is written except --out.

Inputs (sha256 asserted):
  --exe    Baldur.exe of BG2:EE 2.7.3.0 (PE timestamp 1780012861)
  --names  EEex v1.3.1 (tag v1.3.1, commit a6d21abe44e2): EEex/loader/v2.7.3.0/bg2ee/function_names.db
  --eeex   EEex v1.3.1: EEex/loader/v2.7.3.0/EEex.dll (PE timestamp 1790553205)
  --loader-bin  optional, repeatable: other binaries of the same EEex release; sha256 printed. The command
           below passes the loader binaries a 2.7.3.0 game loads with EEex v1.3.1's default InfinityLoader.ini
           (LuaPatchMode=INTERNAL, LuaVersionInternal=5.2, so Lua52/LuaProvider.dll and not LuaJIT).
  --loader-db   optional, repeatable, later files override earlier ones: the loader's pattern files of the
           same release (InfinityLoader.db, then v2.7.3.0/pattern_dbs/v2.7.3.0.db); sha256 printed.
           Without it the hook-site check in C prints NOT CHECKED.

Run from a folder that holds the exe and an EEex v1.3.1 checkout in EEex/ (tested with Python
3.11.9, pefile 2024.8.26 and capstone 5.0.7; other library versions may change the text):
  python -I main_thread_audit.py --exe Baldur.exe \
    --names EEex/EEex/loader/v2.7.3.0/bg2ee/function_names.db \
    --eeex EEex/EEex/loader/v2.7.3.0/EEex.dll \
    --loader-bin EEex/EEex/loader/InfinityLoader.exe \
    --loader-bin EEex/EEex/loader/InfinityLoaderDLL.dll \
    --loader-bin EEex/EEex/loader/InfinityLoaderCommon.dll \
    --loader-bin EEex/EEex/loader/InfinityLoaderUtil.dll \
    --loader-bin EEex/EEex/loader/LuaBindingsCore.dll \
    --loader-bin EEex/EEex/loader/Lua52/LuaProvider.dll \
    --loader-bin EEex/EEex/loader/v2.7.3.0/LuaBindings.dll \
    --loader-db EEex/EEex/loader/InfinityLoader.db \
    --loader-db EEex/EEex/loader/v2.7.3.0/pattern_dbs/v2.7.3.0.db \
    --out main-thread-audit-2.7.3.txt
The listing goes to stdout and, with --out, to that file (UTF-8, LF line ends). It is deterministic.
"""
import argparse
import hashlib
import re
import struct
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, deque
from pathlib import Path

import capstone
import pefile

EXE_SHA256 = "B51093A49140B2B8A7C046B4652BB8E535BE24EBBC12B1D735E0B94217A14D57"
NAMES_SHA256 = "C5E957B9F63B1A945CCC837B827BAD37F209F99412D791D4A749503FC6C25823"
EEEX_SHA256 = "62E110A27BC1AE0530AFC276BB5ADF41609D133AB499BAE3456F046DEDEF0E35"

MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
RIP = re.compile(r"\[rip ([+-]) 0x([0-9a-f]+)\]")
IMM = re.compile(r"^0x([0-9a-f]+)$")
DW = re.compile(r"dword ptr \[(\w+) \+ (\w+)\*4 \+ 0x([0-9a-f]+)\]")
BY = re.compile(r"byte ptr \[(\w+) \+ (\w+) \+ 0x([0-9a-f]+)\]")
CMP = re.compile(r"^(\w+), (0x[0-9a-f]+|\d+)$")
JCC = {"je", "jne", "ja", "jae", "jb", "jbe", "jg", "jge", "jl", "jle", "js", "jns", "jo", "jno", "jp", "jnp",
       "jrcxz", "jecxz", "loop", "loope", "loopne"}
STOP = {"ret", "retf", "int3", "ud2", "hlt", "iretd", "iretq"}
REGS = {"rcx": ("rcx", "ecx", "cx", "cl"), "rdx": ("rdx", "edx", "dx", "dl"),
        "r8": ("r8", "r8d", "r8w", "r8b"), "r9": ("r9", "r9d", "r9w", "r9b")}

# Windows/CRT/STL entry points that create a thread or hand work to another thread.
CREATE_APIS = {"CreateThread", "CreateRemoteThread", "CreateRemoteThreadEx", "_beginthread", "_beginthreadex",
               "_Thrd_create", "_Thrd_start", "_Thrd_startX", "QueueUserWorkItem", "QueueUserAPC", "CreateThreadpool",
               "CreateThreadpoolWork", "SubmitThreadpoolWork", "TrySubmitThreadpoolCallback", "CreateThreadpoolTimer",
               "SetThreadpoolTimer", "CreateThreadpoolWait", "SetThreadpoolWait", "CreateThreadpoolIo",
               "StartThreadpoolIo", "BindIoCompletionCallback", "CreateTimerQueue", "CreateTimerQueueTimer",
               "ChangeTimerQueueTimer", "RegisterWaitForSingleObject", "RegisterWaitForSingleObjectEx",
               "timeSetEvent", "RtlCreateUserThread", "NtCreateThread", "NtCreateThreadEx", "NtQueueApcThread"}
# Engine (SDL/CRT) functions that start or feed a thread; a DLL could bind them by name.
SDL_BIND_NAMES = ["SDL_CreateThread", "SDL_CreateThreadWithStackSize", "SDL_AddTimer", "SDL_RemoveTimer",
                  "SDL_TimerInit", "SDL_TimerThread", "SDL_Init", "SDL_InitSubSystem", "SDL_OpenAudio",
                  "SDL_OpenAudioDevice", "SDL_PauseAudio", "SDL_PauseAudioDevice", "SDL_RunAudio", "SDL_JoystickOpen",
                  "SDL_GameControllerOpen", "SDL_HapticOpen", "SDL_HapticOpenFromJoystick", "SDL_HapticOpenFromMouse",
                  "_beginthreadex", "_beginthread"]
# Name classes (prefix match on function_names.db names).
GAME_FWD = re.compile(r"^(CGame|CInfGame|CBaldur|CScreen|CMessage|CAI|CContingency|CItem|CSpell|CProjectile|"
                      r"CRuleTables|CInfinity|CChitin|CBaldurChitin|CNetwork|DPProvider|DPPeer|XmppHandler|CLUA|"
                      r"tolua_|Infinity_|CVid|CSound|CRes|CMultiplayer|CSearch|CPath|lua_|luaL_|luaV_|luaD_)")
GAME_UNION = re.compile(r"^(CGame|CInfGame|CBaldur|CScreen|CMessage|CAI|CContingency|CItem|CSpell|CProjectile|"
                        r"CRuleTables|CInfinity|CChitin|CNetwork|CMultiplayer|CLUA|CVid|CSound|CRes|CTimerWorld|CStore|"
                        r"CSaveGame|CObList|CString|CPtrList|CFile|CDerived|CBounce|CPersistant|CSelective|CImmunit|"
                        r"CColorEffect|CWorldMap|CSequence|CVariable|CBlood|CMarker|CParticle|CWarp|CTiled|CSearch|"
                        r"CPath|DPWrapper|CSteam|Infinity_|tolua_|lua|uiInventory|SDL_|WIN_)")
GAME_LOGIC = re.compile(r"^(CGame|CInfGame|CBaldur|CScreen|CMessage|CAI|CContingency|CItem|CSpell|CProjectile|"
                        r"CRuleTables|CInfinity|CChitin|CNetwork|CMultiplayer|CLUA|CTimerWorld|CStore|CSaveGame|"
                        r"CDerived|CBounce|CPersistant|CSelective|CImmunit|CColorEffect|CWorldMap|CSequence|"
                        r"CVariable|CBlood|CMarker|CParticle|CWarp|CTiled|CSearch|CPath|Infinity_|tolua_|uiInventory)")
JINGLE = re.compile(r"^(talk_base::|cricket::|buzz::|sigslot::|XmppThread|XmppPump|XmppSocket|XmppHandler|"
                    r"DPProviderJingle|DPPeerJingle)")
LIBJINGLE = re.compile(r"^(talk_base|cricket|buzz|sigslot)::")
GLUE = {"XmppHandler", "XmppThread", "XmppPump", "XmppSocket", "DPProviderJingle", "DPPeerJingle"}
LUA_REGISTRARS = re.compile(r"^(luaopen_\w+|uiLoadFunctions)$")
MP_HANDLERS = re.compile(r"^(CBaldurMessage|CMessage)")
TRAMPOLINES = re.compile(r"^(thread_start<|RunThreadViaBeginThreadEx$)")
# Identical-code-folded bodies that carry an unrelated game name in function_names.db.
FOLDED = {0x14018fc00: ("c70100000000c3", "mov dword ptr [rcx], 0 ; ret (SDL_AtomicUnlock body)")}

TARGETS = [(0x1403727d0, "CGameSprite::SetAtOffset"), (0x1401cb370, "CGameEffectXP::ApplyEffect"),
           (0x1401e4f90, "CGameEffectList::HandleList"), (0x1403ab9d0, "CGameSprite::ProcessEffectList"),
           (0x14015d4b0, "CGameAIBase::ExecuteAction"), (0x1403447f0, "CGameSprite::AIUpdate"),
           (0x1401782a0, "CGameArea::AIUpdate"), (0x1401a3480, "CGameSprite::CGameSprite"),
           (0x140341860, "CGameSprite::CGameSprite"), (0x140343cc0, "CGameSprite::~CGameSprite"),
           (0x1401a4630, "CGameSprite::`scalar_deleting_destructor'")]
# Virtual calls used by the main-loop chains: (site, slot offset, vtable, class, callee, receiver check).
HOPS = [(0x14041cbe5, 0xe8, 0x14058dd00, "CBaldurChitin", 0x140131c10, None),
        (0x140419b40, 0x1a0, 0x1405a7b78, "CScreenWorld", 0x1402fcbb0, None),
        (0x140178cce, 0x18, 0x140598b68, "CGameSprite", 0x1403447f0, None),
        (0x1403451f3, 0x110, 0x140598b68, "CGameSprite", 0x1403a9ec0, None),
        (0x14039281c, 0x100, 0x140598b68, "CGameSprite", 0x140395ff0, None),
        (0x1401e5008, 0x18, 0x140593ce0, "CGameEffectXP", 0x1401e83d0, None),
        (0x1401e867b, 0x10, 0x140593ce0, "CGameEffectXP", 0x1401cb370, None),
        (0x1401e867b, 0x10, 0x140594838, "CGameEffectPolymorph", 0x1401bbb40, None),
        (0x14017ce4e, 0x0, 0x140598b68, "CGameSprite", 0x1401a4630, "qword ptr [rsp + 0x68]")]

LINES, FAILS, NCHECK, OPEN = [], [], [0], []


def out(s=""):
    LINES.append(s)


def check(ok, what):
    NCHECK[0] += 1
    out(("  [ok]   " if ok else "  [FAIL] ") + what)
    if not ok:
        FAILS.append(what)
    return ok


def open_route(label, n, unit):
    """Record a route the graph does not follow: n indirect calls/jumps (or call sites) that stay unresolved."""
    OPEN.append((label, n, unit))


def verdict(nchecks, fails, routes):
    """The RESULT block: PASS only when no check failed and no route stays unresolved, FAIL when a check failed,
    INCONCLUSIVE otherwise. routes: [(label, count, unit)]; a count of 0 is no open route."""
    routes = [r for r in routes if r[1] > 0]
    if fails:
        head = "RESULT: FAIL (%d checks, %d failed)" % (nchecks, len(fails))
    elif routes:
        head = ("RESULT: INCONCLUSIVE (%d checks, 0 failed; no resolved path from another thread to a target; "
                "%d route%s unresolved)" % (nchecks, len(routes), " stays" if len(routes) == 1 else "s stay"))
    else:
        head = ("RESULT: PASS (%d checks, 0 failed; no resolved path from another thread to a target; "
                "no route stays unresolved)" % nchecks)
    return [head] + ["  failed: " + f for f in fails] + ["  unresolved: %s: %d %s" % r for r in routes]


def h(v):
    return "0x%x" % v


def wrap(prefix, items, indent="      ", width=112):
    """prefix followed by the items, comma separated, wrapped at width."""
    line, first = prefix, True
    for it in items:
        if not first and len(line) + 2 + len(it) > width:
            out(line + ",")
            line = indent + it
        else:
            line += it if first else ", " + it
        first = False
    out(line)


def short_import(n):
    """KERNEL32.dll!Sleep -> Sleep; X.dll!?LuaState@SharedState@@3PEAU... -> SharedState::LuaState."""
    nm = n.split("!", 1)[1]
    if nm.startswith("?"):
        return "::".join(reversed(nm[1:].split("@@")[0].split("@")))
    return nm


def rip_target(a, sz, ops):
    m = RIP.search(ops)
    return a + sz + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1) if m else None


class Image:
    """A PE file mapped as the loader would, with imports, exports and .pdata."""

    def __init__(self, path):
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.raw).hexdigest().upper()
        pe = pefile.PE(data=self.raw, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY[d] for d in (
            "IMAGE_DIRECTORY_ENTRY_IMPORT", "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT", "IMAGE_DIRECTORY_ENTRY_EXPORT")])
        self.pe = pe
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.img = pe.get_memory_mapped_image()
        self.iat, self.import_name_rvas = {}, set()
        for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for dll in getattr(pe, attr, []) or []:
                for imp in dll.imports:
                    nm = imp.name.decode() if imp.name else "ord%d" % imp.ordinal
                    self.iat[imp.address] = dll.dll.decode() + "!" + nm
                    rva = getattr(imp, "hint_name_table_rva", None)
                    if imp.name and rva:
                        self.import_name_rvas.add(rva + 2)
        self.exports = {}
        if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                if e.name:
                    self.exports[e.name.decode()] = self.base + e.address
        exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        self.pdata = []
        for off in range(0, exc.Size, 12):
            b, e, u = struct.unpack_from("<III", self.img, exc.VirtualAddress + off)
            if b:
                self.pdata.append((b, e, u))
        self.pdata_starts = sorted(b for b, e, u in self.pdata)
        self.pdata_by_start = {b: e for b, e, u in self.pdata}
        self.exec_secs = [s for s in pe.sections if s.Characteristics & 0x20000000]
        self.data_secs = [s for s in pe.sections if not s.Characteristics & 0x20000000]

    def label(self, parent=True):
        return (self.path.parent.name + "/" + self.path.name) if parent else self.path.name

    def u64(self, va):
        return struct.unpack_from("<Q", self.img, va - self.base)[0]

    def cstr(self, va, n=128):
        r = va - self.base
        e = self.img.find(b"\0", r, r + n)
        s = self.img[r:e if e >= 0 else r]
        return s.decode("latin-1") if s and all(32 <= c < 127 for c in s) else None

    def pdata_range(self, va):
        i = bisect_right(self.pdata_starts, va - self.base) - 1
        if i >= 0:
            b = self.pdata_starts[i]
            if b <= va - self.base < self.pdata_by_start[b]:
                return self.base + b, self.base + self.pdata_by_start[b]
        return None

    def insns(self, lo, hi):
        return list(MD.disasm_lite(self.img[lo - self.base:hi - self.base], lo))

    def code_refs(self, targets):
        """Byte-pattern scan of all code (decoded or not) for references to targets: call/jmp rel32,
        call/jmp [rip], mov r64, [rip] (load) and lea r64, [rip]. Returns {target: sorted [(site, kind)]}."""
        res = {t: [] for t in targets}
        for s in self.exec_secs:
            c = s.get_data()
            va0 = self.base + s.VirtualAddress
            for m in re.finditer(rb"[\xe8\xe9]", c):
                i = m.start()
                t = va0 + i + 5 + int.from_bytes(c[i + 1:i + 5], "little", signed=True)
                if t in res and i + 5 <= len(c):
                    res[t].append((va0 + i, "call rel32" if c[i] == 0xe8 else "jmp rel32"))
            for m in re.finditer(rb"\xff[\x15\x25]", c):
                i = m.start()
                t = va0 + i + 6 + int.from_bytes(c[i + 2:i + 6], "little", signed=True)
                if t in res and i + 6 <= len(c):
                    res[t].append((va0 + i, "call [rip]" if c[i + 1] == 0x15 else "jmp [rip]"))
            for m in re.finditer(rb"[\x48\x4c][\x8b\x8d][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", c):
                i = m.start()
                t = va0 + i + 7 + int.from_bytes(c[i + 3:i + 7], "little", signed=True)
                if t in res and i + 7 <= len(c):
                    res[t].append((va0 + i, "load" if c[i + 1] == 0x8b else "lea"))
        return {t: sorted(v) for t, v in res.items()}

    def data_refs(self, targets):
        """8-aligned 64-bit values in the non-code sections that equal one of targets: {target: [where]}."""
        res = {t: [] for t in targets}
        for s in self.data_secs:
            d = s.get_data()
            for k, (v,) in enumerate(struct.iter_unpack("<Q", d[:len(d) // 8 * 8])):
                if v in res:
                    res[v].append(self.base + s.VirtualAddress + 8 * k)
        return res

    def name_hits(self, names):
        """Whole-token occurrences of names as ASCII or UTF-16 strings, ignoring import name entries."""
        blob = self.img
        hits = []
        for nm in names:
            for enc, w in ((nm.encode(), 1), (nm.encode("utf-16le"), 2)):
                i = blob.find(enc)
                while i >= 0:
                    before = blob[i - w:i] if i >= w else b""
                    after = blob[i + len(enc):i + len(enc) + w]
                    def ident(b):
                        return len(b) == w and (chr(b[0]).isalnum() or b[0] == 0x5f) and (w == 1 or b[1] == 0)
                    if not ident(before) and not ident(after) and not (w == 1 and i in self.import_name_rvas):
                        hits.append("%s (%s at %s)" % (nm, "ascii" if w == 1 else "utf-16", h(self.base + i)))
                    i = blob.find(enc, i + 1)
        return hits


class Graph:
    """Call graph of the exe: nodes are function groups (.pdata unwind-chain roots or leaf functions)."""

    def __init__(self, exe, names):
        self.exe, self.names = exe, names
        self.img, self.base = exe.img, exe.base
        text = next(s for s in exe.pe.sections if s.Name.startswith(b".text"))
        self.lo = self.base + text.VirtualAddress
        self.hi = self.lo + text.Misc_VirtualSize
        self.cov = bytearray(self.hi - self.lo)  # 1 for every byte of .text inside a decoded instruction
        img, base = self.img, self.base
        by_begin = {b: (b, e, u) for b, e, u in exe.pdata}

        def root_of(b, depth=0):
            b0, e0, u0 = by_begin[b]
            if depth > 32:
                return b
            if u0 & 1:
                pb = struct.unpack_from("<I", img, u0 & ~1)[0]
                return root_of(pb, depth + 1) if pb in by_begin else pb
            flags, count = img[u0] >> 3, img[u0 + 2]
            if flags & 0x4:
                pb = struct.unpack_from("<I", img, u0 + 4 + ((count + 1) & ~1) * 2)[0]
                return root_of(pb, depth + 1) if pb in by_begin else pb
            return b
        self.chunks = {base + b: (base + e, base + root_of(b)) for b, e, u in exe.pdata}
        self.cstarts = sorted(self.chunks)
        group_of_chunk = {s: self.chunks[s][1] for s in self.cstarts}
        members = {}
        for s in self.cstarts:
            members.setdefault(group_of_chunk[s], []).append(s)

        def owner_pdata(va):
            c = self.chunk_of(va)
            return group_of_chunk[c] if c is not None else None
        groups = {}
        for r, ms in members.items():
            info = self._decode(r, ms, owner_pdata, False)
            info["chunks"], info["kind"] = [(s, self.chunks[s][0]) for s in ms], "pdata"
            groups[r] = info
        self.n_pdata = len(groups)

        def seeds(info, refs):
            c = {t for a, t in info["calls"]} | {t for a, t, k in info["tails"] if k != "fallthrough"}
            if refs:
                c |= {t for a, t, mn, ops in info["coderefs"]}
            return {t for t in c if self.lo <= t < self.hi and self.chunk_of(t) is None}
        entries = set()
        for info in groups.values():
            entries |= seeds(info, True)
        self.ptr_slots = {}
        for s in exe.data_secs:
            r0 = s.VirtualAddress
            for r in range(r0, r0 + min(s.SizeOfRawData, s.Misc_VirtualSize) - 7, 8):
                v = struct.unpack_from("<Q", img, r)[0]
                if self.lo <= v < self.hi:
                    self.ptr_slots[base + r] = v
                    if self.chunk_of(v) is None:
                        entries.add(v)
        # Leaf functions (no .pdata): decode each one up to the next known function start, collect
        # new call/jump targets, repeat until no new start appears (order-independent fixed point).
        self.leaf_rounds = 0
        while True:
            self.leaf_rounds += 1
            leaves = {}
            for t in sorted(entries):
                def lowner(va, t=t):
                    c = self.chunk_of(va)
                    if c is not None:
                        return group_of_chunk[c]
                    return va if (va in entries and va != t) else None
                info = self._decode(t, [t], lowner, True)
                info["chunks"], info["kind"] = [], "leaf"
                leaves[t] = info
            new = set()
            for info in leaves.values():
                new |= seeds(info, False)
            new -= entries
            if not new:
                break
            entries |= new
        groups.update(leaves)
        self.groups = groups
        self.leaf_at = {}
        for r in sorted(groups):
            if groups[r]["kind"] == "leaf":
                for a in groups[r]["ranges"]:
                    self.leaf_at.setdefault(a, r)
        self.nstarts = sorted(names)
        self.callers, self.tailers, self.coderefs, self.datasites, self.iatcall = {}, {}, {}, {}, {}
        self.succ, self.rev = {}, {}
        for r in sorted(groups):
            g, edges = groups[r], set()
            for a, t in g["calls"]:
                self.callers.setdefault(t, []).append(a)
                x = self.node_of(t)
                if x is not None and x != r:
                    edges.add((x, a, "call"))
            for a, t, k in g["tails"]:
                self.tailers.setdefault(t, []).append(a)
                x = self.node_of(t)
                if x is not None and x != r:
                    edges.add((x, a, k))
            for a, t, mn, ops in g["coderefs"]:
                self.coderefs.setdefault(t, []).append(a)
            for a, t, mn, ops in g["datarefs"]:
                self.datasites.setdefault(t, []).append(a)
            for a, ops, t in g["icalls"] + g["ijmps"]:
                if t in exe.iat:
                    self.iatcall.setdefault(exe.iat[t], []).append(a)
            self.succ[r] = sorted(edges)
        for r, lst in self.succ.items():
            for x, a, k in lst:
                self.rev.setdefault(x, []).append((r, a, k))
        for lst in self.rev.values():
            lst.sort()
        self.slots_of = {}
        for slot, v in self.ptr_slots.items():
            self.slots_of.setdefault(v, []).append(slot)
        self._preds = {}

    # ---- decoding (recursive descent) ----
    def chunk_of(self, va):
        i = bisect_right(self.cstarts, va) - 1
        if i >= 0 and self.cstarts[i] <= va < self.chunks[self.cstarts[i]][0]:
            return self.cstarts[i]
        return None

    def one(self, va):
        r = va - self.base
        for x in MD.disasm_lite(self.img[r:r + 16], va, 1):
            return x
        return None

    def _switch(self, window, jmp_addr):
        t4 = t1 = bound = None
        for (a, sz, mn, ops) in reversed(window):
            m = DW.search(ops)
            if mn == "mov" and m and t4 is None:
                t4 = int(m.group(3), 16)
                continue
            m = BY.search(ops)
            if mn == "movzx" and m and t1 is None and t4 is not None:
                t1 = int(m.group(3), 16)
                continue
            m = CMP.match(ops)
            if mn == "cmp" and m and bound is None and t4 is not None:
                bound = int(m.group(2), 0)
                break
        if t4 is None:
            return None
        if bound is None or bound > 4096:
            bound = 255
        n = (max(self.img[t1:t1 + bound + 1]) + 1) if t1 is not None else bound + 1
        res = []
        for i in range(n):
            v = self.base + struct.unpack_from("<I", self.img, t4 + 4 * i)[0]
            if not (self.lo <= v < self.hi) or abs(v - jmp_addr) > 0x200000:
                break
            res.append(v)
        return res

    def _decode(self, root, entries, owner, is_leaf):
        seen, work = {}, list(entries)
        info = dict(calls=[], tails=[], icalls=[], ijmps=[], coderefs=[], datarefs=[], switches=[])
        while work:
            va, prev = work.pop(), None
            while self.lo <= va < self.hi and va not in seen:
                o = owner(va)
                if o is not None and o != root:
                    if prev is not None and prev[2] != "call":
                        info["tails"].append((prev[0], va, "fallthrough"))
                    break
                ins = self.one(va)
                if ins is None:
                    break
                a, sz, mn, ops = ins
                seen[a], prev, nxt = ins, ins, a + sz
                e = min(nxt, self.hi)
                self.cov[a - self.lo:e - self.lo] = b"\x01" * (e - a)
                tgt = rip_target(a, sz, ops)
                if mn == "call":
                    mi = IMM.match(ops)
                    if mi:
                        info["calls"].append((a, int(mi.group(1), 16)))
                    else:
                        info["icalls"].append((a, ops, tgt))
                    va = nxt
                    continue
                if mn in JCC or mn == "jmp":
                    mi = IMM.match(ops)
                    if mi:
                        t = int(mi.group(1), 16)
                        ot = owner(t)
                        if ot is None and self.chunk_of(t) is None and is_leaf:
                            work.append(t)
                        elif ot == root:
                            work.append(t)
                        else:
                            info["tails"].append((a, t, mn))
                        if mn == "jmp":
                            break
                        va = nxt
                        continue
                    if re.match(r"^r\w+$", ops):
                        win = [seen[x] for x in sorted(seen) if a - 64 <= x < a][-12:]
                        tg = self._switch(win, a)
                        if tg:
                            info["switches"].append((a, tg))
                            for t in tg:
                                if owner(t) == root or (owner(t) is None and is_leaf):
                                    work.append(t)
                                else:
                                    info["tails"].append((a, t, "switch"))
                            break
                    info["ijmps"].append((a, ops, tgt))
                    break
                if mn in STOP:
                    break
                if tgt is not None:
                    (info["coderefs"] if self.lo <= tgt < self.hi else info["datarefs"]).append((a, tgt, mn, ops))
                elif mn in ("mov", "movabs") and re.match(r"^\w+, 0x[0-9a-f]+$", ops):
                    v = int(ops.split("0x")[1], 16)
                    if self.lo <= v < self.hi:
                        info["coderefs"].append((a, v, mn, ops))
                va = nxt
        info["ninsn"], info["ranges"] = len(seen), sorted(seen)
        return info

    # ---- queries ----
    def node_of(self, va):
        c = self.chunk_of(va)
        if c is not None:
            return self.chunks[c][1]
        return va if va in self.groups else self.leaf_at.get(va)

    def name(self, va):
        if va in self.names:
            return self.names[va]
        r = self.node_of(va)
        if r is not None and r in self.names:
            return self.names[r] + "+0x%x" % (va - r)
        i = bisect_right(self.nstarts, va) - 1
        if i >= 0 and va - self.nstarts[i] < 0x4000:
            return "~" + self.names[self.nstarts[i]] + "+0x%x" % (va - self.nstarts[i])
        return "sub_%x" % va

    def fname(self, va):
        return self.name(self.node_of(va) if self.node_of(va) is not None else va)

    def closure(self, entries, extra=None, exclude=None):
        par, dq = {}, deque()
        for e in entries:
            x = self.node_of(e)
            if x is not None and x not in par:
                par[x] = (None, None, None)
                dq.append(x)
        while dq:
            s = dq.popleft()
            nb = self.succ.get(s, [])
            if extra and s in extra:
                nb = sorted(nb + extra[s])
            for x, a, k in nb:
                if x in par or (exclude is not None and exclude(x)):
                    continue
                par[x] = (s, a, k)
                dq.append(x)
        return par

    def ancestors(self, va):
        x = self.node_of(va)
        par, dq = {x: None}, deque([x])
        while dq:
            s = dq.popleft()
            for p, a, k in self.rev.get(s, []):
                if p not in par:
                    par[p] = s
                    dq.append(p)
        return par

    def path(self, par, s):
        res = []
        while s is not None:
            p, a, k = par[s]
            res.append((s, a, k))
            s = p
        return res[::-1]

    def preds(self, g):
        """Predecessors of each decoded instruction of function group g (fall-through, branches, switches)."""
        if g not in self._preds:
            info, p = self.groups[g], {}
            rset = set(info["ranges"])
            for x in info["ranges"]:
                a, sz, mn, ops = self.one(x)
                if mn not in STOP and mn != "jmp" and a + sz in rset:
                    p.setdefault(a + sz, []).append(a)
                mi = IMM.match(ops) if (mn in JCC or mn == "jmp") else None
                if mi and int(mi.group(1), 16) in rset:
                    p.setdefault(int(mi.group(1), 16), []).append(a)
            for a, tg in info["switches"]:
                for t in tg:
                    if t in rset:
                        p.setdefault(t, []).append(a)
            self._preds[g] = p
        return self._preds[g]

    def resolve(self, site, reg, limit=400):
        """Value of an argument register at a call site: the writes that reach the site on every path back
        through the function's control flow must all be the same constant. Returns (value or None, evidence)."""
        p = self.preds(self.node_of(site))
        vals, ev, seen, work = set(), [], set(), list(p.get(site, []))
        if not work:
            return None, "no predecessor"
        while work:
            x = work.pop()
            if x in seen:
                continue
            seen.add(x)
            if len(seen) > limit:
                return None, "search limit"
            a, sz, mn, ops = self.one(x)
            text = "%x: %s %s" % (a, mn, ops)
            if mn == "call":
                return None, text + " (clobbers it)"
            parts = [q.strip() for q in ops.split(",")]
            if parts[0] in REGS[reg] and mn not in ("cmp", "test", "push", "bt"):
                if parts[0] in REGS[reg][2:]:
                    return None, text + " (partial write)"
                if mn == "lea" and rip_target(a, sz, ops) is not None:
                    vals.add(rip_target(a, sz, ops))
                elif mn == "xor" and len(parts) == 2 and parts[1] == parts[0]:
                    vals.add(0)
                elif mn == "mov" and len(parts) == 2 and IMM.match(parts[1]):
                    vals.add(int(parts[1], 16))
                else:
                    return None, text
                ev.append(text)
                continue
            if not p.get(x):
                return None, "unset at the function entry"
            work.extend(p[x])
        if len(vals) != 1:
            return None, "different values: " + "; ".join(sorted(ev))
        return vals.pop(), "; ".join(sorted(set(ev)))

    def covered(self, va):
        return self.lo <= va < self.hi and self.cov[va - self.lo] == 1

    def near(self, site, before, after):
        rs = self.groups[self.node_of(site)]["ranges"]
        i = bisect_left(rs, site)
        return [self.one(x) for x in rs[max(0, i - before):i]], [self.one(x) for x in rs[i + 1:i + 1 + after]]


def one_addr(G, nm):
    addrs = sorted(va for va, n in G.names.items() if n == nm)
    if len(addrs) != 1:
        check(False, "names DB has exactly one function named %s (found %d)" % (nm, len(addrs)))
        return addrs[0] if addrs else 0
    return addrs[0]


def refs_text(G, va):
    parts = ["call from " + G.name(a) for a in sorted(G.callers.get(va, []))]
    parts += ["jump from " + G.name(a) for a in sorted(G.tailers.get(va, []))]
    parts += ["address loaded in " + G.name(a) for a in sorted(G.coderefs.get(va, []))]
    parts += ["data slot " + h(s) for s in sorted(G.slots_of.get(va, []))]
    if exported(G, va):
        parts.append("exported")
    return parts or ["none"]


def exported(G, va):
    return G.exe.exports.get(G.name(va)) == va


def only_exported(G, va, seen=None):
    """True when the exe's own code never uses va: its address is never taken, and it is either an export that
    nothing calls or only called by functions for which the same holds. A function that nothing references at
    all and that is not exported counts as used: the PE header or an exception table can enter it."""
    seen = set() if seen is None else seen
    if va in seen:
        return True
    seen.add(va)
    refs = G.callers.get(va, []) + G.tailers.get(va, [])
    if G.coderefs.get(va) or G.slots_of.get(va) or (not refs and not exported(G, va)):
        return False
    return all(only_exported(G, G.node_of(a), seen) for a in refs)


def folded_ok(G, g):
    if g not in FOLDED:
        return False
    hexbytes = FOLDED[g][0]
    return G.img[g - G.base:g - G.base + len(hexbytes) // 2].hex() == hexbytes


# ---------------------------------------------------------------- section A
def section_a(G):
    exe = G.exe
    out("A. Thread and work creation in Baldur.exe")
    imported = sorted(n for n in exe.iat.values() if n.split("!", 1)[1] in CREATE_APIS)
    out("  imported thread/work-creation APIs: " + (", ".join(imported) or "none"))
    check(imported == ["KERNEL32.dll!CreateThread"],
          "A1 the only thread/work-creation import is KERNEL32.dll!CreateThread (no thread pool, "
          "QueueUserWorkItem, timer queue, RegisterWait, CreateRemoteThread, APC, timeSetEvent or _Thrd_*)")
    dlls = sorted({n.split("!")[0] for n in exe.iat.values()})
    wrap("  imported DLLs: ", dlls)
    stl = sorted({n for n in G.names.values() if re.search(r"std::thread|std::jthread|std::async|_Thrd_|Concurrency::", n)})
    check(not stl and not any(re.match(r"(?i)(msvcp|concrt)", d) for d in dlls),
          "A1 no std::thread, std::async, _Thrd_* or Concurrency function in the names DB and no MSVCP/ConcRT import")
    # thread-pool functions looked up by name at run time (GetProcAddress)
    occ = []
    for api in sorted(CREATE_APIS):
        needle = api.encode() + b"\0"
        i = G.img.find(needle)
        while i >= 0:
            if (i == 0 or not (chr(G.img[i - 1]).isalnum() or G.img[i - 1] == 0x5f)) and i not in exe.import_name_rvas:
                occ.append((api, G.base + i))
            i = G.img.find(needle, i + 1)
    ptrs = exe.data_refs({va for api, va in occ})
    users = {(api, va): sorted({G.node_of(s) for s in G.datasites.get(va, [])}) for api, va in occ}
    lookup_fns = sorted({u for us in users.values() for u in us})
    out("  names of thread/work-creation APIs as strings (outside the import table):")
    for api, va in occ:
        out("    %s at %s, used by %s%s" % (api, h(va), ", ".join(G.name(u) for u in users[(api, va)]) or "no code",
                                         "; pointed to from data at " + ", ".join(map(h, ptrs[va])) if ptrs[va] else ""))
    # pair each GetProcAddress result with its name: lea rdx, <name> ... call GetProcAddress ... mov [rip + slot], rax
    stores = {}
    for u in lookup_fns:
        pending = called = None
        for x in G.groups[u]["ranges"]:
            a, sz, mn, ops = G.one(x)
            t = rip_target(a, sz, ops)
            if mn == "lea" and ops.startswith("rdx,") and t is not None and exe.cstr(t):
                pending = exe.cstr(t)
            elif mn == "call":
                called = pending if exe.iat.get(t, "").endswith("!GetProcAddress") else None
                pending = None
            elif mn == "mov" and t is not None and ops.startswith("qword ptr [rip") and ops.endswith(", rax") and called:
                stores[called], called = t, None
    looked = sorted({api for api, va in occ if users[(api, va)]})
    slot_refs = exe.code_refs({stores[n] for n in stores})
    read_by = {}
    for n, s in stores.items():
        r = {G.node_of(x) for x in G.datasites.get(s, [])} | {G.node_of(x) for x, k in slot_refs[s]}
        read_by[n] = sorted(G.name(x) if x is not None else "undecoded code" for x in r - set(lookup_fns))
    out("  %s stores %d GetProcAddress results; the only ones any code reads (byte scan of all code included): %s" % (
        "/".join(sorted({G.name(u) for u in lookup_fns})) or "nothing", len(stores),
        ", ".join("%s (by %s)" % (n, ", ".join(read_by[n])) for n in sorted(stores) if read_by[n]) or "none"))
    for api in looked:
        out("    %s: result stored at %s, read by %s" % (api, h(stores[api]) if api in stores else "?",
                                                         ", ".join(read_by.get(api, ["?"])) or "nothing"))
    check(all(G.name(u) == "initialize_pointers" for u in lookup_fns) and not any(ptrs.values())
          and all(api in stores and not read_by[api] for api in looked),
          "A2 thread-pool names are used only by the C++ runtime's initialize_pointers, and no code reads the "
          "function pointers it stores for them")
    # direct uses of the creation functions; a byte scan of all code must find no use the decoder missed
    ct, wo, wi = "KERNEL32.dll!CreateThread", "WINMM.dll!waveOutOpen", "WINMM.dll!waveInOpen"
    slot_of = {n: a for a, n in exe.iat.items()}
    bt = one_addr(G, "_beginthreadex")
    sdl = sorted(v for v, n in G.names.items() if n == "SDL_CreateThread")
    scan = exe.code_refs({slot_of[ct], slot_of[wo], slot_of[wi], bt} | set(sdl))

    def missed(target, decoded):  # a scan hit may sit one byte after a decoded call that has a REX prefix
        return [x for x in scan[target] if not any(d <= x[0] <= d + 1 for d in decoded)]
    starts = {}  # start routine -> list of (api, creator site, creator)

    def record(api, site, reg):
        val, how = G.resolve(site, reg)
        creator = G.fname(site)
        out("    %s in %s -> start routine %s   [%s]" % (h(site), creator, G.name(val) if val else "UNRESOLVED", how))
        if val:
            starts.setdefault(val, []).append((api, site, creator))
        return val
    sites = sorted(G.iatcall.get(ct, []))
    loads = sorted(G.datasites.get(slot_of[ct], []))
    out("  %s: %d call sites, %d other references" % (ct, len(sites), len(loads)))
    ok = all([record(ct, s, "r8") for s in sites])
    check(ok and not loads and not missed(slot_of[ct], sites),
          "A3 every CreateThread call site has a resolved start routine; the import is used nowhere else")
    bt_sites = sorted(G.callers.get(bt, []) + G.tailers.get(bt, []))
    out("  _beginthreadex (static C runtime, starts through CreateThread above): %d call sites, address taken %d times"
        % (len(bt_sites), len(G.coderefs.get(bt, [])) + len(G.slots_of.get(bt, []))))
    ok = all([record("_beginthreadex", s, "r8") for s in bt_sites])
    check(ok and not G.coderefs.get(bt) and not G.slots_of.get(bt) and not missed(bt, bt_sites),
          "A4 every _beginthreadex call site has a resolved start routine; its address is never taken")
    ok = len(sdl) == 1
    for va in sdl:
        sdl_sites = sorted(G.callers.get(va, []) + G.tailers.get(va, []))
        other = [r for r in refs_text(G, va) if not r.startswith(("call from", "jump from"))]
        out("  SDL_CreateThread (SDL_SYS_CreateThread -> _beginthreadex -> RunThreadViaBeginThreadEx -> SDL_RunThread "
            "-> fn): %d call sites, other references: %s" % (len(sdl_sites), ", ".join(other) or "none"))
        ok &= all([record("SDL_CreateThread", s, "rcx") for s in sdl_sites])
        ok &= all(r == "exported" for r in other) and not missed(va, sdl_sites)
    check(ok, "A5 every SDL_CreateThread call site has a resolved thread function; its address is never taken "
              "(it is exported, see E for the DLLs)")
    cb_sites = sorted((s, api) for api in (wo, wi) for s in G.iatcall.get(api, []))
    out("  waveOutOpen/waveInOpen (a callback function runs on a WINMM thread): %d call sites" % len(cb_sites))
    ok = True
    for s, api in cb_sites:
        val, how = G.resolve(s, "r9")
        out("    %s %s in %s -> callback %s   [%s]" % (h(s), api.split("!")[1], G.fname(s),
                                                     G.name(val) if val else ("none" if val == 0 else "UNRESOLVED"), how))
        ok &= val is not None
        if val:
            starts.setdefault(val, []).append((api.split("!")[1], s, G.fname(s)))
    ok &= not G.datasites.get(slot_of[wo]) and not G.datasites.get(slot_of[wi])
    ok &= not missed(slot_of[wo], [s for s, a in cb_sites]) and not missed(slot_of[wi], [s for s, a in cb_sites])
    check(ok, "A6 every waveOutOpen/waveInOpen call site passes a resolved callback function or none")
    # which of the SDL threads the exe ever starts
    out("  SDL subsystems (they decide which SDL threads start):")
    flags_ok = True
    for nm in ("SDL_Init", "SDL_InitSubSystem"):
        va = one_addr(G, nm)
        for s in sorted(G.callers.get(va, [])):
            val, how = G.resolve(s, "rcx")
            dead = only_exported(G, G.node_of(s))
            out("    %s called from %s with flags %s   [%s]%s" % (nm, G.name(s), h(val) if val is not None else "?", how,
                                                            " (the caller is only exported, not referenced by the exe's code)" if dead else ""))
            if nm == "SDL_Init":
                flags_ok &= val is not None and not (val & 0x3200)
        for s in sorted(G.tailers.get(va, [])):
            out("    %s jumped to from %s (flags passed through)" % (nm, G.name(s)))
    check(flags_ok, "A7 SDL_Init is called only with immediate flags without JOYSTICK/HAPTIC/GAMECONTROLLER (0x3200)")
    unused = []
    for nm in ("SDL_AddTimer", "SDL_OpenAudio", "SDL_OpenAudioDevice", "SDL_GameControllerOpen", "SDL_HapticOpen",
               "SDL_HapticOpenFromJoystick", "SDL_HapticOpenFromMouse"):
        va = one_addr(G, nm)
        unused.append(only_exported(G, va))
        out("    %s: referenced by %s%s" % (nm, ", ".join(refs_text(G, va)), "" if unused[-1] else "   <- USED"))
    check(all(unused), "A7 no decoded code or data slot of the exe uses SDL_AddTimer, SDL_OpenAudio(Device), "
                       "SDL_GameControllerOpen or SDL_HapticOpen*: only exports and functions that are themselves only "
                       "exported refer to them")
    out("  creators and their direct callers:")
    for c in sorted({cr for v in starts.values() for api, s, cr in v}):
        va = one_addr(G, c) if c in G.names.values() else 0
        wrap("    %s <- " % c, refs_text(G, va) if va else ["?"])
    return starts


# ---------------------------------------------------------------- section B
def section_b(G, starts):
    out("B. Forward: what each non-main start routine reaches through resolved edges (direct calls, jumps, switches, "
        "fall-through)")
    tset = {G.node_of(t): nm for t, nm in TARGETS}
    bodies = []
    tramp = sorted(s for s in starts if TRAMPOLINES.match(G.name(s)))
    winmm = sorted(s for s in starts if any(api in ("waveOutOpen", "waveInOpen") for api, x, c in starts[s]))
    for s in sorted(starts, key=lambda v: G.name(v)):
        if s not in tramp and s not in winmm:
            bodies.append((G.name(s), [s]))
    bodies.append(("C runtime and SDL thread trampolines (%s)" % ", ".join(G.name(s) for s in tramp), tramp))
    if winmm:
        bodies.append(("WINMM audio callbacks (%s)" % ", ".join(G.name(s) for s in winmm), winmm))
    covered = {s for t, e in bodies for s in e}
    check(covered == set(starts), "B every start routine found in A is analysed below")
    thread_nodes = set()
    for title, ents in bodies:
        par = G.closure(ents)
        thread_nodes |= set(par)
        hit = sorted(tset[g] for g in par if g in tset)
        game = sorted(g for g in par if GAME_FWD.match(G.name(g)))
        folded = [g for g in game if folded_ok(G, g)]
        bad = [G.name(g) for g in game if g not in folded]
        unres = sum(1 for g in par for a, ops, t in G.groups[g]["icalls"] + G.groups[g]["ijmps"] if t not in G.exe.iat)
        how = sorted({"%s via %s" % (api, cr) for s in ents for api, x, cr in starts[s]})
        label = title.split(" (")[0]
        open_route(label, unres, "indirect calls/jumps")
        out("  %s" % title)
        wrap("    started by: ", how)
        out("    reaches %d functions; %d indirect calls/jumps in them stay unresolved; game-named functions "
            "reached: %d" % (len(par), unres, len(bad)))
        if folded:
            out("    named like game code but folded (not counted): " + ", ".join(
                "%s %s = %s" % (h(g), G.name(g), FOLDED[g][1]) for g in folded))
        check(not hit, "B %s: reaches none of the %d targets through resolved edges" % (label, len(TARGETS))
              + (" (reaches %s)" % hit if hit else ""))
        check(not bad, "B %s: reaches no game-named function through resolved edges" % label
              + (" (reaches %s)" % bad[:5] if bad else ""))
    # libjingle and glue code together (covers virtual dispatch to any named libjingle or glue function)
    ents = sorted(va for va, nm in G.names.items() if JINGLE.match(nm))
    par = G.closure(ents)
    out("  libjingle and its glue (talk_base, cricket, buzz, sigslot, Xmpp*, DPProviderJingle, DPPeerJingle), all together"
        " (this covers virtual dispatch to any named libjingle or glue function; the lobby is not covered, see F1):")
    unres = sum(1 for g in par for a, ops, t in G.groups[g]["icalls"] + G.groups[g]["ijmps"] if t not in G.exe.iat)
    open_route("libjingle/glue", unres, "indirect calls/jumps")
    glue = sum(1 for g in par if G.name(g).split("::")[0] in GLUE)
    out("    %d named functions reach %d functions; %d indirect calls/jumps in them stay unresolved; %d of the reached "
        "functions are glue (game code that drives the lobby: Xmpp*, DPProviderJingle, DPPeerJingle)" % (
            len(ents), len(par), unres, glue))
    hit = sorted(tset[g] for g in par if g in tset)
    check(not hit, "B libjingle/glue: reaches none of the %d targets through resolved edges" % len(TARGETS)
          + (" (reaches %s)" % hit if hit else ""))
    named = sorted(g for g in par if GAME_UNION.match(G.name(g)))
    fam = Counter()
    for g in named:
        nm = G.name(g)
        fam["SDL/WIN" if nm.startswith(("SDL_", "WIN_")) else "Lua API" if nm.startswith("lua") else
            "DPWrapper" if nm.startswith("DPWrapper") else "folded" if folded_ok(G, g) else
            "game logic" if GAME_LOGIC.match(nm) else "other engine"] += 1
    out("    other engine-named functions among them: %d (%s)" % (
        len(named), ", ".join("%s %d" % kv for kv in sorted(fam.items()))))
    logic = [G.name(g) for g in named if GAME_LOGIC.match(G.name(g)) and not folded_ok(G, g)]
    other = sorted(G.name(g) for g in named if not GAME_LOGIC.match(G.name(g)) and not G.name(g).startswith(
        ("SDL_", "WIN_", "lua", "DPWrapper")))
    if other:
        wrap("    other engine functions: ", other)
    wrap("    DPWrapper functions: ", sorted(G.name(g) for g in named if G.name(g).startswith("DPWrapper")))
    check(not logic, "B libjingle/glue: no game-logic function is reachable through resolved edges"
          + (" (found %s)" % logic[:5] if logic else ""))
    om = sorted({n.rsplit("::", 1)[0] for n in G.names.values() if n.endswith("::OnMessage")})
    om_out = [c for c in om if not LIBJINGLE.match(c + "::")]
    dests = sorted({m.group(1) for n in G.names.values() for m in [re.match(r"^sigslot::_connection\d<([^,]+),", n)] if m})
    dest_out = [c for c in dests if not LIBJINGLE.match(c + "::")]
    out("    non-libjingle classes implementing MessageHandler::OnMessage: %s; receiving sigslot signals: %s"
        % (", ".join(om_out), ", ".join(dest_out)))
    check(set(om_out) <= GLUE and set(dest_out) <= GLUE,
          "B libjingle's MessageHandler::OnMessage and sigslot signals dispatch into no game class except its glue "
          "(which is part of the set above)")
    out("    glue functions that use the engine's Lua state, and who calls them:")
    for g in sorted(G.groups, key=lambda v: G.name(v)):
        nm = G.name(g)
        if nm.split("::")[0] not in GLUE or "+" in nm:
            continue
        lua = sorted({G.name(t) for a, t in G.groups[g]["calls"] if G.name(t).startswith(("lua_", "luaL_"))})
        if lua:
            wrap("      %s (%s) <- " % (nm, ", ".join(lua)), refs_text(G, g))
    pe_ = one_addr(G, "DPWrapper::PumpEvents")
    wrap("    DPWrapper::PumpEvents (pumps the network providers) <- ", refs_text(G, pe_))
    return thread_nodes, set(par), {G.node_of(s) for s in starts}


# ---------------------------------------------------------------- section C
def hook_sites(G, dbs):
    """EEex's CGameSprite construct/destruct hooks: each pattern from the loader's pattern files must occur once
    in the exe, and pattern + offset must be a call inside the expected constructor or destructor."""
    out("  EEex's CGameSprite construct/destruct hook sites (EEex_Sprite_Patch.lua), located with the loader's "
        "patterns from: %s" % (", ".join(label for label, raw in dbs) or "(no --loader-db given)"))
    if not dbs:
        out("    NOT CHECKED")
        return
    secs = {}
    for label, raw in dbs:  # later files override earlier ones
        cur = None
        for line in raw.decode("utf-8", "replace").splitlines():
            line = line.strip()
            m = re.match(r"^\[(.+)\]$", line)
            if m:
                cur = secs[m.group(1)] = {"file": label}
            elif cur is not None and "=" in line and not line.startswith(";"):
                k, v = line.split("=", 1)
                cur[k.strip()] = v.strip()
    for lab, fn in (("Hook-CGameSprite::Construct1()-FirstCall", 0x1401a3480),
                    ("Hook-CGameSprite::Construct2()-FirstCall", 0x140341860),
                    ("Hook-CGameSprite::Destruct()-FirstCall", 0x140343cc0)):
        e, ok = secs.get(lab, {}), False
        m = re.fullmatch(r"ADD (-?\d+)", e.get("Operations", "ADD 0"))
        pat = bytes.fromhex(e["Pattern"]) if re.fullmatch(r"([0-9A-Fa-f]{2})+", e.get("Pattern", "")) else None
        hits = []
        i = G.img.find(pat) if pat else -1
        while i >= 0:
            hits.append(G.base + i)
            i = G.img.find(pat, i + 1)
        if m and len(hits) == 1:
            site = hits[0] + int(m.group(1))
            a, sz, mn, ops = G.one(site) or (site, 0, "undecodable", "")
            ok = mn == "call" and G.node_of(site) == G.node_of(fn)
            out("    %s (%s): pattern found once in the image at %s; hook site %s = %s: %s %s" % (
                lab, e["file"], h(hits[0]), h(site), G.name(site), mn, ops))
        else:
            out("    %s: pattern %s, operations %s, found %d times in the image" % (
                lab, e.get("Pattern", "missing"), e.get("Operations", "none"), len(hits)))
        check(ok, "C EEex hook %s is a call inside %s %s" % (lab, h(fn), G.name(fn)))


def section_c(G, thread_nodes, union_nodes, start_nodes, dbs):
    exe = G.exe
    out("C. Reverse: callers of each target in the resolved graph, and a chain from the main loop")
    names_ok = all(G.names.get(va) == nm for va, nm in TARGETS)
    check(names_ok, "C target addresses carry the expected names in the names DB")
    ctors = sorted(va for va, n in G.names.items() if n == "CGameSprite::CGameSprite")
    dtors = sorted(va for va, n in G.names.items() if re.match(r"^CGameSprite::(~CGameSprite|`\w+_destructor')$", n))
    check(set(ctors) | set(dtors) <= {t for t, n in TARGETS},
          "C all CGameSprite constructors (%s) and destructors (%s) are targets" % (", ".join(map(h, ctors)), ", ".join(map(h, dtors))))
    hook_sites(G, dbs)
    out("  virtual calls used by the chains (matched by slot; the vtable is the one the class constructor installs):")
    extra = {}
    for site, off, vt, cls, callee, recv in HOPS:
        a, sz, mn, ops = G.one(site)
        m = re.match(r"^qword ptr \[(\w+)(?: \+ (0x[0-9a-f]+))?\]$", ops)
        got = (int(m.group(2), 16) if m.group(2) else 0) if m else None
        owners = sorted({G.fname(s) for s in G.datasites.get(vt, [])})
        ok = mn in ("call", "jmp") and got == off and exe.u64(vt + off) == callee and "%s::%s" % (cls, cls) in owners
        out("    %s %s %s in %s -> %s vtable %s + %s = %s (vtable loaded by %s)" % (
            h(site), mn, ops, G.fname(site), cls, h(vt), h(off), G.name(callee), ", ".join(owners)))
        if recv:
            before, after = G.near(site, 6, 0)
            loads = [i for i in before if i[2] == "mov" and i[3] == "rcx, " + recv]
            ctor_sites = [a2 for a2, t in G.groups[G.node_of(site)]["calls"] if t in ctors]
            stored = []
            for cs in ctor_sites:
                b2, a3 = G.near(cs, 0, 5)
                stored += [cs for i in a3 if i[2] == "mov" and i[3] == recv + ", rax"]
            out("      receiver: %s, loaded at %s, holds the CGameSprite built at %s" % (
                recv, ", ".join(h(i[0]) for i in loads) or "?", ", ".join(h(x) for x in sorted(set(stored))) or "?"))
            ok = ok and loads and stored
        check(ok, "C virtual call at %s resolves to %s" % (h(site), G.name(callee)))
        extra.setdefault(G.node_of(site), []).append((G.node_of(callee), site, "virtual +%s" % h(off)))
    entry = exe.base + exe.pe.OPTIONAL_HEADER.AddressOfEntryPoint
    upd = one_addr(G, "CChitin::Update")
    par = G.closure([entry])
    ok = G.node_of(upd) in par
    check(ok, "C the process entry reaches CChitin::Update by direct calls (the main loop)")
    if ok:
        out("    " + " > ".join(G.name(x) for x, a, k in G.path(par, G.node_of(upd))))
    main = G.closure([upd], extra, exclude=lambda x: bool(MP_HANDLERS.match(G.name(x))))
    full = G.closure([upd], extra)
    chains = {}
    for va, nm in TARGETS:
        g = G.node_of(va)
        if g in main:
            chains[va] = ("", G.path(main, g))
        elif g in full:
            chains[va] = (" (only through multiplayer message handlers)", G.path(full, g))
    printed = []
    for va, nm in TARGETS:
        out("  %s %s" % (h(va), nm))
        wrap("    referenced by: ", refs_text(G, va))
        for s in sorted(G.slots_of.get(va, [])):
            vt = next((b for b in range(s, s - 8 * 512, -8) if G.datasites.get(b)), None)
            if vt is not None:
                out("      slot %s = vtable %s + %s (vtable loaded by %s)" % (
                    h(s), h(vt), h(s - vt), ", ".join(sorted({G.fname(x) for x in G.datasites[vt]}))))
        anc = G.ancestors(va)
        roots = sorted(g for g in anc if not G.rev.get(g))
        kinds, odd = Counter(), []
        for g in roots:
            if g == entry:
                kinds["process entry"] += 1
            elif G.slots_of.get(g):
                kinds["data slot (vtable or function table)"] += 1
            elif G.coderefs.get(g):
                regs = sorted({G.fname(a) for a in G.coderefs[g]})
                if all(LUA_REGISTRARS.match(r) for r in regs):
                    kinds["Lua binding (%s)" % "/".join(regs)] += 1
                else:
                    kinds["address taken"] += 1
                    odd.append("%s (address loaded in %s)" % (G.name(g), ", ".join(regs)))
            else:
                kinds["unreferenced"] += 1
                odd.append("%s (unreferenced)" % G.name(g))
        viaptr = sum(1 for g in anc if G.slots_of.get(g) or G.coderefs.get(g))
        out("    it and its callers in the resolved graph, transitively up to the roots: %d function%s; roots (functions "
            "nothing calls directly) by how they are referenced: %s; %d of the %d can also be entered through a function pointer "
            "(data slot or loaded address)" % (len(anc), "" if len(anc) == 1 else "s",
                                              ", ".join("%s %d" % kv for kv in sorted(kinds.items())), viaptr, len(anc)))
        for o in odd:
            out("      root " + o)
        bad = sorted(G.name(g) for g in set(anc) & (thread_nodes | union_nodes | start_nodes))
        check(not bad, "C %s: no start routine, thread-body function or libjingle/glue function among its callers "
              "in the resolved graph" % nm + (" (found %s)" % bad[:5] if bad else ""))
        if va not in chains:
            check(False, "C %s: reached from the main loop" % nm)
            continue
        note, steps = chains[va]
        longer = [(v2, n2) for v2, n2 in TARGETS if v2 in printed and len(chains[v2][1]) > len(steps)
                  and chains[v2][1][:len(steps)] == steps]
        check(True, "C %s: reached from the main loop CChitin::Update%s" % (nm, note))
        if longer and not note:
            v2, n2 = longer[0]
            out("    chain: the first %d steps of the chain printed for %s %s" % (len(steps), h(v2), n2))
            continue
        out("    chain:")
        for x, a, k in steps:
            out("      %s%s" % ("> " if a is not None else "", G.name(x)) + ("   (%s at %s)" % (k, h(a)) if a is not None else ""))
        printed.append(va)
    # code the recursive descent never reached (for example __except blocks) could still call into the targets
    allanc = set()
    for va, nm in TARGETS:
        allanc |= set(G.ancestors(va))
    scan = exe.code_refs(allanc)
    hidden = sorted((x, k, t) for t, hits in scan.items() for x, k in hits if not G.covered(x))
    out("  byte scan of all code for calls, jumps and address loads of the targets and all their callers in the resolved "
        "graph (%d functions): %d hits, %d of them outside the decoded instructions" % (
            len(allanc), sum(map(len, scan.values())), len(hidden)))
    for x, k, t in hidden:
        out("    %s %s -> %s" % (h(x), k, G.name(t)))
    check(not hidden, "C no code outside the decoded instructions calls, jumps to or loads the address of a target or "
                      "of any of its callers in the resolved graph")
    out("  XP field writes in CGameSprite::SetAtOffset (stat 44 branch):")
    for x in G.groups[G.node_of(0x1403727d0)]["ranges"]:
        a, sz, mn, ops = G.one(x)
        if "[rcx + 0x570]" in ops and mn in ("add", "mov", "sub"):
            out("    %s %s %s" % (h(a), mn, ops))


# ---------------------------------------------------------------- section D
def section_d(G, starts):
    out("D. SearchThreadMain and CNetwork::ThreadLoop (names suggest threads)")
    upd = one_addr(G, "CChitin::Update")
    for nm in ("SearchThreadMain", "CNetwork::ThreadLoop"):
        va = one_addr(G, nm)
        calls = sorted(G.callers.get(va, []))
        wrap("  %s %s <- " % (h(va), nm), refs_text(G, va))
        check(not G.tailers.get(va) and not G.coderefs.get(va) and not G.slots_of.get(va) and va not in starts,
              "D %s is only called directly, its address is never taken, so it is no thread start routine" % nm)
        check(any(G.node_of(c) == G.node_of(upd) for c in calls), "D %s is called directly from CChitin::Update" % nm)


# ---------------------------------------------------------------- section E
def section_e(eeex, loader_bins):
    out("E. EEex.dll and the loader binaries")
    thr = sorted(n for n in eeex.iat.values() if n.split("!", 1)[1] in CREATE_APIS)
    thr += sorted({n.split("!")[0] for n in eeex.iat.values() if re.match(r"(?i)(concrt|vcomp|libomp)", n)})
    check(thr == ["KERNEL32.dll!CreateThread"], "E EEex.dll imports no thread/work-creation API except CreateThread, "
                                                "and no ConcRT/OpenMP runtime")
    slot = next(a for a, n in eeex.iat.items() if n == "KERNEL32.dll!CreateThread")
    refs = eeex.code_refs([slot])[slot]
    out("  references to the CreateThread import (byte scan of all code): " + ", ".join("%s %s" % (h(a), k) for a, k in refs))
    if not check(len(refs) == 1 and refs[0][1] == "call [rip]", "E EEex.dll calls CreateThread at exactly one place"):
        return
    site = refs[0][0]
    flo, fhi = eeex.pdata_range(site)
    ins = eeex.insns(flo, fhi)
    lea_r8 = [(a, rip_target(a, sz, ops)) for a, sz, mn, ops in ins if a < site and mn == "lea" and ops.startswith("r8,")]
    start = lea_r8[-1][1] if lea_r8 else None
    a, sz, mn, ops = eeex.insns(start, start + 16)[0]
    body = int(ops, 16) if mn == "jmp" and IMM.match(ops) else None
    out("  call at %s in function %s..%s; start routine %s = '%s %s'; thread body %s" % (
        h(site), h(flo), h(fhi), h(start), mn, ops, h(body) if body else "?"))
    fref = eeex.code_refs([flo])[flo]
    dref = eeex.data_refs([flo])[flo]
    out("  references to %s: %s; data slots: %s" % (h(flo), ", ".join("%s %s" % (h(a2), k) for a2, k in fref) or "none",
                                                   ", ".join(map(h, dref)) or "none"))
    reg_ok = False
    if len(fref) == 1 and fref[0][1] == "lea" and not dref:
        L = fref[0][0]
        seq = eeex.insns(L, L + 40)[:4]
        tolua = next((x for x, n in eeex.iat.items() if n == "LuaBindingsCore.dll!?tolua_function@@YAXPEAUlua_State@@PEBDP6AH0@Z@Z"), None)
        name_va = rip_target(seq[2][0], seq[2][1], seq[2][3]) if seq[2][2] == "lea" else None
        call_va = rip_target(seq[3][0], seq[3][1], seq[3][3]) if seq[3][2] == "call" else None
        reg_ok = (seq[0][2] == "lea" and seq[0][3].startswith("r8,") and rip_target(*seq[0][:2], seq[0][3]) == flo
                  and seq[2][3].startswith("rdx,") and name_va and eeex.cstr(name_va) == "OpenDebugWindow" and call_va == tolua)
        rlo, rhi = eeex.pdata_range(L)
        out("  registration in %s..%s: " % (h(rlo), h(rhi)) + "; ".join("%s %s %s" % (h(i[0]), i[2], i[3]) for i in seq))
        out("    = tolua_function(L, \"%s\", %s)" % (eeex.cstr(name_va) if name_va else "?", h(flo)))
    check(reg_ok, "E the function that calls CreateThread is reached only through the Lua binding OpenDebugWindow")
    # what the debug-window thread runs: linear sweep of each called function's .pdata range (0x200 bytes when
    # it has none), following direct calls and jumps, at most 400 call targets
    seen, dq, used, ind, units, nopdata = set(), deque([body]), set(), [], set(), 0
    while dq and len(seen) < 400:
        f = dq.popleft()
        if f in seen:
            continue
        seen.add(f)
        rng = eeex.pdata_range(f)
        if rng is None:
            nopdata += 1
        lo, hi = rng or (f, f + 0x200)
        if (lo, hi) in units:
            continue
        units.add((lo, hi))
        for a, sz, mn, ops in eeex.insns(lo, hi):
            if mn in ("call", "jmp"):
                mi = IMM.match(ops)
                if mi:
                    t = int(mi.group(1), 16)
                    if not (lo <= t < hi):
                        dq.append(t)
                else:
                    t = rip_target(a, sz, ops)
                    if t is not None and t in eeex.iat:
                        used.add(eeex.iat[t])
                        continue
                    if mn == "call":
                        ind.append(a)
    cut = any(f not in seen for f in dq)
    title = []
    for enc in ("EEex Debug Window".encode("utf-16le"), b"EEex Debug Window\0"):
        i = eeex.img.find(enc)
        while i >= 0:
            title.append(eeex.base + i)
            i = eeex.img.find(enc, i + 1)
    trefs = eeex.code_refs(title)
    strs = sorted(r for t in title for r, k in trefs[t] if k == "lea")
    in_body = [r for r in strs if any(lo <= r < hi for lo, hi in units)]
    out("  debug-window thread body: %d call targets in %d code ranges (%d without .pdata, swept as 0x200-byte windows), "
        "sweep %s; %d imports used; %d indirect calls decoded at %d distinct sites (overlapping windows decode %d "
        "twice)" % (len(seen), len(units), nopdata, "CUT AT 400" if cut else "complete", len(used), len(ind),
                    len(set(ind)), len(ind) - len(set(ind))))
    wrap("    Lua and synchronisation imports it uses: ", sorted(
        short_import(n) for n in used if re.search(r"lua_|LuaState|SRWLock|ConditionVariable|_Mtx_", n)))
    out("    the window title 'EEex Debug Window' is loaded at %s" % (", ".join(map(h, in_body)) or "?"))
    check(not cut and in_body, "E the CreateThread start routine is the EEex debug window")
    out("  binaries checked for SDL thread, timer and audio function names (ASCII or UTF-16, whole names):")
    for im in [eeex] + loader_bins:
        hits = im.name_hits(SDL_BIND_NAMES)
        thr = sorted(n for n in im.iat.values() if n.split("!", 1)[1] in CREATE_APIS)
        thr += sorted({n.split("!")[0] for n in im.iat.values() if re.match(r"(?i)(concrt|vcomp|libomp)", n)})
        out("    %-32s %8d bytes  sha256 %s" % (im.label(), len(im.raw), im.sha256))
        out("      thread/work-creation imports (and ConcRT/OpenMP DLLs): %s; SDL thread/timer/audio names: %s" % (
            ", ".join(thr) or "none", ", ".join(hits) or "none"))
        check(not hits, "E %s binds no SDL thread, timer or audio function by name" % im.label())
        if im is not eeex:
            check(not thr, "E %s imports no thread/work-creation API and no ConcRT/OpenMP runtime" % im.label())
    names = eeex.name_hits(["SearchThreadMain", "CNetwork::ThreadLoop"])
    out("  thread-like engine function names in EEex.dll: %s (both are plain main-thread calls, see D)" % (
        ", ".join(names) or "none"))
    open_route("EEex debug-window thread", len(set(ind)), "indirect call sites")
    return len(set(ind))


# ---------------------------------------------------------------- section F
def section_f(n_ind):
    out("F. Remaining uncertainties (as found by the analysis; this script does not check them)")
    for item in (
        "1. Beamdog internet lobby, not covered. DPProviderJingle::OnNicknameCollision, called from "
        "XmppHandler::OnMucLeft, reads the engine's Lua state without a lock, possibly on the XMPP network thread "
        "(likely, not proven). It makes no Lua calls, but a Lua __index handler or garbage-collector finalizer could "
        "in theory run Lua code there. This is an existing engine race, only in the lobby. The lobby code (libjingle "
        "and its glue) has no resolved path to the targets, but its indirect calls/jumps stay unresolved (see "
        "RESULT), so this audit does not cover it.",
        "2. Debug-window thread. It uses the shared Lua state with locks. Whether it hands its Lua calls to the main "
        "thread is not proven, and its %s indirect call sites are unresolved (see RESULT). It only matters if "
        "someone opens the window." % (n_ind if n_ind is not None else "?"),
        "3. Code outside the exe and EEex. OS, GPU driver, OpenAL, Steam and COM threads were not analysed. No way "
        "for them to call into game code was found: OpenAL is used without callbacks, and the Steam update runs "
        "from the main loop.",
        "4. No runtime check. This is static analysis only; the game was not run. A lab could confirm it by logging "
        "the thread ID inside the hook and at EEex start.",
        "5. Unresolved indirect routes. B follows only resolved edges from each thread; the indirect calls/jumps "
        "counted there are not followed, so a route through them to a target is not excluded. RESULT lists each "
        "such route with its count."):
        words, line = item.split(), "  "
        for w in words:
            if len(line) + len(w) + 1 > 110:
                out(line)
                line = "     " + w
            else:
                line += (" " if line.strip() else "") + w
        out(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--names", required=True)
    ap.add_argument("--eeex", required=True)
    ap.add_argument("--loader-bin", action="append", default=[])
    ap.add_argument("--loader-db", action="append", default=[])
    ap.add_argument("--out")
    args = ap.parse_args()
    exe, eeex = Image(args.exe), Image(args.eeex)
    names_raw = Path(args.names).read_bytes()
    names_sha = hashlib.sha256(names_raw).hexdigest().upper()
    loader = [Image(p) for p in args.loader_bin]
    dbs = [(Path(p).parent.name + "/" + Path(p).name, Path(p).read_bytes()) for p in args.loader_db]
    out("Main-thread audit, BG2:EE 2.7.3.0 (static; produced by main_thread_audit.py)")
    out("inputs:")
    out("  exe    %-28s %9d bytes  sha256 %s  PE timestamp %d" % (exe.label(False), len(exe.raw), exe.sha256, exe.pe.FILE_HEADER.TimeDateStamp))
    out("  names  %-28s %9d bytes  sha256 %s" % (Path(args.names).parent.name + "/" + Path(args.names).name, len(names_raw), names_sha))
    out("  eeex   %-28s %9d bytes  sha256 %s  PE timestamp %d" % (eeex.label(), len(eeex.raw), eeex.sha256, eeex.pe.FILE_HEADER.TimeDateStamp))
    for label, raw in dbs:
        out("  patterns %-26s %9d bytes  sha256 %s" % (label, len(raw), hashlib.sha256(raw).hexdigest().upper()))
    out("tools: python %d.%d.%d, pefile %s, capstone %s" % (sys.version_info[:3] + (pefile.__version__, capstone.__version__)))
    ok = check(exe.sha256 == EXE_SHA256, "input Baldur.exe is the pinned 2.7.3.0 build")
    ok &= check(names_sha == NAMES_SHA256, "input function_names.db is EEex v1.3.1's v2.7.3.0 names DB")
    ok &= check(eeex.sha256 == EEEX_SHA256, "input EEex.dll is EEex v1.3.1's v2.7.3.0 build")
    if ok:
        names = {}
        for line in names_raw.decode("utf-8", "replace").splitlines():
            a, _, n = line.partition("\t")
            if a.startswith("0x"):
                names.setdefault(int(a, 16), n)
        G = Graph(exe, names)
        out("decoded: %d .pdata functions, %d leaf functions (fixed point after %d rounds), %d instructions, "
            "%d data slots holding code addresses, %d names" % (
                G.n_pdata, len(G.groups) - G.n_pdata, G.leaf_rounds, sum(g["ninsn"] for g in G.groups.values()),
                len(G.ptr_slots), len(names)))
        out()
        starts = section_a(G)
        out()
        thread_nodes, union_nodes, start_nodes = section_b(G, starts)
        out()
        section_c(G, thread_nodes, union_nodes, start_nodes, dbs)
        out()
        section_d(G, starts)
        out()
    n_ind = section_e(eeex, loader) if ok else None
    out()
    for line in verdict(NCHECK[0], FAILS, OPEN):
        out(line)
    out()
    section_f(n_ind)
    data = ("\n".join(LINES) + "\n").encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    if args.out:
        Path(args.out).write_bytes(data)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
