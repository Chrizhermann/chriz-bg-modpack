"""Static check: the bank's native callbacks reach no code that could destroy or
recreate an actor.

Destroying or recreating an actor inside these callbacks is prohibited. The award
and setter bridges (award_native.cpp, writer_native.cpp), the cap check, the
dual-class bridge and the party hook run them while the engine holds the actor
(and effect) pointers, and the engine's callers (CGameEffectList::HandleList,
the stat setter's recalculation) keep using those pointers after the hook
returns. The bridges' last safeguard, writing nothing into a lifetime that
provably ended (status 11), cannot make that later use safe; this check enforces
the prohibition for the SHIPPED Lua.

What it proves: from each native callback it follows, by name, every function of
ours a call can reach (module functions, configured module fields, the global
module tables), and every call that leaves our modules must be a reviewed
function that only reads or records state (no game action, script, effect, UI,
area, save or load). A call it cannot resolve to one of those fails it: a call
through a local value, a call of an expression's result, an undefined name, and a
function value handed to a builtin that calls it (pcall, both functions of
xpcall, a table.sort comparator, a gsub replacement), unless that value is a
function literal (scanned with its enclosing function), a plain name resolved as
above, or a literal that calls nothing.

Names are trusted, so a parser of the package checks that each keeps meaning
what the walk read, everywhere (reachable or not: it all runs). A reviewed name
is never rebound. A function the walk follows by name is bound to nothing but
its definitions (no parameter, loop variable or other value of that name), and
each call reaches that variable, not a global (agrees()). A module's table is
its one local table; a field the walk follows is written only by its own
definition, the configured ones only in CONFIGURES; no computed key writes into
a library, EngineGlobals, _G (COMPUTED_GLOBALS excepted) or any value that may
be a module table, under whatever name the module's code passes it on
(module_values()). The callback globals are bound only where their hooks
install them (bindings()).
An engine method (METHODS) is trusted only on an engine value, traced through
every variable and parameter that carries it (engine_values()); Lua's string
methods are not trusted. No module uses metatables, raw writes, debug, _ENV or
code loading, by name or through _G, or holds a shared table under another name
(metatables(), loaded_code()).

What it assumes: the reviewed game, EEex and native functions (NATIVES, ENGINE,
METHODS) run no Lua and end no lifetime, as reviewed below; metatables of game
values (EEex's field accessors) only read, and a field of an engine value is an
engine value or a plain one; the globals written or made natively under
computed names, and those read so (COMPUTED_GLOBALS, COMPUTED_NATIVE_GLOBALS,
GLOBAL_READS, GLOBAL_LOOPS: install code and its own CBM* helpers), are not
reviewed names; a table that other modules or native code fill (an options
table, a profile list, EEex's per-actor table) holds a module table only in a
configured field of that name; R.Configure and each hook's Install run once,
from the bootstrap, with what the wiring tests assert. The dual-class level-up
and HLA screens are not part of an XP change and are outside this check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "chriz-bg-modpack/campaign-xp/runtime"
BANK = "xp-banking-native/bank_runtime.lua"
CAP = "xp-banking-native/cap_hook.lua"
PARTY = "xp-banking-native/party_hooks.lua"
CALLBACKS = ("BeforeAward", "CompleteAward", "UncertainAward", "BeforeWrite", "CompleteWrite", "UncertainWrite")
DUAL = ("PrepareDual", "CompleteDual", "UncertainDual", "CaptureDualPreview")
# What native code calls with a live actor: the XP bridges' callbacks, the cap
# check in the engine's stat update, the dual-class bridge and the party hook.
ROOTS = ([(BANK, f"R.{name}") for name in CALLBACKS + DUAL]
         + [(CAP, "M.BeforeNativeClamp"), (PARTY, "CBMBank_OnPartyReady")])

# Module fields holding another module, as bank_bootstrap.lua wires them.
CONFIGURED = {
    (BANK, "R.policy"): "xp-banking/cbmbank_policy.lua",
    (BANK, "R.account"): "xp-banking/native_account.lua",
    (BANK, "R.wire"): "xp-banking/cbmbank_store.lua",
    (BANK, "R.receipts"): "xp-banking-native/dual_reward_receipts.lua",
}
# Module fields holding one function of another module.
CONFIGURED_FUNCTIONS = {
    (CAP, "M.snapshot"): (BANK, "R.Snapshot"),
    (CAP, "M.report"): (BANK, "R.Report"),
    (PARTY, "options.runtime.OnLoaded"): (BANK, "R.OnLoaded"),
}
# Global module tables, each published by its own Install as `_G.<name>=M`.
GLOBAL_MODULES = {
    "CBMBank_Identity": "xp-banking-native/identity_hooks.lua",
    "CBMBank_Award": "xp-banking-native/award_hooks.lua",
    "CBMBank_Writer": "xp-banking-native/writer_hooks.lua",
    "CBMBank_Reset": "xp-banking-native/reset_hooks.lua",
}
# Our C++ exports, as the hooks expose them, and why each is safe inside a callback.
NATIVES = {
    "CBMBank_IdentityNativeQuery": ("CBMI_LuaQuery", "reads the bank's lifetime registry"),
    "CBMBank_IdentityNativeAckReplaced": ("CBMI_LuaAckReplaced", "clears one flag in the bank's lifetime registry"),
    "CBMBank_AwardNativeQuery": ("CBMA_LuaQuery", "reads the award bridge's record of the change"),
    "CBMBank_WriterNativeQuery": ("CBMW_LuaQuery", "reads the setter bridge's record of the change"),
    "CBMBank_WriterNativePlan": ("CBMW_LuaPlan", "stores the planned XP word in the setter bridge's record"),
    "CBMBank_ResetNativeQuery": ("CBMR_LuaQuery", "reads the dual-class bridge's record"),
    "CBMBank_ResetNativePreviewQuery": ("CBMR_LuaPreviewQuery", "reads the dual-class bridge's preview record"),
    # 2.7.3.0: CRuleTables::GetXPCap at 0x140249E40. Its whole direct-call closure
    # (174 functions) is the class and race string lookups, C2DArray::GetAt, CString
    # and CRT code (sscanf, locale); its 70 indirect calls are Win32 imports and the
    # CRT's guard dispatch. No actor constructor, destructor, area or object-list
    # change. 2.6.6.0: bg2ee-2.6.6-xp.txt (class string, 2DA GetAt, sscanf).
    "CBMBank_ResetNativeCap": ("CBMR_LuaNativeCap", "runs CRuleTables::GetXPCap, a table lookup"),
}
ENGINE = {
    "EEex_GetUDAux": "returns the Lua table EEex keeps for the userdata",
    "EEex_UDToPtr": "returns the userdata's address",
    "EEex_Sprite_GetCharacterIndex": "reads the party's character list",
    "EEex_GameState_GetGlobalInt": "reads a game variable",
    "EEex_Resource_Load2DA": "loads XPLEVEL through the engine's resource cache",
    "EEex_Sprite_GetActiveStats": "returns the actor's derived stats",
}
# Engine methods, trusted only where the receiver is an engine value (receivers()).
# Lua's string methods are not trusted: a receiver can be a table of ours, so the
# callbacks' code calls string.find(s,...) and the like instead.
METHODS = {
    "getAtLabels": "reads a cell of a loaded 2DA table",
    "get": "reads the text of an engine CString",
    "GetAtOffset": "reads one derived stat (CDerivedStats::GetAtOffset)",
}
# Reviewed engine functions whose result is an engine value whatever they are passed.
ENGINE_SOURCES = {"EEex_Resource_Load2DA", "EEex_Sprite_GetActiveStats"}
BUILTINS = {"assert", "error", "getmetatable", "ipairs", "next", "pairs", "pcall", "print", "rawequal", "rawget",
            "select", "tonumber", "tostring", "type", "unpack", "xpcall"}
LIBRARIES = {"math", "string", "table"}
# Globals that could give a table of ours a metatable, write a field past the
# checks below, change what global names mean, or reach the Lua state's
# internals: no module may use them.
FORBIDDEN = {"setmetatable", "rawset", "debug", "setfenv", "getfenv", "newproxy", "_ENV"}
# Lua that loads code (Infinity_DoFile: a Lua file of the game's override): only
# the startup file's load of its configuration and of the bootstrap, and the
# bootstrap's of the package's own modules.
LOADERS = {"load", "loadstring", "loadfile", "dofile", "require", "Infinity_DoFile"}
LOADING = {"m_cbmbnk.lua": {"dofile": 1, "Infinity_DoFile": 1}, "xp-banking-native/bank_bootstrap.lua": {"dofile": 1}}
# EEex functions that make a global from native code: the argument naming it.
NATIVE_GLOBALS = {"EEex_ExposeToLua": 2, "EEex_JITNearAsLuaFunction": 1}
# Calls of them with a computed name, by module: private CBM* helper names.
COMPUTED_NATIVE_GLOBALS = {"xp-banking-native/dual_combined_hooks.lua": 1, "xp-banking-native/dual_manual_hooks.lua": 2,
                           "xp-banking-native/dual_old_hla.lua": 1, "xp-banking-native/identity_hooks.lua": 1}
# Tables the checks trust by their global name: no module may hold one under another name.
SHARED = LIBRARIES | {"_G", "EngineGlobals"}
# The callback globals native code calls, and where each hook binds them: to
# options.runtime.<name>, to a function literal (None) or to M.<name>.
INSTALLED = {**{f"CBMBank_{name}": ("xp-banking-native/award_hooks.lua", f"options.runtime.{name}")
                for name in CALLBACKS[:3]},
             **{f"CBMBank_{name}": ("xp-banking-native/writer_hooks.lua", f"options.runtime.{name}")
                for name in CALLBACKS[3:]},
             **{f"CBMBank_{name}": ("xp-banking-native/reset_hooks.lua", f"options.runtime.{name}") for name in DUAL},
             "CBMBank_OnPartyReady": (PARTY, None),
             "CBMBank_BeforeNativeClamp": (CAP, "M.BeforeNativeClamp")}
# The one function that may write each module's configured fields.
CONFIGURES = {BANK: "R.Configure", CAP: "M.Install"}
# Computed-name global writes of a value other than nil, by module: dual_bootstrap
# restores the CBMD* globals it found at install.
COMPUTED_GLOBALS = {"xp-banking-native/dual_bootstrap.lua": 1}
# The one variable each module may hold _G in (`x=x or _G`), writing only fields
# by name through it: the old-class picker's M.Bind keeps its CBMDOldPicker* menu
# functions in the globals table it is given.
GLOBALS_ALIASES = {"xp-banking-native/dual_retired_picker.lua": "globals"}
# Reads of a global by a computed name whose value is used (not only tested or
# typed), and loops over _G, by module: install code fetching the EEex functions
# and listener tables it lists and the helpers it just made, and dual_bootstrap
# saving and clearing its CBMD* globals.
GLOBAL_READS = {"xp-banking-native/bank_record.lua": 1, "xp-banking-native/identity_hooks.lua": 2,
                "xp-banking-native/dual_manual_hooks.lua": 1}
GLOBAL_LOOPS = {"xp-banking-native/dual_bootstrap.lua": 2}
# Builtins that call a function value they are given, by argument: a protected
# call runs its first argument with the arguments after it (xpcall also runs
# its handler), table.sort its comparator, gsub a function replacement.
CALLERS = {"pcall": (1,), "xpcall": (1, 2), "table.sort": (2,), "string.gsub": (3,)}
METHOD_CALLERS = {"gsub": (2,)}  # s:gsub(pattern, replacement)
KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto", "if", "in", "local",
            "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}

LEXEME = re.compile(r"""
    (?P<skip>[ \t\r\n\f\v]+|--\[(?P<c>=*)\[.*?\](?P=c)\]|--[^\n]*)
  | (?P<string>\[(?P<s>=*)\[.*?\](?P=s)\]|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<number>0[xX][0-9a-fA-F]+|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|::|[-+*/%^\#<>=(){}\[\];:,.])
""", re.S | re.X)


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    line: int


def lex(source: str) -> list[Token]:
    out, at, line = [], 0, 1
    while at < len(source):
        match = LEXEME.match(source, at)
        assert match, f"unlexable Lua at line {line}: {source[at:at + 30]!r}"
        if match.lastgroup != "skip":
            out.append(Token(match.lastgroup, match.group(), line))
        line += match.group().count("\n")
        at = match.end()
    return out


def block_end(tokens: list[Token], start: int) -> int:
    depth = 0
    for at in range(start, len(tokens)):
        token = tokens[at]
        if token.kind == "name" and token.text in ("function", "if", "do", "repeat"):
            depth += 1
        elif token.kind == "name" and token.text in ("end", "until"):
            depth -= 1
            if depth == 0:
                return at
    raise AssertionError(f"unbalanced block at line {tokens[start].line}")


@dataclass
class Function:
    module: str
    name: str | None
    start: int
    end: int


@dataclass
class Call:
    chain: str
    line: int
    reference: bool = False  # passed as a value (pcall, a stored reference), not called here
    indirect: bool = False  # called by a builtin it is handed to, with that builtin's arguments
    head: int = -1  # the token of the chain's first name
    at: int = -1  # the token that opens the call's arguments


@dataclass
class Module:
    path: str
    source: str
    tokens: list[Token] = field(init=False)
    table: str | None = field(init=False)
    functions: list[Function] = field(init=False)
    named: dict[str, list[Function]] = field(init=False)
    statement: list[bool] = field(init=False)  # Per token: not inside a bracket of its function.
    size: int = field(init=False)  # Tokens before the end markers.
    parsed: "Parser | None" = field(init=False)  # See parse().
    values: object = field(init=False)  # See module_values().

    def __post_init__(self):
        tokens = lex(self.source)
        self.size = len(tokens)
        self.parsed = self.values = None
        last = tokens[-2:]
        self.table = last[1].text if len(last) == 2 and last[0].text == "return" and last[1].kind == "name" else None
        # End markers: looking a few tokens past the last one reads them, not past the list.
        self.tokens = tokens + [Token("end", "", tokens[-1].line if tokens else 1)] * 4
        self.statement, stack = [], []
        for at, token in enumerate(self.tokens):
            self.statement.append(not stack or stack[-1] != "bracket")
            if token.kind == "name" and token.text == "function":
                stack.append(block_end(self.tokens, at))
            elif token.kind == "op" and token.text in ("(", "{", "["):
                stack.append("bracket")
            elif token.kind == "op" and token.text in (")", "}", "]"):
                if not stack or stack.pop() != "bracket":
                    raise AssertionError(f"{self.path}: unbalanced {token.text} at line {token.line}")
            while stack and stack[-1] == at:
                stack.pop()  # The end of a function body.
        self.functions = [self.function_at(at) for at, token in enumerate(self.tokens)
                          if token.kind == "name" and token.text == "function"]
        # Every function of a name is followed: two locals of one name in different
        # scopes are both scanned rather than one of them missed.
        self.named = {}
        for f in self.functions:
            if f.name:
                self.named.setdefault(f.name, []).append(f)
        # `M.Validate=valid`: a module field that is one of the module's local functions.
        t = self.tokens
        for at in range(len(t) - 4):
            if (t[at].text == self.table and t[at + 1].text == "." and t[at + 3].text == "="
                    and t[at + 4].kind == "name" and t[at + 4].text in self.named
                    and (at + 5 >= len(t) or t[at + 5].text not in ("(", ".", ":", "[", ","))):
                self.named.setdefault(f"{self.table}.{t[at + 2].text}", []).extend(self.named[t[at + 4].text])

    def function_at(self, at: int) -> Function:
        t, end = self.tokens, block_end(self.tokens, at)
        if at and t[at - 1].text == "local":
            return Function(self.path, t[at + 1].text, at, end)
        if t[at + 1].kind == "name":
            parts, j = [t[at + 1].text], at + 2
            while t[j].text in (".", ":"):
                parts.append(t[j].text + t[j + 1].text)
                j += 2
            return Function(self.path, "".join(parts), at, end)
        if at >= 2 and t[at - 1].text == "=" and t[at - 2].kind == "name":
            j, parts = at - 2, [t[at - 2].text]
            while j >= 2 and t[j - 1].text == "." and t[j - 2].kind == "name":
                parts.insert(0, t[j - 2].text)
                j -= 2
            before = t[j - 1].text if j else ""
            if before not in ("{", ",", "]"):  # not a field of a table constructor
                return Function(self.path, ".".join(parts), at, end)
        return Function(self.path, None, at, end)

    def chain_before(self, at: int) -> tuple[str, int] | None:
        """The name chain ending at token `at` (a.b.c, a.b:c, <expr>:c), and its first index."""
        t = self.tokens
        if t[at].kind != "name" or t[at].text in KEYWORDS:
            return None
        parts, k = [t[at].text], at
        while k >= 2 and t[k - 1].text in (".", ":"):
            if t[k - 2].kind == "name" and t[k - 2].text not in KEYWORDS:
                parts.insert(0, t[k - 2].text + t[k - 1].text)
                k -= 2
            else:
                parts.insert(0, "<expr>" + t[k - 1].text)
                k -= 1
                break
        return "".join(parts), k

    def locals_in(self, function: Function) -> set[str]:
        """Names declared as plain locals, parameters or loop variables inside the function."""
        t, names = self.tokens, set()
        for at in range(function.start, function.end):
            text = t[at].text
            if text == "local" and t[at + 1].text != "function":
                j = at + 1
                while t[j].kind == "name" and t[j].text not in KEYWORDS:
                    names.add(t[j].text)
                    if t[j + 1].text != ",":
                        break
                    j += 2
            elif text == "for":
                j = at + 1
                while t[j].kind == "name" and t[j].text not in KEYWORDS:
                    names.add(t[j].text)
                    if t[j + 1].text != ",":
                        break
                    j += 2
            elif text == "function":
                j = at + 1
                while t[j].text != "(":
                    j += 1
                j += 1
                while t[j].text != ")":
                    if t[j].kind == "name":
                        names.add(t[j].text)
                    j += 1
        local_functions = {f.name for f in self.functions
                           if f.name and function.start < f.start < function.end and "." not in f.name}
        return names - local_functions

    def closing(self, at: int) -> int:
        """The bracket that closes the one at `at` (function literals skipped)."""
        t, depth, j = self.tokens, 0, at
        while True:
            if t[j].kind == "name" and t[j].text == "function":
                j = block_end(t, j)
            elif t[j].kind == "op" and t[j].text in ("(", "{", "["):
                depth += 1
            elif t[j].kind == "op" and t[j].text in (")", "}", "]"):
                depth -= 1
                if depth == 0:
                    return j
            j += 1

    def arguments(self, at: int) -> list[tuple[int, int]]:
        """(first, last) token of each argument of the call whose "(" is at `at`."""
        t, args, start, j, end = self.tokens, [], at + 1, at + 1, self.closing(at)
        while j < end:
            if t[j].kind == "name" and t[j].text == "function":
                j = block_end(t, j)
            elif t[j].kind == "op" and t[j].text in ("(", "{", "["):
                j = self.closing(j)
            elif t[j].kind == "op" and t[j].text == ",":
                args.append((start, j - 1))
                start = j + 1
            j += 1
        if end > start:
            args.append((start, end - 1))
        return args

    def plain_chain(self, first: int, last: int) -> str | None:
        """a, a.b or a.b.c spanning exactly these tokens."""
        t = self.tokens
        for k in range(first, last + 1):
            if (k - first) % 2 == 0 and (t[k].kind != "name" or t[k].text in KEYWORDS):
                return None
            if (k - first) % 2 == 1 and t[k].text != ".":
                return None
        return "".join(t[k].text for k in range(first, last + 1)) if (last - first) % 2 == 0 else None

    def harmless(self, first: int, last: int) -> bool:
        """A value that runs nothing of its own when a builtin calls or uses it:
        a function literal (its body is scanned with the enclosing function), a
        string, a number, nil, a boolean or a table constructor."""
        t = self.tokens
        if t[first].kind == "name" and t[first].text == "function":
            return block_end(t, first) == last
        if first == last:
            return t[first].kind in ("string", "number") or t[first].text in ("nil", "true", "false")
        return t[first].text == "{" and t[first].kind == "op" and self.closing(first) == last

    def callable_arguments(self, chain: str, at: int, line: int) -> list[Call]:
        """The function values a builtin caller runs: each is called as a plain
        name chain, or is a literal that runs nothing else; anything else is an
        unresolved callable argument."""
        args, out = self.arguments(at), []

        def visit(caller: str, base: int):
            method = caller.rsplit(":", 1)[1] if ":" in caller else None
            for position in METHOD_CALLERS.get(method, ()) if method else CALLERS.get(caller, ()):
                index = base + position
                if index > len(args):
                    continue
                first, last = args[index - 1]
                target = self.plain_chain(first, last)
                if target is not None:
                    out.append(Call(target, line, indirect=True, head=first))
                    if caller in ("pcall", "xpcall") and position == 1 and target in CALLERS:
                        visit(target, index + (caller == "xpcall"))  # Its arguments follow (after xpcall's handler).
                elif not self.harmless(first, last):
                    out.append(Call(f"<unresolved callable argument {index} of {chain}>", line))

        visit(chain, 0)
        return out

    def calls_in(self, function: Function) -> list[Call]:
        t, out = self.tokens, []
        body_start = function.start
        for at in range(body_start + 1, function.end):
            token = t[at]
            opener = token.text in ("(", "{") and token.kind == "op" or token.kind == "string"
            if opener:
                previous = t[at - 1]
                if previous.text in (")", "]") and previous.kind == "op":
                    out.append(Call("<expression call>", token.line, at=at))
                    continue
                found = self.chain_before(at - 1)
                if found is None:
                    continue
                chain, first = found
                if first and t[first - 1].text == "function":
                    continue  # a definition's name, not a call
                out.append(Call(chain, token.line, head=first, at=at))
                method = chain.rsplit(":", 1)[1] if ":" in chain else None
                if token.text == "(" and (method in METHOD_CALLERS if method else chain in CALLERS):
                    out += self.callable_arguments(chain, at, token.line)
            elif token.kind == "name" and token.text not in KEYWORDS:
                # A function passed or stored as a value may be called later: follow it.
                following = t[at + 1].text if at + 1 < function.end else ""
                if following in (".", ":", "(", "{") or t[at + 1].kind == "string":
                    continue
                if t[at - 1].text in (".", ":"):
                    found = self.chain_before(at)
                    if found and t[found[1] - 1].text not in ("function",):
                        out.append(Call(found[0], token.line, reference=True, head=found[1]))
                elif t[at - 1].text != "function":
                    out.append(Call(token.text, token.line, reference=True, head=at))
        return out


# A small Lua parser for the checks that need scopes: what each name refers to,
# every value a variable is bound to, and the receiver of each method call.
@dataclass(eq=False)
class Decl:
    """A local, a parameter (self included) or a loop variable."""
    name: str
    kind: str  # "local", "function" (a local function), "param", "self", "for"
    at: int
    owner: "Fn | None"  # The function whose body declares it; None: the chunk.
    values: list = field(default_factory=list)  # Each bound value: a Node, or "nil", "extra", "number", "iterated"
    loop: list | None = None  # A generic for's variable: the loop's expressions; position is its place.
    position: int = 0


@dataclass(eq=False)
class Fn:
    at: int  # Its `function` token.
    parent: "Fn | None"
    params: list = field(default_factory=list)
    end: int = -1
    node: "Node | None" = None


@dataclass(eq=False)
class Node:
    kind: str  # const, vararg, name, index, call, method, function, table, binop, unop, paren
    at: int
    end: int
    where: "Fn | None"  # The function it is in.
    name: str | None = None  # A name; a field or method name (None: computed); an operator; a constant.
    decl: Decl | None = None  # A name's variable; None: a global.
    obj: "Node | None" = None  # The indexed table, called function, method receiver, operand or left side.
    key: "Node | None" = None  # A computed key; the right side of a binary operator.
    items: list = field(default_factory=list)  # Arguments; a table constructor's values.
    keys: list = field(default_factory=list)  # A table constructor's keys (None: positional).
    open: int = -1  # A call: the token that opens its arguments.
    body: "Fn | None" = None  # A function literal's function.
    parent: "Node | None" = None


@dataclass(eq=False)
class Binding:
    """One target bound to one value by a declaration or an assignment."""
    kind: str  # "local", "local function", "function", "assign", "for", "param"
    target: "Decl | Node"  # A declared variable, or an assigned name or field.
    value: "Node | str"
    single: bool  # One target and one value.
    at: int
    extra: "Node | None" = None  # For the value "extra": the call or vararg that supplies it.


BINARY = {"or": (1, 1), "and": (2, 2), "<": (3, 3), ">": (3, 3), "<=": (3, 3), ">=": (3, 3), "~=": (3, 3),
          "==": (3, 3), "..": (9, 8), "+": (10, 10), "-": (10, 10), "*": (11, 11), "/": (11, 11), "%": (11, 11),
          "^": (14, 13)}  # Lua's left and right priorities.
BLOCK_ENDS = ("end", "else", "elseif", "until")


def string_value(text: str) -> str | None:
    """The value of a string literal without escapes, or None."""
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0] and "\\" not in text:
        return text[1:-1]
    match = re.fullmatch(r"\[(=*)\[(.*)\]\1\]", text, re.S)
    return match.group(2) if match else None


class Parser:
    def __init__(self, module: Module):
        self.path, self.t, self.p = module.path, module.tokens[:module.size], 0
        self.fn: Fn | None = None
        self.scopes: list[dict[str, Decl]] = [{}]
        self.decls: list[Decl] = []
        self.nodes: list[Node] = []
        self.fns: list[Fn] = []
        self.bindings: list[Binding] = []
        self.returns: dict[Fn | None, list[Node]] = {}  # What each function (None: the chunk) returns.
        self.block()
        if self.p != len(self.t):
            self.fail(f"unexpected {self.t[self.p].text!r}")
        for node in self.nodes:
            for child in (node.obj, node.key, *node.items, *node.keys):
                if child is not None:
                    child.parent = node

    def fail(self, message: str):
        line = self.t[min(self.p, len(self.t) - 1)].line if self.t else 1
        raise AssertionError(f"{self.path}:{line}: {message}")

    def peek(self, ahead: int = 0) -> Token:
        at = self.p + ahead
        return self.t[at] if at < len(self.t) else Token("eof", "", 0)

    def op(self, *texts: str) -> bool:
        return self.peek().kind == "op" and self.peek().text in texts

    def word(self, *texts: str) -> bool:
        return self.peek().kind == "name" and self.peek().text in texts

    def expect(self, text: str):
        if not (self.op(text) or self.word(text)):
            self.fail(f"expected {text!r}, found {self.peek().text!r}")
        self.p += 1

    def name(self) -> int:
        token = self.peek()
        if token.kind != "name" or token.text in KEYWORDS:
            self.fail(f"expected a name, found {token.text!r}")
        self.p += 1
        return self.p - 1

    def node(self, kind: str, at: int, end: int, **fields) -> Node:
        node = Node(kind, at, end, self.fn, **fields)
        self.nodes.append(node)
        return node

    def declare(self, at: int, kind: str, value=None) -> Decl:
        decl = Decl("self" if kind == "self" else self.t[at].text, kind, at, self.fn)
        self.scopes[-1][decl.name] = decl
        self.decls.append(decl)
        if kind in ("param", "self"):
            self.bindings.append(Binding("param", decl, "param", False, at))
        elif value is not None:
            decl.values.append(value)
            self.bindings.append(Binding(kind, decl, value, False, at))
        return decl

    def resolve(self, name: str) -> Decl | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def bind(self, kind: str, targets: list, values: list, at: int):
        # A call or vararg last supplies the targets past the values; otherwise they get nil.
        rest = "extra" if values and values[-1].kind in ("call", "method", "vararg") else "nil"
        for i, target in enumerate(targets):
            value = values[i] if i < len(values) else rest
            self.bindings.append(Binding(kind, target, value, len(targets) == 1 and len(values) == 1, at,
                                         values[-1] if value == "extra" else None))
            decl = target if isinstance(target, Decl) else target.decl if target.kind == "name" else None
            if decl is not None:
                decl.values.append(value)

    def block(self):
        while not (self.peek().kind == "eof" or self.word(*BLOCK_ENDS)):
            if self.word("return"):
                self.p += 1
                if not (self.peek().kind == "eof" or self.word(*BLOCK_ENDS) or self.op(";")):
                    self.returns.setdefault(self.fn, []).extend(self.expressions())
                if self.op(";"):
                    self.p += 1
                if not (self.peek().kind == "eof" or self.word(*BLOCK_ENDS)):
                    self.fail("return must end its block")
                return
            self.statement()

    def scoped(self):
        self.scopes.append({})
        self.block()
        self.scopes.pop()

    def statement(self):
        start, word = self.p, self.peek().text if self.peek().kind == "name" else None
        if self.op(";"):
            self.p += 1
        elif self.op("::"):
            self.p += 1
            self.name()
            self.expect("::")
        elif word in ("break", "goto"):
            self.p += 1
            if word == "goto":
                self.name()
        elif word == "do":
            self.p += 1
            self.scoped()
            self.expect("end")
        elif word == "while":
            self.p += 1
            self.expression()
            self.expect("do")
            self.scoped()
            self.expect("end")
        elif word == "repeat":
            self.p += 1
            self.scopes.append({})  # The condition sees the body's locals.
            self.block()
            self.expect("until")
            self.expression()
            self.scopes.pop()
        elif word == "if":
            self.p += 1
            self.expression()
            self.expect("then")
            self.scoped()
            while self.word("elseif"):
                self.p += 1
                self.expression()
                self.expect("then")
                self.scoped()
            if self.word("else"):
                self.p += 1
                self.scoped()
            self.expect("end")
        elif word == "for":
            self.p += 1
            names, loop = [self.name()], None
            if self.op("="):
                self.p += 1
                self.expressions()
                kind = "number"
            else:
                while self.op(","):
                    self.p += 1
                    names.append(self.name())
                self.expect("in")
                loop = self.expressions()
                kind = "iterated"
            self.expect("do")
            self.scopes.append({})
            for position, at in enumerate(names):
                decl = self.declare(at, "for", kind)
                decl.loop, decl.position = loop, position
            self.block()
            self.scopes.pop()
            self.expect("end")
        elif word == "function":
            self.p += 1
            at = self.name()
            target = self.node("name", at, at, name=self.t[at].text, decl=self.resolve(self.t[at].text))
            method = False
            while self.op(".", ":") and not method:
                method = self.peek().text == ":"
                self.p += 1
                at = self.name()
                target = self.node("index", target.at, at, obj=target, name=self.t[at].text)
            self.bind("function", [target], [self.function(start, method)], start)
        elif word == "local":
            self.p += 1
            if self.word("function"):
                at = self.p
                self.p += 1
                decl = self.declare(self.name(), "function")  # Visible in its own body.
                value = self.function(at, False)
                decl.values.append(value)
                self.bindings.append(Binding("local function", decl, value, True, start))
            else:
                names = [self.name()]
                self.attribute()
                while self.op(","):
                    self.p += 1
                    names.append(self.name())
                    self.attribute()
                values = []
                if self.op("="):
                    self.p += 1
                    values = self.expressions()
                self.bind("local", [self.declare(at, "local") for at in names], values, start)  # Visible after.
        else:
            first = self.suffixed()
            if self.op("=", ","):
                targets = [first]
                while self.op(","):
                    self.p += 1
                    targets.append(self.suffixed())
                self.expect("=")
                if any(target.kind not in ("name", "index") for target in targets):
                    self.fail("cannot assign to an expression")
                self.bind("assign", targets, self.expressions(), start)
            elif first.kind not in ("call", "method"):
                self.fail("syntax error")

    def attribute(self):
        if self.op("<"):  # Lua 5.4 <const> and <close>.
            self.p += 1
            self.name()
            self.expect(">")

    def function(self, at: int, method: bool) -> Node:
        fn = Fn(at, self.fn)
        self.fns.append(fn)
        outer, self.fn = self.fn, fn
        self.scopes.append({})
        if method:
            fn.params.append(self.declare(at, "self"))
        self.expect("(")
        while not self.op(")"):
            if self.op("..."):
                self.p += 1
            else:
                fn.params.append(self.declare(self.name(), "param"))
            if not self.op(")"):
                self.expect(",")
        self.expect(")")
        self.block()
        self.expect("end")
        fn.end = self.p - 1
        self.scopes.pop()
        self.fn = outer
        fn.node = self.node("function", at, fn.end, body=fn)
        return fn.node

    def expressions(self) -> list[Node]:
        values = [self.expression()]
        while self.op(","):
            self.p += 1
            values.append(self.expression())
        return values

    def expression(self, limit: int = 0) -> Node:
        if self.op("-", "#") or self.word("not"):
            at, operator = self.p, self.peek().text
            self.p += 1
            operand = self.expression(12)
            left = self.node("unop", at, operand.end, name=operator, obj=operand)
        else:
            left = self.simple()
        while True:
            token = self.peek()
            operator = token.text if token.kind == "op" or token.text in ("and", "or") else None
            if operator not in BINARY or BINARY[operator][0] <= limit:
                return left
            self.p += 1
            right = self.expression(BINARY[operator][1])
            left = self.node("binop", left.at, right.end, name=operator, obj=left, key=right)

    def simple(self) -> Node:
        token, at = self.peek(), self.p
        if token.kind in ("number", "string") or self.word("nil", "true", "false"):
            self.p += 1
            return self.node("const", at, at, name=token.text)
        if self.op("..."):
            self.p += 1
            return self.node("vararg", at, at)
        if self.op("{"):
            return self.table()
        if self.word("function"):
            self.p += 1
            return self.function(at, False)
        return self.suffixed()

    def suffixed(self) -> Node:
        token, at = self.peek(), self.p
        if token.kind == "name" and token.text not in KEYWORDS:
            self.p += 1
            node = self.node("name", at, at, name=token.text, decl=self.resolve(token.text))
        elif self.op("("):
            self.p += 1
            inner = self.expression()
            self.expect(")")
            node = self.node("paren", at, self.p - 1, obj=inner)
        else:
            self.fail(f"unexpected {token.text!r}")
        while True:
            if self.op("."):
                self.p += 1
                at = self.name()
                node = self.node("index", node.at, at, obj=node, name=self.t[at].text)
            elif self.op("["):
                self.p += 1
                key = self.expression()
                self.expect("]")
                text = string_value(key.name) if key.kind == "const" and key.name else None
                node = self.node("index", node.at, self.p - 1, obj=node, key=key, name=text)
            elif self.op(":"):
                self.p += 1
                at = self.name()
                opener = self.p
                items = self.arguments()
                node = self.node("method", node.at, self.p - 1, obj=node, name=self.t[at].text, items=items,
                                 open=opener)
            elif self.op("(", "{") or self.peek().kind == "string":
                opener = self.p
                items = self.arguments()
                node = self.node("call", node.at, self.p - 1, obj=node, items=items, open=opener)
            else:
                return node

    def arguments(self) -> list[Node]:
        token, at = self.peek(), self.p
        if token.kind == "string":
            self.p += 1
            return [self.node("const", at, at, name=token.text)]
        if self.op("{"):
            return [self.table()]
        self.expect("(")
        if self.op(")"):
            self.p += 1
            return []
        items = self.expressions()
        self.expect(")")
        return items

    def table(self) -> Node:
        at, keys, values = self.p, [], []
        self.expect("{")
        while not self.op("}"):
            if self.op("["):
                self.p += 1
                key = self.expression()
                self.expect("]")
                self.expect("=")
            elif self.peek().kind == "name" and self.peek().text not in KEYWORDS and \
                    self.peek(1).kind == "op" and self.peek(1).text == "=":
                key = self.node("const", self.p, self.p, name=f'"{self.peek().text}"')
                self.p += 2
            else:
                key = None
            keys.append(key)
            values.append(self.expression())
            if not self.op(",", ";"):
                break
            self.p += 1
        self.expect("}")
        return self.node("table", at, self.p - 1, keys=keys, items=values)


def parse(module: Module) -> Parser:
    if module.parsed is None:
        module.parsed = Parser(module)
    return module.parsed


MODULES: dict[tuple[str, str], Module] = {}  # By path and source: a module is not changed once made.


def load(paths=None, replace=None) -> dict[str, Module]:
    """Every Lua file of the package: the runtime modules, and the startup file and
    policy configurations beside them (named without a directory)."""
    replace = replace or {}
    modules = {}
    for path in sorted(RUNTIME.rglob("*.lua")) + sorted(RUNTIME.parent.glob("*.lua")):
        name = path.relative_to(RUNTIME if path.is_relative_to(RUNTIME) else RUNTIME.parent).as_posix()
        source = replace.get(name, path.read_text(encoding="utf-8"))
        if (name, source) not in MODULES:
            MODULES[(name, source)] = Module(name, source)
        modules[name] = MODULES[(name, source)]
    return modules


@dataclass
class Result:
    reached: dict[tuple[str, str], list[str]]
    allowed: dict[str, str]
    unknown: list[str]
    sites: dict = field(default_factory=dict)  # (module, function) -> the calls that reach it: (module, Call)
    receivers: list = field(default_factory=list)  # Engine-method calls: (module, Call, path)


REVIEWED = BUILTINS | LIBRARIES | set(NATIVES) | set(ENGINE) | set(GLOBAL_MODULES)
# Tokens after a value that make it part of a longer expression.
CONTINUES = {".", ":", "(", "[", "{", ",", "..", "+", "-", "*", "/", "%", "^", "==", "~=", "<", ">", "<=", ">=",
             "and", "or"}


def assignment_targets(module: Module, at: int) -> list[tuple[int, int]]:
    """The chains `a`, `a.b`, `a[k]` ... of a statement-level assignment that starts
    at token `at` (a list of them, then "="), or none if there is no such one. An
    assignment of nil only (a rollback clearing names) binds nothing: none."""
    t, targets, j = module.tokens, [], at
    while True:
        k = j + 1
        while t[k].kind == "op" and t[k].text in (".", "["):
            k = module.closing(k) + 1 if t[k].text == "[" else k + 2
        targets.append((j, k - 1))
        if t[k].text == "," and t[k].kind == "op" and t[k + 1].kind == "name" and t[k + 1].text not in KEYWORDS:
            j = k + 1
            continue
        if t[k].text != "=" or t[k].kind != "op":
            return []
        while t[k + 1].text == "nil" and t[k + 1].kind == "name":
            if t[k + 2].text != ",":
                return [] if t[k + 2].text not in CONTINUES and t[k + 2].kind != "string" else targets
            k += 2
        return targets


def field_name(module: Module, first: int) -> str | None:
    """The first field of a chain: `a.b` or `a["b"]`."""
    t = module.tokens
    if t[first + 1].text == ".":
        return t[first + 2].text
    if t[first + 1].text == "[" and t[first + 2].kind == "string" and t[first + 3].text == "]":
        return t[first + 2].text[1:-1]
    return None


def rebindings(modules: dict[str, Module]) -> list[str]:
    """Reviewed names are trusted by name, so nothing in the package (reachable or
    not: all of it runs) may bind one to another value: a local, global, loop
    variable or function of that name (only `local x=x` keeps its value), a field
    of a reviewed library or of a global module table (each defines its own as
    M.<name>), or `_G.<name>` other than a module publishing itself."""
    found = []
    for module in modules.values():
        t = module.tokens

        def report(at: int, name: str):
            found.append(f"{module.path}:{t[at].line} rebinds the reviewed name {name}")

        for at, token in enumerate(t):
            if token.kind != "name":
                continue
            before = t[at - 1].text if at else ""
            if token.text == "local":
                if t[at + 1].text == "function":
                    if t[at + 2].text in REVIEWED:
                        report(at, t[at + 2].text)
                    continue
                names, j = [], at + 1
                while t[j].kind == "name" and t[j].text not in KEYWORDS:
                    names.append(t[j].text)
                    if t[j + 1].text != ",":
                        break
                    j += 2
                kept = (len(names) == 1 and t[j + 1].text == "=" and t[j + 2].text == names[0]
                        and t[j + 3].text not in CONTINUES and t[j + 3].kind != "string")
                for name in names:
                    if name in REVIEWED and not kept:
                        report(at, name)
            elif token.text == "function":
                head, following = t[at + 1].text, t[at + 2].text
                if before != "local" and t[at + 1].kind == "name" and following == "(" and head in REVIEWED:
                    report(at, head)
                elif head in LIBRARIES | set(GLOBAL_MODULES) and following in (".", ":"):
                    report(at, f"{head}.{t[at + 3].text}")
                elif head == "_G" and following == "." and t[at + 3].text in REVIEWED:
                    report(at, t[at + 3].text)
            elif token.text == "for":
                j = at + 1
                while t[j].kind == "name" and t[j].text not in KEYWORDS:
                    if t[j].text in REVIEWED:
                        report(j, t[j].text)
                    if t[j + 1].text != ",":
                        break
                    j += 2
            elif (token.text not in KEYWORDS and module.statement[at]
                  and before not in (".", ":", ",", "local", "for", "function")):
                for first, last in assignment_targets(module, at):
                    head, name = t[first].text, field_name(module, first) if last > first else None
                    if last == first and head in REVIEWED:
                        report(first, head)
                    elif last > first and head in LIBRARIES | set(GLOBAL_MODULES):
                        report(first, f"{head}.{name}" if name else f"{head}[...]")
                    elif head == "_G" and name in REVIEWED and GLOBAL_MODULES.get(name) != module.path:
                        report(first, name)
    return found


def method_fields(modules: dict[str, Module]) -> list[str]:
    """A reviewed method is trusted only on an engine value (receivers()); no table
    of ours has a field of that name either: no `{name=...}`, `{["name"]=...}`,
    `x.name=...`, `x["name"]=...` or `function x.name`/`function x:name`."""
    found = []
    for module in modules.values():
        t = module.tokens
        for at in range(1, len(t) - 2):
            token, before, after = t[at], t[at - 1].text, t[at + 1].text
            if token.kind == "name" and token.text in METHODS:
                name = token.text
                constructor = before in ("{", ",", ";") and after == "=" and not module.statement[at]
                assigned = before in (".", ":") and after == "="
                found_chain = module.chain_before(at)
                defined = before in (".", ":") and found_chain and found_chain[1] and t[found_chain[1] - 1].text == "function"
                if not (constructor or assigned or defined):
                    continue
            elif token.kind == "string" and before == "[" and after == "]" and t[at + 2].text == "=" \
                    and token.text[1:-1] in METHODS:
                name = token.text[1:-1]
            else:
                continue
            found.append(f"{module.path}:{token.line} gives a table a field named like the reviewed method {name}")
    return found


def chain_text(node) -> str | None:
    """a, a.b or a["b"].c as text, or None for anything else."""
    if not isinstance(node, Node):
        return None
    if node.kind == "name":
        return node.name
    if node.kind == "index" and node.name is not None:
        base = chain_text(node.obj)
        return None if base is None else f"{base}.{node.name}"
    return None


def chain_head(node: Node) -> Node:
    while node.kind == "index":
        node = node.obj
    return node


def is_nil(value) -> bool:
    return value == "nil" or isinstance(value, Node) and value.kind == "const" and value.name == "nil"


def runs_at_once(call: Node) -> bool:
    """A builtin that calls the function values it is given before it returns."""
    text = chain_text(call.obj)
    return text in CALLERS and chain_head(call.obj).decl is None


class Lookup:
    """What the parser found, by token: calls, names and functions, the variables
    each name uses, each module's table and the globals each module binds."""

    def __init__(self, modules: dict[str, Module]):
        self.modules = modules
        self.calls, self.names, self.fns, self.uses, self.bound, self.tables = {}, {}, {}, {}, {}, {}
        self.globals: dict[str, set[str]] = {}
        self.escapes_cache: dict[Fn, bool] = {}
        for path, module in modules.items():
            parsed = parse(module)
            for node in parsed.nodes:
                if node.kind in ("call", "method"):
                    self.calls[(path, node.open)] = node
                elif node.kind == "name":
                    self.names[(path, node.at)] = node
                    if node.decl is not None:
                        self.uses.setdefault(node.decl, []).append(node)
            for fn in parsed.fns:
                self.fns[(path, fn.at)] = fn
            for binding in parsed.bindings:
                target, value = binding.target, binding.value
                decl = target if isinstance(target, Decl) else target.decl if target.kind == "name" else None
                if decl is not None and isinstance(value, Node) and value.kind == "function" and \
                        (binding.single or binding.kind == "local function"):
                    self.bound[value] = decl  # A function literal held by one variable.
                if decl is not None and decl.owner is None and decl.name == module.table and \
                        binding.kind == "local" and isinstance(value, Node) and value.kind == "table":
                    self.tables[path] = decl
                name = self.global_name(target)
                if name is not None:
                    self.globals.setdefault(name, set()).add(path)

    @staticmethod
    def global_name(target) -> str | None:
        """The global a binding target names: `x` free, `_G.x` or `_G["x"]`."""
        if isinstance(target, Decl):
            return None
        if target.kind == "name" and target.decl is None:
            return target.name
        if target.kind == "index" and target.obj.kind == "name" and target.obj.decl is None and \
                target.obj.name == "_G":
            return target.name
        return None

    def line(self, path: str, at: int) -> int:
        return self.modules[path].tokens[at].line

    def escaping(self, fn: Fn) -> bool:
        """A nested function that can run after the call that made it returned:
        one stored, returned or passed on, unlike a local function only ever
        called by name or a literal that pcall, xpcall or table.sort runs at once."""
        if fn not in self.escapes_cache:
            node, escapes = fn.node, True
            parent = node.parent
            if fn.parent is None:
                escapes = False  # A function of the chunk: its free variables are the chunk's.
            elif parent is not None and parent.kind == "call" and node in parent.items and runs_at_once(parent):
                escapes = False
            elif parent is not None and parent.kind == "paren" and parent.parent is not None and \
                    parent.parent.kind == "call" and parent.parent.obj is parent:
                escapes = False  # (function() ... end)(...)
            elif node in self.bound:
                escapes = not all(use.parent is not None and use.parent.kind == "call" and use.parent.obj is use
                                  for use in self.uses.get(self.bound[node], []))
            self.escapes_cache[fn] = escapes
        return self.escapes_cache[fn]

    def escapes(self, inner: Fn | None, outer: Fn | None) -> bool:
        """Whether code in `inner` can run outside the activation of `outer` that made it."""
        fn = inner
        while fn is not None and fn is not outer:
            if self.escaping(fn):
                return True
            fn = fn.parent
        return fn is not outer


def only_tested(node: Node) -> bool:
    """A value only tested or typed: compared, negated, the left side of `and`, or
    the argument of type()."""
    parent = node.parent
    return parent is not None and (
        parent.kind == "binop" and (parent.name in ("==", "~=") or parent.name == "and" and parent.obj is node)
        or parent.kind == "unop"
        or parent.kind == "call" and parent.items == [node] and parent.obj.kind == "name"
        and parent.obj.decl is None and parent.obj.name == "type")


def metatables(modules: dict[str, Module]) -> list[str]:
    """No module gives a table of ours a metatable or reaches what FORBIDDEN and
    LOADERS name another way: none uses setmetatable, rawset, debug, setfenv,
    getfenv, newproxy or _ENV, by name or through _G; getmetatable only tests
    that a value has no metatable. string, math, table, _G and EngineGlobals are
    only indexed or tested, never held under another name (GLOBALS_ALIASES
    excepted); a global read by a computed name is only tested, and _G is looped
    over, only where GLOBAL_READS and GLOBAL_LOOPS list it."""
    found = []
    for module in modules.values():
        parsed = parse(module)
        targets = {id(binding.value): binding.target for binding in parsed.bindings}
        written = {id(binding.target) for binding in parsed.bindings}
        reads = loops = 0
        for node in parsed.nodes:
            where, parent = f"{module.path}:{module.tokens[node.at].line}", node.parent
            if node.kind == "index" and node.obj.kind == "name" and node.obj.decl is None and node.obj.name == "_G":
                if node.name in FORBIDDEN | LOADERS:
                    found.append(f"{where} uses {node.name} through _G")
                elif node.name is None and id(node) not in written and not only_tested(node):
                    reads += 1
                    if reads > GLOBAL_READS.get(module.path, 0):
                        found.append(f"{where} reads a global by a computed name")
                continue
            if node.kind != "name" or node.decl is not None:
                continue
            if node.name == "_G" and parent is not None and parent.kind == "binop" and parent.name == "or" \
                    and parent.key is node and module.path in GLOBALS_ALIASES:
                target = targets.get(id(parent))
                if target is not None and target.name == GLOBALS_ALIASES[module.path] and \
                        (isinstance(target, Decl) or target.kind == "name"):
                    continue  # The reviewed alias; bindings() checks its writes.
            if node.name == "_G" and parent is not None and parent.kind == "call" and parent.items == [node] \
                    and parent.obj.kind == "name" and parent.obj.decl is None and parent.obj.name == "pairs":
                loops += 1
                if loops > GLOBAL_LOOPS.get(module.path, 0):
                    found.append(f"{where} loops over _G, which reaches every global")
                continue
            if node.name in FORBIDDEN:
                found.append(f"{where} uses {node.name}, which can change what a table or a name runs")
            elif node.name == "getmetatable":
                call = parent if parent is not None and parent.kind == "call" and parent.obj is node else None
                test = call.parent if call is not None else None
                if not (test is not None and test.kind == "binop" and test.name in ("==", "~=")
                        and is_nil(test.key if test.obj is call else test.obj)):
                    found.append(f"{where} uses getmetatable other than to test that a value has none")
            elif node.name in SHARED and not (parent is not None and parent.kind == "index" and parent.obj is node
                                              or only_tested(node)):
                found.append(f"{where} holds the table {node.name} as a value, which lets it change under "
                             "another name")
        found += exact(module.path, "GLOBAL_READS", GLOBAL_READS, reads) + \
            exact(module.path, "GLOBAL_LOOPS", GLOBAL_LOOPS, loops)
    return found


def exact(path: str, name: str, reviewed: dict, count: int) -> list[str]:
    """A reviewed exception lists exactly the sites a module has: a site it no
    longer has must leave the list, so that no new one takes its place unseen."""
    listed = reviewed.get(path, 0)
    return [f"{path}: {name} lists {listed} for {count} such site(s)"] if count < listed else []


def loaded_code(modules: dict[str, Module]) -> list[str]:
    """No module loads code the check cannot read (LOADING excepted), and no
    native global takes a reviewed name: EEex_ExposeToLua names only the
    reviewed natives, once each, and a computed name is used only where
    COMPUTED_NATIVE_GLOBALS lists one."""
    found, exposed = [], {}
    protected = REVIEWED | set(INSTALLED) | {"EngineGlobals"}
    for module in modules.values():
        loads, computed = {}, 0
        for node in parse(module).nodes:
            where = f"{module.path}:{module.tokens[node.at].line}"
            if node.kind == "name" and node.decl is None and node.name in LOADERS:
                loads[node.name] = loads.get(node.name, 0) + 1
                if loads[node.name] > LOADING.get(module.path, {}).get(node.name, 0):
                    found.append(f"{where} uses {node.name}, which runs code this check cannot read")
            if node.kind != "call" or not (node.obj.kind == "name" and node.obj.decl is None
                                           and node.obj.name in NATIVE_GLOBALS):
                continue
            index = NATIVE_GLOBALS[node.obj.name] - 1
            argument = node.items[index] if index < len(node.items) else None
            name = string_value(argument.name) if argument is not None and argument.kind == "const" and \
                argument.name else None
            if name is None:
                computed += 1
                if computed > COMPUTED_NATIVE_GLOBALS.get(module.path, 0):
                    found.append(f"{where} makes a native global under a computed name")
            elif name in protected and not (node.obj.name == "EEex_ExposeToLua" and name in NATIVES):
                found.append(f"{where} makes the native global {name}, a reviewed name")
            elif name in NATIVES:
                exposed.setdefault(name, []).append(where)
        found += exact(module.path, "COMPUTED_NATIVE_GLOBALS", COMPUTED_NATIVE_GLOBALS, computed)
        for loader, listed in LOADING.get(module.path, {}).items():
            found += exact(module.path, f"LOADING {loader}", {module.path: listed}, loads.get(loader, 0))
    for name, places in exposed.items():
        if len(places) > 1:
            found += [f"{where} exposes {name}, which {len(places)} calls expose" for where in places]
    return found


MODULE, GLOBALS = ("module",), ("_G",)  # The abstract objects any module table and the globals table.
PASSES = {"assert", "select"}  # Builtins that return their arguments (assert all, select those after n).
READS = {"rawget", "next", "unpack", "table.unpack", "table.remove"}  # Builtins that return a field.


def key_names(key: Node | None, name: str | None) -> set[str]:
    """The field names a key can be: its name; "#" for a number or a boolean; for
    the key of `for k in pairs({...})` (never reassigned), that table's keys;
    otherwise "*", any name."""
    if name is not None:
        return {name}
    if key is None:
        return {"*"}
    if key.kind == "const":
        text = string_value(key.name)
        return {text} if text is not None else {"*"} if key.name[:1] in "\"'[" else {"#"}
    if key.kind == "unop" or key.kind == "binop" and key.name not in ("..", "and", "or"):
        return {"#"}
    decl = key.decl if key.kind == "name" else None
    if decl is not None and decl.kind == "for" and decl.position == 0:
        loop = decl.loop
        if decl.values == ["number"] or decl.values == ["iterated"] and len(loop) == 1 and \
                loop[0].kind == "call" and loop[0].obj.kind == "name" and loop[0].obj.decl is None and \
                loop[0].obj.name == "ipairs":
            return {"#"}
        if decl.values == ["iterated"] and len(loop) == 1 and loop[0].kind == "call" and \
                loop[0].obj.kind == "name" and loop[0].obj.decl is None and loop[0].obj.name == "pairs" and \
                len(loop[0].items) == 1 and loop[0].items[0].kind == "table":
            return set().union(*({"#"} if k is None else key_names(k, None) for k in loop[0].items[0].keys))
    return {"*"}


def module_values(module: Module, table: Decl | None):
    """Whether a value of the module may be a module table, by a may-points-to
    analysis of the module (flow- and context-insensitive, by field). A module
    table is its own table, a loaded or global module, or a configured field
    (R.policy, options.runtime: a field of that name of anything), and whatever
    those flow into: variables, parameters, returns, fields and keys of tables,
    loop variables and the builtins that pass values on; a module's field read by
    a computed key may be one too. Every other table, function, global, call
    result and parameter's outside value is an object of its own, so a module
    stored into one and read back is found. What other modules and native code
    put into a value is not seen (the docstring's assumption). Least fixpoint;
    cached on the module. Returns the test."""
    if module.values is not None:
        return module.values
    parsed = parse(module)
    own = {binding.value for binding in parsed.bindings if binding.target is table and binding.kind == "local"
           and isinstance(binding.value, Node) and binding.value.kind == "table"}
    configured = {chain.split(".")[-1] for _, chain in CONFIGURED} | {"runtime"}
    var: dict = {}  # Decl, ("vararg", fn) or "thrown" -> objects
    fields: dict = {}  # object -> {name, "#" or "*": objects}
    keys: dict = {}  # object -> the objects used as its keys
    memo: dict = {}
    changed = False

    def add(store: dict, key, values: set):
        nonlocal changed
        if values:
            target = store.setdefault(key, set())
            if not values <= target:
                target |= values
                changed = True

    def put(obj, name: str, values: set):
        add(fields.setdefault(obj, {}), name, values)

    def read(objects: set, names: set) -> set:
        out = {MODULE} if names & configured else set()
        for obj in objects:
            found = fields.get(obj, {})
            for name in names:
                if name == "*":
                    out.update(*found.values())
                    if obj == MODULE:
                        out.add(MODULE)  # Its configured fields, filled by the bootstrap.
                else:
                    out |= found.get(name, set()) | found.get("*", set())
                if obj == GLOBALS:
                    out.add(("global", name))
                    if name in GLOBAL_MODULES or name == "*":
                        out.add(MODULE)
        return out

    def key_objects(objects: set) -> set:
        return set().union(*(keys.get(obj, set()) for obj in objects))

    def value(node) -> set:
        if not isinstance(node, Node):
            return set()
        if node not in memo:
            memo[node] = set()  # A function's return that calls it again.
            memo[node] = evaluate(node)
        return memo[node]

    def evaluate(node: Node) -> set:
        kind = node.kind
        if kind == "name":
            if node.decl is None:
                return {GLOBALS} if node.name == "_G" else read({GLOBALS}, {node.name})
            out = set(var.get(node.decl, set()))
            return out | {("param", node.decl)} if node.decl.kind in ("param", "self") else out
        if kind == "index":
            return read(value(node.obj), key_names(node.key, node.name))
        if kind in ("call", "method"):
            return call(node)
        if kind == "table":
            return {MODULE} if node in own else {("table", node)}
        if kind == "function":
            return {("function", node)}
        if kind == "vararg":
            return {("vararg", node.where)} | var.get(("vararg", node.where), set())
        if kind == "paren":
            return value(node.obj)
        if kind == "binop" and node.name in ("and", "or"):
            return value(node.key) | (value(node.obj) if node.name == "or" else set())
        return set()  # A constant, or an operator's number, string or boolean.

    def invoke(functions: set, args: list, rest: set, node: Node) -> set:
        """Calls each function value: its parameters and varargs take the
        arguments (rest: what a last call or vararg supplies past them), and it
        gives what it returns; any other value gives an outside result."""
        out = set() if functions else {("call", node)}
        for obj in functions:
            if obj[0] != "function":
                out.add(("call", node))
                continue
            fn = obj[1].body
            for i, param in enumerate(fn.params):
                add(var, param, args[i] if i < len(args) else rest)
            add(var, ("vararg", fn), set().union(rest, *args[len(fn.params):]))
            for expr in parsed.returns.get(fn, []):
                out |= value(expr)
        return out

    def call(node: Node) -> set:
        items = [value(item) for item in node.items]
        rest = items[-1] if node.items and node.items[-1].kind in ("call", "method", "vararg") else set()
        if node.kind == "method":
            receiver = value(node.obj)
            return invoke(read(receiver, {node.name}), [receiver, *items], rest, node)
        callee, head = node.obj, chain_head(node.obj)
        builtin = chain_text(callee) if head.kind == "name" and head.decl is None else None
        thrown = var.get("thrown", set())
        if callee.kind == "name" and callee.name in LOADERS:
            return {MODULE}  # A loaded module, also through a parameter named like a loader.
        if builtin in PASSES:
            if builtin == "assert":
                add(var, "thrown", set().union(*items[1:]))
            return set().union(rest, *items[builtin == "select":])
        if builtin == "error":
            add(var, "thrown", set().union(*items[:1]))
            return set()
        if builtin in READS:
            names = key_names(node.items[1], None) if builtin == "rawget" and len(items) > 1 else {"*"}
            out = read(items[0], names) if items else set()
            return out | key_objects(items[0]) if builtin == "next" and items else out
        if builtin == "table.insert":
            for obj in (items[0] if len(items) > 1 else ()):
                put(obj, "#", items[-1])
            return set()
        if builtin in ("pcall", "xpcall"):
            functions, args = (items[0], items[1 + (builtin == "xpcall"):]) if items else (set(), [])
            out = invoke(functions, args, rest, node) | thrown
            if builtin == "xpcall" and len(items) > 1:
                out |= invoke(items[1], [thrown], set(), node)
            if any(obj[0] != "function" for obj in functions):
                out |= set().union(rest, *args)  # A builtin run this way may return its arguments.
            return out
        if builtin == "table.sort":
            if len(items) > 1:
                elements = read(items[0], {"*"})
                invoke(items[1], [elements, elements], set(), node)
            return set()
        if builtin in ("pairs", "ipairs"):
            return set().union(*items)  # An iterator, the table and nil.
        if builtin in BUILTINS or builtin is not None and builtin.split(".")[0] in LIBRARIES:
            return set()  # A number, string or boolean (getmetatable only tests that there is none).
        return invoke(value(callee), items, rest, node)

    def iterate(decl: Decl) -> set:
        """What a loop variable takes: the keys or values of the table pairs, ipairs
        or next walk, or what each step's call of any other iterator returns."""
        loop, first = decl.loop, decl.loop[0]
        builtin = first.obj.name if first.kind == "call" and first.obj.kind == "name" and \
            first.obj.decl is None and first.obj.name in ("pairs", "ipairs") and first.items else None
        if builtin or first.kind == "name" and first.decl is None and first.name == "next" and len(loop) > 1:
            source = value(first.items[0] if builtin else loop[1])
            if decl.position == 0:
                return set() if builtin == "ipairs" else key_objects(source)
            return read(source, {"*"}) if decl.position == 1 else set()
        return invoke(value(first), [value(expr) for expr in loop[1:]], set(), first)

    loops = [decl for decl in parsed.decls if decl.kind == "for" and decl.loop is not None]
    while True:
        changed = False
        memo.clear()
        for binding in parsed.bindings:
            target, bound = binding.target, binding.value
            values = value(binding.extra if bound == "extra" else bound)
            if isinstance(target, Decl):
                if target.kind not in ("for", "param", "self"):
                    add(var, target, values)
            elif target.kind == "name":
                if target.decl is not None:
                    add(var, target.decl, values)
                else:
                    put(GLOBALS, target.name, values)
            else:
                objects = value(target.obj)
                for name in key_names(target.key, target.name):
                    for obj in objects:
                        put(obj, name, values)
                if target.name is None:
                    for obj in objects:
                        add(keys, obj, value(target.key))
        for node in parsed.nodes:
            if node.kind == "table":
                obj = MODULE if node in own else ("table", node)
                for key, item in zip(node.keys, node.items):
                    names = {"#"} if key is None else key_names(key, None)
                    for name in names:
                        put(obj, name, value(item))
                    if "*" in names:
                        add(keys, obj, value(key))
            elif node.kind in ("call", "method"):
                value(node)  # Its arguments reach the parameters of the functions it calls.
        for decl in loops:
            add(var, decl, iterate(decl))
        if not changed:
            break
    module.values = lambda node: MODULE in value(node)
    return module.values


def canonical_function(binding: Binding) -> bool:
    """Binds a function the walk follows by this name (see Module.named), or nil."""
    if binding.kind in ("local function", "function"):
        return True
    if binding.kind in ("local", "assign"):
        return is_nil(binding.value) or binding.single and isinstance(binding.value, Node) \
            and binding.value.kind == "function"
    return False


def bindings(modules: dict[str, Module], result: "Result", lookup: Lookup) -> list[str]:
    """The walk follows functions by name, so every binding of a name it follows
    must bind that function. In each module, a name of its functions the walk
    follows (a local function, `function f`, `f=function`) is bound to nothing
    else: no parameter, loop variable, other local or value of that name. Its
    table is its one `local M={...}`. A field the walk follows (M.f reached, the
    configured fields) is written only by its module, through its table, with the
    function (or an alias of a local function of the chunk, or nil); the
    configured fields only in CONFIGURES. No module writes a computed field of a
    library or of a value that may be a module table (module_values()), writes
    into or rebinds EngineGlobals, binds _ENV, or writes a global
    by a computed name (COMPUTED_GLOBALS excepted); the callback globals are
    bound only where their hook installs them, or to nil. No parameter takes a
    reviewed name either."""
    found, computed = [], {}
    followed_fields: dict[str, set[str]] = {}
    for path, name in result.reached:
        table = modules[path].table
        if table and name.startswith(table + ".") and name.count(".") == 1:
            followed_fields.setdefault(name.split(".", 1)[1], set()).add(path)
    configured = {}
    for module_path, chain in [*CONFIGURED, *CONFIGURED_FUNCTIONS]:
        head, _, rest = chain.partition(".")
        configured.setdefault(rest.split(".")[0], set()).add(module_path)
    for module in modules.values():
        parsed, table = parse(module), lookup.tables.get(module.path)
        if module.table and table is None:
            found.append(f"{module.path} returns {module.table}, which is not its one local table")
        plain = {name for path, name in result.reached if path == module.path and "." not in name and ":" not in name}
        configure = module.named.get(CONFIGURES.get(module.path, ""), [])
        is_module = module_values(module, table)
        for binding in parsed.bindings:
            target, value = binding.target, binding.value
            at = target.at if isinstance(target, Decl) else target.at
            where = f"{module.path}:{module.tokens[at].line}"
            decl = target if isinstance(target, Decl) else target.decl if target.kind == "name" else None
            name = target.name if isinstance(target, Decl) or target.kind == "name" else None
            if name is not None:
                if name in plain and not canonical_function(binding):
                    found.append(f"{where} rebinds the followed function name {name}")
                if name == module.table and decl is not table or (decl is table and table is not None
                                                                  and binding.kind != "local" and not is_nil(value)):
                    found.append(f"{where} rebinds its module table {name}")
                if binding.kind == "param" and name in REVIEWED:
                    found.append(f"{where} rebinds the reviewed name {name}")
                if name == "_ENV":
                    found.append(f"{where} binds _ENV, which changes what every global name means")
            global_name = lookup.global_name(target)
            if global_name == "EngineGlobals":
                found.append(f"{where} rebinds EngineGlobals")
            if global_name in INSTALLED and not is_nil(value):
                home, expected = INSTALLED[global_name]
                head = chain_head(value) if isinstance(value, Node) else None
                # options: the hook's Install parameter, never reassigned; M: its module table.
                head_ok = head is not None and head.decl is not None and (
                    head.decl is table if head.name == module.table else head.decl.kind == "param"
                    and not head.decl.values)
                if not (module.path == home and isinstance(value, Node) and (
                        value.kind == "function" if expected is None else
                        chain_text(value) == expected and head_ok)):
                    found.append(f"{where} binds the callback global {global_name} other than where its hook "
                                 "installs it")
            if isinstance(target, Decl) or target.kind != "index":
                continue
            base, field_name = chain_head(target), target.name
            if base.kind == "name" and base.decl is None and base.name == "EngineGlobals":
                found.append(f"{where} writes into EngineGlobals")
                continue
            obj = target.obj
            if obj.kind == "name" and obj.decl is not None and obj.name == GLOBALS_ALIASES.get(module.path):
                if field_name is None:
                    found.append(f"{where} writes a global by a computed name through {obj.name}")
                elif field_name in REVIEWED or field_name in INSTALLED:
                    found.append(f"{where} rebinds the reviewed name {field_name} through {obj.name}")
                continue
            own = obj.kind == "name" and table is not None and obj.decl is table
            if field_name is None:
                if obj.kind == "name" and obj.decl is None and obj.name in LIBRARIES:
                    found.append(f"{where} writes a computed field of {obj.name}")
                elif is_module(obj):
                    text = chain_text(obj)
                    found.append(f"{where} writes a computed field of " +
                                 (f"the module table {text}" if text else "a module table"))
                elif obj.kind == "name" and obj.decl is None and obj.name == "_G" and not is_nil(value):
                    computed.setdefault(module.path, []).append(where)
                continue
            key = f"{module.table}.{field_name}"
            if own and (module.path, key) in result.reached:
                alias = binding.single and isinstance(value, Node) and value.kind == "name" and \
                    value.decl is not None and value.decl.kind == "function" and value.decl.owner is None
                if not (canonical_function(binding) or alias):
                    found.append(f"{where} rebinds the followed function {key}")
            elif own and (module.path, key) in [*CONFIGURED, *CONFIGURED_FUNCTIONS]:
                inside = any(f.start < at < f.end for f in configure)
                if not inside and not is_nil(value):
                    found.append(f"{where} writes the configured field {key} outside {CONFIGURES[module.path]}")
            elif not own and (field_name in followed_fields or field_name in configured):
                owners = sorted(followed_fields.get(field_name, set()) | configured.get(field_name, set()))
                found.append(f"{where} writes the field {field_name}, which the walk follows in {', '.join(owners)}")
    for path, sites in computed.items():
        if len(sites) > COMPUTED_GLOBALS.get(path, 0):
            found += [f"{where} writes a global by a computed name (reviewed: {COMPUTED_GLOBALS.get(path, 0)} "
                      f"in {path})" for where in sites]
    for path in COMPUTED_GLOBALS:
        found += exact(path, "COMPUTED_GLOBALS", COMPUTED_GLOBALS, len(computed.get(path, [])))
    return found


def engine_values(modules: dict[str, Module], result: "Result", lookup: Lookup):
    """Which variables hold only engine values: an engine userdata, a value read
    from one, or a plain value. Engine values come from EngineGlobals, the
    ENGINE_SOURCES and the actor and effect native code passes the callbacks; a
    field of one is one. A variable of the chunk lasts across calls, so all its
    bindings, anywhere, must be engine values ("always"). A variable of a
    function needs that only while a callback runs ("during"): a parameter takes
    what the reached calls pass it (nothing known if a builtin calls the function;
    a call through a value is reported by the walk), a local what its bindings
    give it. Code in
    a function that can outlive its maker sees its maker's variables "always",
    with parameters unknown. Greatest fixpoint: assume all, drop the failures."""
    decls = [decl for module in modules.values() for decl in parse(module).decls]
    always = {decl: decl.kind not in ("param", "self") for decl in decls}
    during = {decl: decl.kind != "self" for decl in decls}
    native, passed, unknown = set(), {}, set()
    for (path, name), sites in result.sites.items():
        for function in modules[path].named.get(name, []):
            fn = lookup.fns.get((path, function.start))
            if fn is None:
                continue
            if (path, name) in ROOTS:
                native.update(fn.params)
            for site_path, call in sites:
                if call.reference:
                    continue  # A value nothing in the callbacks calls: a call through it is reported.
                node = lookup.calls.get((site_path, call.at))
                if call.indirect or node is None or node.kind != "call":
                    unknown.update(fn.params)
                    continue
                items = node.items
                rest = "extra" if items and items[-1].kind in ("call", "method", "vararg") else "nil"
                for i, param in enumerate(fn.params):
                    passed.setdefault(param, []).append(items[i] if i < len(items) else rest)

    def engine(node, mode: str) -> bool:
        if isinstance(node, str):
            return node in ("nil", "number")
        kind = node.kind
        if kind == "const" or kind == "unop":
            return True
        if kind == "name":
            decl = node.decl
            if decl is None:
                return node.name == "EngineGlobals"
            if decl.owner is None or mode == "always" or lookup.escapes(node.where, decl.owner):
                return always[decl]
            return during[decl]
        if kind in ("index", "paren"):
            return engine(node.obj, mode)
        if kind == "call":
            return node.obj.kind == "name" and node.obj.decl is None and node.obj.name in ENGINE_SOURCES
        if kind == "binop":
            if node.name == "and":
                return engine(node.key, mode)
            if node.name == "or":
                return engine(node.obj, mode) and engine(node.key, mode)
            return True  # A comparison, arithmetic or concatenation gives a plain value.
        return False  # A function, table, vararg, method call or any other call.

    changed = True
    while changed:
        changed = False
        for decl in decls:
            if always[decl] and not all(engine(value, "always") for value in decl.values):
                always[decl] = False
                changed = True
            if not during[decl]:
                continue
            if decl.owner is None:
                ok = always[decl]
            elif decl.kind == "param":
                ok = (decl in native or decl in passed) and decl not in unknown and \
                    all(engine(value, "during") for value in passed.get(decl, []))
            elif decl.kind == "self":
                ok = False
            else:
                ok = all(engine(value, "always" if isinstance(value, Node)
                                and lookup.escapes(value.where, decl.owner) else "during")
                         for value in decl.values)
            if not ok:
                during[decl] = False
                changed = True
    return engine


def receivers(modules: dict[str, Module], result: "Result", lookup: Lookup) -> list[str]:
    """Each reached engine-method call is made on an engine value (engine_values)."""
    found, engine = [], engine_values(modules, result, lookup)
    for path, call, via in result.receivers:
        node, where = lookup.calls.get((path, call.at)), f"{path}:{call.line}"
        method = call.chain.rsplit(":", 1)[1]
        if node is None or node.kind != "method" or node.name != method:
            found.append(f"{where} method {call.chain} the parser did not see via {via}")
        elif not engine(node.obj, "during"):
            found.append(f"{where} method {call.chain} on a value that is not the engine's via {via}")
        else:
            result.allowed[f"<engine value>:{method}"] = METHODS[method]
    return found


def agrees(lookup: Lookup, module: Module, call: Call, kind: str) -> str | None:
    """The name a call starts with is the variable the walk resolves it to: a
    function of the module ("function"), its table ("table"), a global ("global")
    or a parameter nothing reassigns ("param"). None if so, else the problem."""
    node = lookup.names.get((module.path, call.head))
    if node is None:
        # A name that is no expression (a declared name, a constructor's key): the
        # walk follows it anyway, which only scans more.
        return None if call.reference else "the parser did not see this call"
    decl = node.decl
    if kind == "function":
        if decl is not None:
            return None  # bindings() keeps every variable of that name on the module's functions.
        if lookup.globals.get(node.name, set()) == {module.path}:
            return None  # The module's own global function; nothing else binds that global.
        return f"{node.name} here is a global, not the function of this module the walk follows"
    if kind == "table":
        return None if decl is not None and decl is lookup.tables.get(module.path) else \
            f"{node.name} here is not the module table"
    if kind == "global":
        kept = decl is not None and decl.kind == "local" and all(
            isinstance(value, Node) and value.kind == "name" and value.name == node.name and value.decl is None
            for value in decl.values) and decl.values  # `local tostring=tostring`
        return None if decl is None or kept else f"{node.name} here is a local, not the global"
    return None if decl is not None and decl.kind == "param" and not decl.values else \
        f"{node.name} here is not a parameter that keeps its value"


def walk(modules: dict[str, Module]) -> Result:
    queue = list(ROOTS)
    reached = {item: [f"{item[1]} ({item[0]}, native callback)"] for item in queue}
    sites = {item: [] for item in queue}
    allowed, unknown = {}, rebindings(modules) + method_fields(modules) + metatables(modules) + loaded_code(modules)
    result, lookup = Result(reached, allowed, unknown, sites), Lookup(modules)

    while queue:
        module_name, function_name = queue.pop()
        module = modules[module_name]
        functions = module.named.get(function_name)
        assert functions, f"{module_name} has no function {function_name}"
        via = reached[(module_name, function_name)]
        for function in functions:
            shadowed = module.locals_in(function)
            for call in module.calls_in(function):

                def reach(target_module: str, name: str, path: list[str], site=(module.path, call)):
                    key = (target_module, name)
                    sites.setdefault(key, []).append(site)
                    if key not in reached:
                        reached[key] = path + [f"{name} ({target_module})"]
                        queue.append(key)

                resolve(modules, module, call, shadowed, via, reach, allowed, unknown, result, lookup)
    unknown += bindings(modules, result, lookup) + receivers(modules, result, lookup)
    return result


def resolve(modules, module, call, shadowed, via, reach, allowed, unknown, result, lookup):
    chain, where = call.chain, f"{module.path}:{call.line}"
    path = " -> ".join(via)

    def follow(kind: str, target_module: str, name: str):
        problem = agrees(lookup, module, call, kind)
        if problem:
            unknown.append(f"{where} {chain}: {problem} via {path}")
        else:
            reach(target_module, name, via)

    if chain.startswith("<unresolved "):
        unknown.append(f"{where} {chain} via {path}")
        return
    if ":" in chain:
        method = chain.rsplit(":", 1)[1]
        if method in METHODS and not call.reference:
            result.receivers.append((module.path, call, path))  # Checked once the walk is done.
        elif not call.reference:
            unknown.append(f"{where} method {chain} via {path}")
        return
    parts = chain.split(".")
    head = parts[0]
    if head.startswith("<"):
        if not call.reference:
            unknown.append(f"{where} {chain} via {path}")
        return
    if head in shadowed:
        if not call.reference:
            unknown.append(f"{where} call through local value {chain} via {path}")
        return
    if len(parts) == 1 and chain in module.named:
        follow("function", module.path, chain)
    elif head == module.table and len(parts) == 2 and chain in module.named:
        follow("table", module.path, chain)
    elif (module.path, chain) in CONFIGURED_FUNCTIONS:
        follow("table" if head == module.table else "param", *CONFIGURED_FUNCTIONS[(module.path, chain)])
    elif head == module.table and len(parts) == 3 and (module.path, ".".join(parts[:2])) in CONFIGURED:
        target = modules[CONFIGURED[(module.path, ".".join(parts[:2]))]]
        name = f"{target.table}.{parts[2]}"
        if name in target.named:
            follow("table", target.path, name)
        elif not call.reference:
            unknown.append(f"{where} undefined {chain} via {path}")
    elif head == module.table and len(parts) == 2:
        if not call.reference:
            unknown.append(f"{where} undefined {chain} via {path}")
    elif head in GLOBAL_MODULES and len(parts) == 2:
        target = modules[GLOBAL_MODULES[head]]
        name = f"{target.table}.{parts[1]}"
        if name in target.named:
            follow("global", target.path, name)
        elif not call.reference:
            unknown.append(f"{where} undefined {chain} via {path}")
    elif head in REVIEWED and agrees(lookup, module, call, "global"):
        if not call.reference:
            unknown.append(f"{where} {chain}: {agrees(lookup, module, call, 'global')} via {path}")
    elif chain in NATIVES:
        allowed[chain] = NATIVES[chain][1]
    elif chain in ENGINE:
        allowed[chain] = ENGINE[chain]
    elif chain in BUILTINS or (head in LIBRARIES and len(parts) == 2):
        allowed[chain] = "Lua builtin"
    elif not call.reference:  # a value that is no function of ours is not followed
        unknown.append(f"{where} {chain} via {path}")


def test_native_callbacks_reach_only_reviewed_calls_that_cannot_end_an_actor_lifetime():
    result = walk(load())
    assert not result.unknown, "Unreviewed calls reachable from native callbacks:\n" + "\n".join(result.unknown)
    reached = {name for _, name in result.reached}
    # The walk is not vacuous: it reaches the bank's cap check, accounts, wire
    # copies and the hooks' native queries.
    for name in ("R.Snapshot", "R.Adopt", "R.ReconcileCHR", "settled", "identityOf", "stageNotices",
                 "M.Inspect", "M.PrepareWrite", "M.CompleteAward", "M.WireSnapshot", "M.Campaign",
                 "M.ChapterPhase", "M.AckReplaced", "M.NativeCap", "M.Plan", "M.Query", "M.AddressText"):
        assert name in reached, name
    natives = {name for name in result.allowed if name in NATIVES}
    assert natives == set(NATIVES), natives
    # The engine's owned SET path runs the game's setter; no XP callback reaches it.
    assert "CBMBank_WriterNativeOwnedSet" not in result.allowed
    assert ("xp-banking-native/bank_runtime.lua", "R.OwnedSet") not in result.reached


def test_the_native_bridges_call_exactly_these_runtime_callbacks():
    modules = load()
    for path, names in (("xp-banking-native/award_hooks.lua", CALLBACKS[:3]),
                        ("xp-banking-native/writer_hooks.lua", CALLBACKS[3:])):
        source = modules[path].source
        assert sorted(re.findall(r'CallbackAssembly\("(CBMBank_\w+)"', source)) == sorted(f"CBMBank_{n}" for n in names)
        for name in names:
            assert re.search(rf"CBMBank_{name}=options\.runtime\.{name}\b", source), (path, name)
    reset = modules["xp-banking-native/reset_hooks.lua"].source
    assert sorted(re.findall(r'CallbackAssembly\("(CBMBank_\w+)"', reset)) == sorted(f"CBMBank_{n}" for n in DUAL)
    for name in DUAL:
        assert re.search(rf"CBMBank_{name}=options\.runtime\.{name}\b", reset), name
    party = modules[PARTY].source
    assert re.findall(r'CallbackAssembly\("(CBMBank_\w+)"', party) == ["CBMBank_OnPartyReady"]
    assert "CBMBank_OnPartyReady=function(sprite) options.runtime.OnLoaded(sprite); return true end" in party
    cap = modules[CAP].source
    assert re.findall(r'GenLuaCall\("(CBMBank_\w+)"', cap) == ["CBMBank_BeforeNativeClamp"]
    assert "_G.CBMBank_BeforeNativeClamp=M.BeforeNativeClamp" in cap
    assert "M.snapshot,M.report=config.snapshot,config.report" in cap
    bootstrap = modules["xp-banking-native/bank_bootstrap.lua"].source
    assert "cap.Install({researchOnly=true,snapshot=runtime.Snapshot,report=runtime.Report,callbacks=callbacks})" in bootstrap
    assert "party.Install({researchOnly=true,dllPath=options.dllPath,profiles=pp,runtime=runtime,resetHooks=reset})" \
        in bootstrap
    # No other module of the package generates a native callback of the bank.
    generated = {path for path, module in modules.items()
                 if re.search(r'(CallbackAssembly|GenLuaCall)\("CBMBank_', module.source)}
    assert generated == {"xp-banking-native/award_hooks.lua", "xp-banking-native/writer_hooks.lua",
                         "xp-banking-native/reset_hooks.lua", PARTY, CAP}, generated


def test_configured_modules_and_native_exports_are_wired_as_declared():
    modules = load()
    bootstrap = modules["xp-banking-native/bank_bootstrap.lua"].source
    assert 'runtime.Configure(load("xp-banking/cbmbank_policy.lua"),account,wire,options.policy,rewardReceipts)' in bootstrap
    for variable, path in (("account", "xp-banking/native_account.lua"), ("wire", "xp-banking/cbmbank_store.lua"),
                           ("rewardReceipts", "xp-banking-native/dual_reward_receipts.lua")):
        assert f'local {variable}=load("{path}")' in bootstrap
    runtime = modules[BANK].source
    assert "function R.Configure(policy,account,wire,choice,receipts)" in runtime
    assert "R.policy,R.account,R.wire,R.choice=policy,account,wire,choice" in runtime
    assert "R.receipts=receipts" in runtime
    for name, path in GLOBAL_MODULES.items():
        assert re.search(rf"_G\.{name}\s*=\s*M\b", modules[path].source), name
    for name, (export, _) in NATIVES.items():
        sources = [m for m in modules.values() if f'"{name}"' in m.source and f'proc("{export}")' in m.source]
        assert len(sources) == 1, (name, export)
        module = sources[0]
        variable = exposed_variable(module, name)
        assert proc_variable(module, variable) == export, (name, variable)


def exposed_variable(module: Module, name: str) -> str:
    t = module.tokens
    for at in range(len(t) - 5):
        if t[at].text == "EEex_ExposeToLua" and t[at + 1].text == "(" and t[at + 3].text == "," \
                and t[at + 4].text == f'"{name}"':
            return t[at + 2].text
    raise AssertionError(f"{module.path} does not expose {name}")


def proc_variable(module: Module, variable: str) -> str:
    """The export a local was bound to by `local a,b=proc("X"),proc("Y")`."""
    t = module.tokens
    for at, token in enumerate(t):
        if token.text != "local":
            continue
        names, j = [], at + 1
        while t[j].kind == "name" and t[j].text not in KEYWORDS:
            names.append(t[j].text)
            if t[j + 1].text != ",":
                break
            j += 2
        if not names or t[j + 1].text != "=" or variable not in names:
            continue
        values, j = [], j + 2
        while t[j].text == "proc" and t[j + 1].text == "(" and t[j + 2].kind == "string" and t[j + 3].text == ")":
            values.append(t[j + 2].text.strip('"'))
            if t[j + 4].text != ",":
                break
            j += 5
        if len(values) == len(names):
            return values[names.index(variable)]
    raise AssertionError(f"{module.path}: {variable} is not bound to a native export")


SETTLED = "local function settled(state,identity)\n"


@pytest.mark.parametrize("injected,expected", [
    # A script action run at once can destroy or create creatures.
    ('EEex_Action_ExecuteResponseStringOnAIBaseInstantly("DestroySelf()",nil)',
     "EEex_Action_ExecuteResponseStringOnAIBaseInstantly"),
    ("local run=EEex_GameObject_Get;run(1)", "call through local value run"),
    ("state:Destroy()", "method state:Destroy"),
    ('CBMBank_WriterNativeOwnedSet("1","2","1")', "CBMBank_WriterNativeOwnedSet"),
    ("(EEex_GameObject_Get)(1)", "<expression call>"),
    ("pcall(EEex_LuaAction,1)", "EEex_LuaAction"),
    ('_G["EEex_LuaAction"](1)', "<expression call>"),
    ("CBMBank_Identity.Destroy(state)", "undefined CBMBank_Identity.Destroy"),
    # A function value a builtin calls: resolved like a call, or reported.
    ('pcall(_G["EEex_LuaAction"],1)', "unresolved callable argument 1 of pcall"),
    ("pcall(EEex_LuaAction or print,1)", "unresolved callable argument 1 of pcall"),  # Chosen by an expression.
    ('xpcall(_G["EEex_LuaAction"],function(e) return e end,1)', "unresolved callable argument 1 of xpcall"),
    ("xpcall(function() error('x') end,EEex_LuaAction)", "EEex_LuaAction"),  # The handler runs too.
    ('xpcall(function() end,_G["EEex_LuaAction"])', "unresolved callable argument 2 of xpcall"),
    ("pcall(state.run,1)", "call through local value state.run"),
    ("local run=EEex_LuaAction;pcall(run,1)", "call through local value run"),
    ("table.sort({},EEex_LuaAction)", "EEex_LuaAction"),
    ('table.sort({},_G["EEex_LuaAction"])', "unresolved callable argument 2 of table.sort"),
    ('("x"):gsub("x",EEex_LuaAction)', "EEex_LuaAction"),
    ('state.text:gsub("x",(EEex_LuaAction))', "unresolved callable argument 2 of state.text:gsub"),
    ('string.gsub("x","x",EEex_LuaAction)', "EEex_LuaAction"),
    ("pcall(table.sort,{},EEex_LuaAction)", "EEex_LuaAction"),  # A builtin caller run protected.
    ("pcall(pcall,EEex_LuaAction)", "EEex_LuaAction"),
    ("xpcall(pcall,print,EEex_LuaAction)", "EEex_LuaAction"),
    ("pcall(...)", "unresolved callable argument 1 of pcall"),
])
def test_an_unreviewed_call_in_a_reachable_helper_is_reported(injected, expected):
    # The check is not vacuous: one forbidden call in `settled`, which the cap
    # check runs from every XP callback, is found with its path.
    source = (RUNTIME / BANK).read_text(encoding="utf-8")
    assert source.count(SETTLED) == 1
    changed = source.replace(SETTLED, SETTLED + "    " + injected + "\n")
    result = walk(load(replace={BANK: changed}))
    assert any(expected in line and "settled" in line for line in result.unknown), result.unknown


BEFORE_AWARD = "function R.BeforeAward(sprite,effect)\n"


@pytest.mark.parametrize("injected", [
    # Codex's case: a destroying script action through a protected call of an
    # indexed global, then the same through both of xpcall's functions.
    'pcall(_G["EEex_Action_ExecuteResponseStringOnAIBaseInstantly"],"DestroySelf()",sprite)',
    'xpcall(_G["EEex_Action_ExecuteResponseStringOnAIBaseInstantly"],function(e) return e end,"DestroySelf()",sprite)',
    'xpcall(function() error("x") end,function() EEex_Action_ExecuteResponseStringOnAIBaseInstantly("DestroySelf()",sprite) end)',
    'xpcall(function() error("x") end,EEex_Action_ExecuteResponseStringOnAIBaseInstantly)',
])
def test_a_protected_destroying_call_in_a_callback_is_reported(injected):
    source = (RUNTIME / BANK).read_text(encoding="utf-8")
    assert source.count(BEFORE_AWARD) == 1
    result = walk(load(replace={BANK: source.replace(BEFORE_AWARD, BEFORE_AWARD + "    " + injected + "\n")}))
    assert any("R.BeforeAward" in line and ("EEex_Action_ExecuteResponseStringOnAIBaseInstantly" in line
                                            or "unresolved callable argument" in line) for line in result.unknown), \
        result.unknown


@pytest.mark.parametrize("injected,expected", [
    # Reviewed names and methods are trusted by name: no module may rebind them.
    ("local tostring=EEex_LuaAction", "rebinds the reviewed name tostring"),
    ("local pairs,ipairs=pairs,EEex_LuaAction", "rebinds the reviewed name ipairs"),
    ("local function type(x) EEex_LuaAction() end", "rebinds the reviewed name type"),
    ("function tostring(x) EEex_LuaAction() end", "rebinds the reviewed name tostring"),
    ("tostring=EEex_LuaAction", "rebinds the reviewed name tostring"),
    ("local a;a,tonumber=1,EEex_LuaAction", "rebinds the reviewed name tonumber"),
    ("tostring=nil or EEex_LuaAction", "rebinds the reviewed name tostring"),
    ("string.format=EEex_LuaAction", "rebinds the reviewed name string.format"),
    ('string["find"]=EEex_LuaAction', "rebinds the reviewed name string.find"),
    ("function string.lower() EEex_LuaAction() end", "rebinds the reviewed name string.lower"),
    ("_G.pairs=EEex_LuaAction", "rebinds the reviewed name pairs"),
    ('_G["select"]=EEex_LuaAction', "rebinds the reviewed name select"),
    ("_G.CBMBank_Identity={Query=EEex_LuaAction}", "rebinds the reviewed name CBMBank_Identity"),
    ("CBMBank_Identity.Query=EEex_LuaAction", "rebinds the reviewed name CBMBank_Identity.Query"),
    ("function CBMBank_Writer.Plan() EEex_LuaAction() end", "rebinds the reviewed name CBMBank_Writer.Plan"),
    ("CBMBank_WriterNativeQuery=EEex_LuaAction", "rebinds the reviewed name CBMBank_WriterNativeQuery"),
    ("EEex_GetUDAux=EEex_LuaAction", "rebinds the reviewed name EEex_GetUDAux"),
    ("for _,next in ipairs({}) do end", "rebinds the reviewed name next"),
    ("local text={get=EEex_LuaAction}", "gives a table a field named like the reviewed method get"),
    ('local text={["getAtLabels"]=EEex_LuaAction}', "gives a table a field named like the reviewed method getAtLabels"),
    ("local text={};text.GetAtOffset=EEex_LuaAction", "gives a table a field named like the reviewed method GetAtOffset"),
    ('local text={};text["get"]=EEex_LuaAction', "gives a table a field named like the reviewed method get"),
    ("local text={};function text:GetAtOffset() EEex_LuaAction() end",
     "gives a table a field named like the reviewed method GetAtOffset"),
])
def test_rebinding_a_reviewed_name_anywhere_is_reported(injected, expected):
    # Anywhere in the package, reachable or not: it all runs before the callbacks.
    source = (RUNTIME / CAP).read_text(encoding="utf-8")
    result = walk(load(replace={CAP: injected + "\n" + source}))
    assert any(expected in line and CAP in line for line in result.unknown), result.unknown


@pytest.mark.parametrize("kept", ["local tostring=tostring", "CBMBank_ResetNativeCap=nil",
                                  "CBMBank_ResetNativeQuery,CBMBank_ResetNativeCap=nil,nil",
                                  "local text={value=1};text.value=2", "_G.CBMBank_Other=1",
                                  "local t={};t.empty=getmetatable(t)==nil", "local kind=type(string)",
                                  "local s=string.format('%d',1)", 'local free=_G["CBM".."X"]==nil'])
def test_keeping_or_clearing_a_reviewed_name_is_no_rebinding(kept):
    source = (RUNTIME / CAP).read_text(encoding="utf-8")
    assert not walk(load(replace={CAP: kept + "\n" + source})).unknown


RETURN = "\nreturn R\n"
DESTROY = 'local function destroy(s) EEex_Action_ExecuteResponseStringOnAIBaseInstantly("DestroySelf()",s) end\n'


def walk_bank(before_return: str = "", in_before_award: str = "") -> Result:
    source = (RUNTIME / BANK).read_text(encoding="utf-8")
    assert source.endswith(RETURN) and source.count(BEFORE_AWARD) == 1
    source = source.replace(BEFORE_AWARD, BEFORE_AWARD + "    " + in_before_award + "\n")
    return walk(load(replace={BANK: source[:-len(RETURN)] + "\n" + before_return + RETURN}))


@pytest.mark.parametrize("injected,expected", [
    # Codex's case: the callbacks call what identityOf holds when they run, not
    # the helper the walk read.
    (DESTROY + "identityOf=destroy", "rebinds the followed function name identityOf"),
    # ... or a table that calls it through its metatable.
    (DESTROY + "identityOf=setmetatable({},{__call=function(_,s) destroy(s) end})",
     "rebinds the followed function name identityOf"),
    (DESTROY + "local identityOf=destroy", "rebinds the followed function name identityOf"),
    ("local identityOf,other=function() end,1", "rebinds the followed function name identityOf"),
    # A parameter or loop variable of that name is another value, also to a closure.
    ("local function wrap(settled) return function(state,identity) return settled(state,identity) end end",
     "rebinds the followed function name settled"),
    ("for _,settled in ipairs({}) do end", "rebinds the followed function name settled"),
    ("local function shadow(R) return function() R.Snapshot() end end", "rebinds its module table R"),
    ("R={Snapshot=print}", "rebinds its module table R"),
    ("R.Snapshot=EEex_LuaAction", "rebinds the followed function R.Snapshot"),
    # An alias of a local function is followed as that function.
    (DESTROY + "R.Snapshot=destroy", "EEex_Action_ExecuteResponseStringOnAIBaseInstantly via"),
    (DESTROY + 'R["Snap".."shot"]=destroy', "writes a computed field of the module table R"),
    ("R.policy={Campaign=print}", "writes the configured field R.policy outside R.Configure"),
])
def test_rebinding_a_function_the_walk_follows_is_reported(injected, expected):
    result = walk_bank(before_return=injected)
    assert any(expected in line and BANK in line for line in result.unknown), result.unknown


def test_a_call_that_reaches_a_global_instead_of_the_local_function_is_reported():
    # Called before its local declaration, the name is a global at the call.
    result = walk_bank(before_return="local function later() end", in_before_award="later(sprite)")
    assert any("later here is a global, not the function of this module the walk follows" in line
               for line in result.unknown), result.unknown


@pytest.mark.parametrize("injected,expected", [
    # A field the walk follows, written through another name for its table.
    ("local runtime={};runtime.Snapshot=print", f"writes the field Snapshot, which the walk follows in {BANK}"),
    ("local runtime={};function runtime.OnLoaded() end", f"writes the field OnLoaded, which the walk follows in {BANK}"),
    ("local options={};options.runtime=print", f"writes the field runtime, which the walk follows in {PARTY}"),
    ("local x={};x.policy=print", f"writes the field policy, which the walk follows in {BANK}"),
    # The callback globals native code calls.
    ("CBMBank_BeforeAward=print", "binds the callback global CBMBank_BeforeAward other than where its hook"),
    ('_G["CBMBank_OnPartyReady"]=print', "binds the callback global CBMBank_OnPartyReady other than where its hook"),
    ("local function x(tostring) return function() return tostring(1) end end", "rebinds the reviewed name tostring"),
    # Metatables, raw writes and other names for shared tables (Codex: __index and __call).
    ("local evil=setmetatable({},{__index=function() return print end})", "uses setmetatable"),
    ("local evil=_G.setmetatable({},{})", "uses setmetatable through _G"),
    ('local sm=_G["set".."metatable"]', "reads a global by a computed name"),
    ("for _,f in pairs(_G) do end", "loops over _G, which reaches every global"),
    ('rawset(_G,"tostring",print)', "uses rawset"),
    ("debug.sethook()", "uses debug"),
    ('getmetatable("").__index.upper=print', "uses getmetatable other than to test that a value has none"),
    ("local s=string;s.format=print", "holds the table string as a value"),
    ("local g=_G;g.tostring=print", "holds the table _G as a value"),
    ("local e=EngineGlobals", "holds the table EngineGlobals as a value"),
    ("EngineGlobals.g_pBaldurChitin=nil", "writes into EngineGlobals"),
    ('local name="format";string[name]=print', "writes a computed field of string"),
    ('local name="tostring";_G[name]=print', "writes a global by a computed name"),
    ("EngineGlobals={}", "rebinds EngineGlobals"),
    # What global names mean, code the check cannot read, globals made natively.
    ("local _ENV={}", "binds _ENV, which changes what every global name means"),
    ("_ENV.tostring=print", "uses _ENV"),
    ('load("tostring=EEex_LuaAction")()', "uses load, which runs code this check cannot read"),
    ('EEex_ExposeToLua(print,"tostring")', "makes the native global tostring, a reviewed name"),
    ('EEex_JITNearAsLuaFunction("CBMBank_BeforeAward",{})', "makes the native global CBMBank_BeforeAward"),
    ('EEex_ExposeToLua(print,"CBMBank_WriterNativeQuery")', "exposes CBMBank_WriterNativeQuery, which 2 calls expose"),
    ('local name="CBMX";EEex_ExposeToLua(print,name)', "makes a native global under a computed name"),
])
def test_a_write_that_could_change_what_the_walk_trusts_is_reported(injected, expected):
    # Anywhere in the package, reachable or not: it all runs before the callbacks.
    source = (RUNTIME / CAP).read_text(encoding="utf-8")
    result = walk(load(replace={CAP: injected + "\n" + source}))
    assert any(expected in line and CAP in line for line in result.unknown), result.unknown


def test_a_computed_write_into_a_module_the_bootstrap_loaded_is_reported():
    path = "xp-banking-native/bank_bootstrap.lua"
    source = (RUNTIME / path).read_text(encoding="utf-8")
    line = '    local runtime=load("xp-banking-native/bank_runtime.lua")\n'
    assert source.count(line) == 1
    result = walk(load(replace={path: source.replace(line, line + '    runtime["Snap".."shot"]=print\n')}))
    assert any(f"{path}:" in item and "writes a computed field of the module table runtime" in item
               for item in result.unknown), result.unknown


COMPUTED_SNAPSHOT = '["Snap".."shot"]=EEex_LuaAction'


@pytest.mark.parametrize("injected", [
    # A module table under another name: a variable, a parameter, a return or a field.
    "local R2=R;R2" + COMPUTED_SNAPSHOT,
    "local m=(assert(R));m" + COMPUTED_SNAPSHOT,
    "local m;local function set() m=R end;set();m" + COMPUTED_SNAPSHOT,
    "local function get() return R end;get()" + COMPUTED_SNAPSHOT,
    "local function two() return 1,R end;local _,m=two();m" + COMPUTED_SNAPSHOT,
    'local function w(t,k,v) t[k]=v end;w(R,"Snapshot",EEex_LuaAction)',
    'local function w(t,k,v) t[k]=v end;pcall(w,R,"Snapshot",EEex_LuaAction)',
    'local h={w=function(t,k,v) t[k]=v end};h.w(R,"Snapshot",EEex_LuaAction)',
    "local function f(...) local t={...};t[1]" + COMPUTED_SNAPSHOT + " end;f(R)",
    # ... held in a table, found through its fields, keys and loops, or the builtins.
    "local t={R};t[1]" + COMPUTED_SNAPSHOT,
    "local t={};table.insert(t,R);t[1]" + COMPUTED_SNAPSHOT,
    "local t={a={}};t.a.b=R;t.a.b" + COMPUTED_SNAPSHOT,
    "local q={};local p=q;p.x=R;q.x" + COMPUTED_SNAPSHOT,
    "local d={};local c={};c.f=d;c.f.x=R;d.x" + COMPUTED_SNAPSHOT,
    "for _,m in ipairs({R}) do m" + COMPUTED_SNAPSHOT + " end",
    "for k in pairs({[R]=true}) do k" + COMPUTED_SNAPSHOT + " end",
    "local _,m=next({R});m" + COMPUTED_SNAPSHOT,
    "table.sort({R,R},function(a,b) a" + COMPUTED_SNAPSHOT + ";return false end)",
    "xpcall(function() error(R) end,function(e) e" + COMPUTED_SNAPSHOT + " end)",
    "GLOBAL_X=R;GLOBAL_X" + COMPUTED_SNAPSHOT,
    'local w=R.wire;w["Wire".."Snapshot"]=EEex_LuaAction',
    # A configured field read by a computed key, and the hooks' global modules
    # under another name, also read through _G.
    'local w=R["wi".."re"];w["Wire".."Snapshot"]=EEex_LuaAction',
    'local m=CBMBank_Writer;m["Pl".."an"]=EEex_LuaAction',
    'local m=_G.CBMBank_Identity;m["Que".."ry"]=EEex_LuaAction',
    'local m=_G["CBMBank_".."Award"];m["Que".."ry"]=EEex_LuaAction',
    # A key that is not the literal keys of its loop may be any name, so every
    # field of that table may hold a module.
    "local load=function() return R end;local p={};for key,name in pairs(R.choice) do p[key]=load(name) end;"
    "p.saved={};p.saved" + COMPUTED_SNAPSHOT,
])
def test_a_computed_write_into_a_module_under_another_name_is_reported(injected):
    result = walk_bank(before_return=injected)
    assert any("writes a computed field of" in line and BANK in line for line in result.unknown), result.unknown


@pytest.mark.parametrize("kept", [
    # dual_bootstrap: modules under the literal keys of their loop, then a fresh
    # table of saved values beside them.
    "local load=function() return R end;local p={};for key,name in pairs({rules='a',skills='b'}) do "
    "p[key]=load(name) end;p.saved={};for name,value in pairs({x=1}) do p.saved[name]=value end",
    # identity_hooks: a copy of a profile table it is passed.
    "function R.Copy(profiles) local selected={};for name,value in pairs(profiles) do selected[name]=value end;"
    "selected.entries={};for name,value in pairs(profiles.entries) do selected.entries[name]=value end;"
    "return selected end",
    # dual_retired_picker: a deep copy of what it is passed, appended to.
    "local function clone(v) if type(v)~='table' then return v end;local c={};for k,x in pairs(v) do "
    "c[k]=clone(x) end;return c end;function R.Hold(list) local s={};s.items=clone(list);"
    "s.items[#s.items+1]=1;return s end",
    "R.cache={};R.cache['x'..'y']=1",
])
def test_a_computed_write_into_a_data_table_is_no_module_write(kept):
    assert not walk_bank(before_return=kept).unknown


def test_the_bootstraps_load_only_modules_this_check_reads():
    # bank_bootstrap's dofile helper `load` runs each module; it is called with the
    # package's own paths, dual_bootstrap's listed names, and handed only to
    # dual_bootstrap (progression.Preflight).
    modules = load()
    called, handed = [], []
    for path in ("xp-banking-native/bank_bootstrap.lua", "xp-banking-native/dual_bootstrap.lua"):
        for node in parse(modules[path]).nodes:
            if node.kind == "name" and node.name == "load" and node.decl is not None:
                parent = node.parent
                if parent is not None and parent.kind == "call" and parent.obj is node:
                    called.append((path, parent.items[0]))
                else:
                    handed.append((path, chain_text(parent.obj) if parent is not None and parent.kind == "call"
                                   else None))
    assert handed == [("xp-banking-native/bank_bootstrap.lua", "progression.Preflight")], handed
    literal = [string_value(item.name) for _, item in called if item.kind == "const"]
    computed = [(path, item) for path, item in called if item.kind != "const"]
    dual = modules["xp-banking-native/dual_bootstrap.lua"].source
    listed = re.search(r'for key,name in pairs\(\{(.*?)\}\)do\s*p\[key\]=load\("xp-banking-native/"\.\.name\.\."\.lua"\)',
                       dual, re.S)
    assert listed and len(computed) == 1 and computed[0][0] == "xp-banking-native/dual_bootstrap.lua"
    names = literal + [f"xp-banking-native/{name}.lua" for name in re.findall(r'=\s*"(\w+)"', listed.group(1))]
    assert len(names) > 30 and all(name in modules for name in names), [n for n in names if n not in modules]
    # The startup file loads the bootstrap and its configuration, both checked here.
    assert {"m_cbmbnk.lua", "cbmbkcfg.lua", "cbmbkchp.lua", "cbmbksoa.lua"} <= set(modules)
    startup = modules["m_cbmbnk.lua"].source
    assert 'Infinity_DoFile("CBMBKCFG")' in startup
    assert 'dofile(root.."/runtime/xp-banking-native/bank_bootstrap.lua")' in startup


def test_the_old_class_menu_runs_only_its_own_picker_names():
    # The menu's Lua (labels, enabled, clickable and action fragments) runs in the
    # globals too: it names only the picker's CBMDOldPicker* globals, rowNumber
    # and tostring, and assigns only CBMDOldPickerHlaPage.
    menu = (RUNTIME.parent / "cbmdold.menu").read_text(encoding="utf-8")
    fragments = re.findall(r'(?:\blua|\benabled|\baction)\s+"([^"]*)"', menu)
    assert len(fragments) > 40
    for fragment in fragments:
        tokens = lex(fragment)
        for at, token in enumerate(tokens):
            if token.kind != "name" or token.text in KEYWORDS or at and tokens[at - 1].text in (".", ":"):
                continue
            assert token.text.startswith("CBMDOldPicker") or token.text in ("rowNumber", "tostring"), fragment
            if at + 1 < len(tokens) and tokens[at + 1].text == "=":
                assert token.text == "CBMDOldPickerHlaPage", fragment


def test_a_callback_global_bound_through_a_reassigned_options_table_is_reported():
    path = "xp-banking-native/award_hooks.lua"
    source = (RUNTIME / path).read_text(encoding="utf-8")
    line = "    CBMBank_BeforeAward=options.runtime.BeforeAward\n"
    assert source.count(line) == 1
    result = walk(load(replace={path: source.replace(line, "    options={runtime={BeforeAward=print}}\n" + line)}))
    assert any(f"{path}:" in item and "binds the callback global CBMBank_BeforeAward" in item
               for item in result.unknown), result.unknown


def test_the_old_class_picker_writes_only_named_menu_globals_through_its_alias_of_g():
    path = "xp-banking-native/dual_retired_picker.lua"
    source = (RUNTIME / path).read_text(encoding="utf-8")
    alias = " globals=globals or _G\n"
    assert source.count(alias) == 1
    for injected, expected in (("globals.tostring=print", "rebinds the reviewed name tostring through globals"),
                               ('globals["CBM".."Bank_BeforeAward"]=print',
                                "writes a global by a computed name through globals"),
                               ("local other=globals or _G", "holds the table _G as a value")):
        result = walk(load(replace={path: source.replace(alias, alias + " " + injected + "\n")}))
        assert any(expected in line and path in line for line in result.unknown), (injected, result.unknown)


@pytest.mark.parametrize("defined", [
    # Codex's cases: a table of the bank whose `get` destroys, given by a computed
    # key or by a metatable outside the callbacks, called as if it were an engine
    # string. The walk never reads the function the call runs.
    DESTROY + 'evil={};evil["g".."et"]=function(_,s) destroy(s) end',
    DESTROY + "evil=setmetatable({},{__index=function() return function(_,s) destroy(s) end end})",
])
def test_a_table_of_the_bank_called_as_an_engine_string_is_reported(defined):
    result = walk_bank(before_return=defined, in_before_award="evil:get(sprite)")
    assert any("method evil:get on a value that is not the engine's via R.BeforeAward" in line
               for line in result.unknown), result.unknown


def test_an_engine_method_the_parser_did_not_see_is_reported():
    # The walk finds calls by token and the parser by grammar, over the same tokens,
    # so the two agree on every reached method; were they ever to part, the method
    # would be reported rather than trusted.
    modules = load()
    result = walk(modules)
    assert not result.unknown and result.receivers
    lookup = Lookup(modules)
    path, call, via = result.receivers[0]
    assert lookup.calls.pop((path, call.at)).kind == "method"
    found = receivers(modules, result, lookup)
    assert any(f"{path}:{call.line} method {call.chain} the parser did not see via" in line for line in found), found


@pytest.mark.parametrize("injected,expected", [
    # A table of ours given a `get` field by a computed key, then called as if it
    # were an engine string.
    ('local evil={};evil["g".."et"]=function(s) EEex_Action_ExecuteResponseStringOnAIBaseInstantly("DestroySelf()",s)'
     " end;evil:get(sprite)", "method evil:get on a value that is not the engine's"),
    # ... or by a metatable.
    ("local evil=setmetatable({},{__index=function() return print end});evil:get(sprite)",
     "method evil:get on a value that is not the engine's"),
    # A parameter some reached call feeds a table of ours.
    ("local function read(v) return v:get() end;read({})", "method v:get on a value that is not the engine's"),
    # A function that can outlive the callback sees its maker's parameters as anything.
    ("R.later=function() return sprite:get() end", "method sprite:get on a value that is not the engine's"),
    # Lua's string methods are not trusted: their receiver can be a table of ours.
    ("local text=tostring(sprite);text:upper()", "method text:upper via"),
    ('("%d"):format(1)', "method <expr>:format via"),
])
def test_an_engine_method_on_a_value_that_is_not_the_engines_is_reported(injected, expected):
    result = walk_bank(in_before_award=injected)
    assert any(expected in line and "R.BeforeAward" in line for line in result.unknown), result.unknown


def test_a_variable_of_the_chunk_that_any_code_sets_to_a_table_is_no_engine_receiver():
    # R.RetiredThreshold calls xpLevels:getAtLabels; xpLevels outlives every call,
    # so code that is not reached still decides what it holds.
    result = walk_bank(before_return="function R.Poison() xpLevels={} end")
    assert any("method xpLevels:getAtLabels on a value that is not the engine's" in line
               for line in result.unknown), result.unknown


def test_the_engine_methods_the_callbacks_call_are_on_engine_values():
    result = walk(load())
    assert {name for name in result.allowed if name.startswith("<engine value>:")} == \
        {f"<engine value>:{name}" for name in METHODS}
    calls = {(path, call.chain) for path, call, _ in result.receivers}
    # The resource reference of an effect, three calls below the dual-class
    # preview, comes from the actor native code passes (resref's parameter).
    assert ("xp-banking-native/dual_reward_receipts.lua", "v:get") in calls
    assert (BANK, "xpLevels:getAtLabels") in calls and (BANK, "game.m_sCurrentCampaign.m_pchData:get") in calls


def test_an_unreviewed_call_outside_the_callbacks_is_not_their_concern():
    # The startup fallback's script SET (m_cbmbnk.lua) and the notice display are
    # not reachable from the XP callbacks.
    result = walk(load())
    reached_modules = {module for module, _ in result.reached}
    assert "xp-banking-native/bank_notice.lua" not in reached_modules
    assert "xp-banking-native/bank_compat.lua" not in reached_modules
