# Campaign XP banking: native interception evidence

Research date: 2026-10-09. Branch: `codex/campaign-xp-banking`, initial source
`d22427a`. Read the complete campaign-banking brief and mandatory BG compatibility
policy before this work. This note and `research/xp-banking-native/` are the only
owned changes. No game was launched, executable/resource/save modified, component
installed, commit made, or remote publication performed.

## Finding and remaining gate

There is a concrete native boundary **after party distribution and before the XP
write/cap/level check**: `CGameEffectXP::ApplyEffect` (opcode104). Instruction
inspection proves that party XP, individual AddXPObject and the traced utility
and kill award paths converge on per-character opcode104. This is stronger than
an inferred function name or a fabricated Lua callback.

Stock EEex v1.3.1 does **not** expose an unconditional pre-op104 award listener.
Its generic JIT hooks can implement the new boundary using a new loader pattern.
An **uninstalled observational prototype** is provided. It preserves the complete
native operation and records the proposed allowance separately. It does not bank
or suppress XP, and does not establish production readiness.

Still required before a functioning component: native bridge acceptance;
ChangeStat/direct-writer classification; pre-dual capture/reactivation semantics;
atomic award-plus-bank commit; save-bound persistence and release/disable recovery.
No claim of complete mod-writer coverage follows from opcode104 coverage.

## Inputs and reproducibility

The cached official sources are:

- `C:/tmp/scroll-hook-research-20261009/EEex`, official Bubb13/EEex commit
  `a6d21abe44e20509f5d0259ccc6c7e7f9d12b285` (v1.3.1).
- `C:/tmp/scroll-hook-research-20261009/InfinityLoader`, official
  Bubb13/InfinityLoader commit `817925caab3eb9cf600cfaf38853da8d30c28247`.

Two executables were opened as ordinary read-only files, never executed/copied:

| Engine | Read-only path | SHA-256 |
|---|---|---|
| BG2EE 2.6.6.0 | `<BG2EE 2.6.6.0 install>/Baldur.exe` | `fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580` |
| BG2EE 2.7.3.0 | `%USERPROFILE%/CEBG-Tests/Combined-20260908/game/Baldur.exe` | `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57` |

The executable format/version/ABI checks are memory-safety evidence, not arbitrary
resource-layout preconditions. They do not establish Linux/macOS/BGEE support.
SR does not enter this interception mechanism; no SR dependency is implied.

All addresses below are preferred-image virtual addresses for image base
`0x140000000`. Use RVA/signature relocation, never these absolute addresses at
runtime. `inspect_native.py` uses PE sections and official per-version
`EEex/loader/v2.x.x.x/bg2ee/function_names.db`. Some folded functions have multiple
names; e.g. the tiny class-byte getter is labeled `GetMoveScale` in the database.
Call-site operands, table dispatch and data flow were inspected rather than
trusting such names. Trailing jump-table data printed as instructions in a whole
function dump is not control-flow evidence. Candidate E8/E9 xrefs were checked in
their enclosing disassembly before relying on them.

## Native award paths (2.6.6.0)

Detailed disassembly is in `xp-banking-native/bg2ee-2.6.6-xp.txt`, `*-paths.txt`,
`*-writers.txt`, `*-extra.txt` and `*-class-utility.txt`.

`CInfGame::AddPartyXP` starts at `0x14026d900`. It first performs the native party
XP adjustment. At `0x14026da23`–`0x14026da34`, it divides the adjusted amount by
the living-party count: quotient goes to R15D, remainder to EBP. The count and
recipient loop exclude state bit `0x800` (dead). At `0x14026db0d`–`0x14026db1f`,
successive eligible members receive quotient+1 while remainder remains, otherwise
quotient. This is NOT a second division inside opcode104.

At `0x14026da37`, EDX=0x68 selects opcode104 for `ClearItemEffect`; the individual
share is written to its parameter1. The timing constant read at `0x1405906ec` is
1; the cleared modifier/parameter2 remains 0. `DecodeEffect` is called at
`0x14026db53`. `CMessageAddEffect` is queued at `0x14026dbc2` for the selected
actor. Thus the later104 receives the native individual entitlement, including
native adjustment, party size and remainder allocation.

| Award path | Concrete native evidence | Convergence |
|---|---|---|
| AddExperienceParty action164 | action jump-table resolves to `0x14015eca0`; call at `0x14015ecb4` | AddPartyXP → individual104 |
| AddExperiencePartyGlobal action165 | table → `0x14015ecd3`; helper calls AddPartyXP at `0x1401652e3` | same |
| AddXPObject action259 | table → `0x14015fa27`; `lea edx,[r14+0x69]` with R14=-1 selects104; fills amount and queues at `0x14015faef` | individual104, no party split |
| AddXP2DA action327, party-total branch | table → `0x14015ecc3`; call at `0x140165863` | AddPartyXP → individual104 |
| AddXP2DA individual branch | `0x1401658e3` constructs104 per selected actor; queues at `0x14016597f` | individual104 |
| Kill XP | `ApplyTriggers` calls at `0x140388384` / `0x14038841b`; latter loads slain sprite XP value at+0x56c, alongside RecordKill | AddPartyXP → individual104 |
| Learn/scribe spell | `CGameEffectLearnSpell::ApplyEffect`, call at `0x1401b7b0f` after XPBONUS lookup | AddPartyXP → individual104 |
| Pick locks | `PickLock`, calls at `0x1403a751f`, `0x1403a79ad` | AddPartyXP → individual104 |
| Remove traps | `RemoveTraps`, calls at `0x1403b083c`, `0x1403b0cb8`, `0x1403b1136` | AddPartyXP → individual104 |
| Direct SPL/EFF opcode104 | dispatches the same virtual ApplyEffect body | intercepted if actually applied |

Dialogue/script origin does not create a different meaning for these action IDs.
The dispatch table, rather than a rewrite of individual dialogues, identifies the
native implementation. Action names/IDs are corroborated by
[IESDP's BGEE action reference](https://gibberlings3.github.io/iesdp/scripting/actions/bgeeactions.htm#259).

**Origin limitation:** party/direct action construction generally uses source
ID=-1 and no resource. Kill, quest, utility and a mod's additive catch-up can be
indistinguishable once they become104. The probe deliberately reports that it
does not know the economic origin. Never infer "earned" solely from a positive
amount. An owned catch-up/release must supply separate context.

Also, AddPartyXP's observed division is unsigned. Negative party-total requests
therefore require explicit upstream origin handling; interpreting the resulting
positive shares as ordinary earnings is not justified. Negative direct104 remains
distinguishable by signed parameter1. This probe does not fix native loss behavior.

## Opcode104 boundary, native behavior and hook ABI

| Site | 2.6.6.0 RVA | 2.7.3.0 RVA |
|---|---|---|
| `CGameEffectXP::ApplyEffect` | `0x1cb160` | `0x1cb370` |
| Permanent-add write | `0x1cb203` | `0x1cb413` |
| CheckStatsChange cap lookup | `0x34e71c` | `0x34ed5c` |
| Single/multi derived cap write | `0x34e7b1` | `0x34edf1` |
| MakeDualClass active XP reset | `0x2a87c6` | `0x2a8e46` |
| ChangeStat XP branch | `0x372707` | `0x372d47` |

The complete 0xe0-byte ApplyEffect body is identical in both files, SHA-256
`b82b9164057049bbca1f2f7cbe5c98e3edf3595bc09aa1ab53ace0912e626c86`.
The 15-byte entry signature `4C8BC14C8BCA8B492085C90F848700` occurs exactly once
in each executable. The first 9 bytes are three complete, relocatable instructions:

```asm
mov r8, rcx              ; original effect
mov r9, rdx              ; target CGameSprite
mov ecx, [rcx+0x20]      ; modifier mode
```

At entry, RCX=effect and RDX=recipient. Mode0/timing1 reaches:

```asm
cmp dword ptr [r8+0x24], 1
mov eax, [r8+0x1c]       ; full individual amount
jne temporary_branch
add [rdx+0x570], eax     ; baseStats.m_xp, uint32 addition
mov eax, 1
mov dword ptr [r8+0x118], 1
mov dword ptr [r8+0x114], 1
ret
```

There are no calls/cap checks/failure returns in this scoped branch. The original
function sets done/repass and returns1. A full input amount can overflow uint32;
the proposed ledger must do its arithmetic before this write. Mode1 SET and mode2
percentage use separate branches; nonpermanent mode0 updates bonus XP instead.
They are not automatically ordinary earned XP.

`xp_probe.lua` uses existing EEex `EEex_HookShimFunctionMaintainOriginal` to retain
the 9-byte prologue and call the original function. It brackets that call with
**newly implemented** Lua observer functions. It is not using an imaginary stock
XP listener. The separate `loader-patterns.txt` is deliberately not installed.
No M_ loader, TP2 registration, TRA entry or public component was added.

The observer's event includes actor ID, signed amount, native base XP before and
after, proposed allowance, unchanged applied allowance, native result/done,
source effect metadata, and an honest origin-unclassified flag. SET/percentage/
loss/nonpermanent modes are recorded distinctly. It retains no actor/effect
userdata after the callback. A proposal cannot mutate the live effect via its
snapshot. Repeated after-callbacks cannot duplicate a diagnostic event.

The wrapper saves pointers/token/native return in its own shadow-space frame;
callback errors resume the unchanged native operation. Its observer-only default
therefore cannot lose an award because a policy callback failed. The checked
internal-write exclusion and reentrancy guard suppress diagnostic callbacks,
not native execution. They demonstrate an exclusion mechanism; they do not prove
the origin of unrelated engine/mod writes.

**Not implemented:** mutation of the allowance or bank. A mutating version must
commit usable XP and bank coherently. Reducing the native amount then invoking a
fallible Lua bank commit is not acceptable. A prepared non-throwing commit or
rollback design, native bridge execution, and save-bound atomicity tests remain
required. An ordinary pcall or a successful synthetic policy test is not that proof.

## Cap, multiclass, dual and serialization findings

The reviewed native cap is **derived-XP-only** at this point. The base header is
at sprite+0x560, with `m_xp` at+0x10 (absolute sprite+0x570). `CDerivedStats::Reload`
copies base XP into derived+0x60 (`0x140153769`/`0x14015376c`). CheckStatsChange
then limits sprite+0x1180 and calls `GetNextLevel` at `0x14034e7ce`, before the
level-up-availability flag is set. It does not subtract excess from base XP.

`CRuleTables::GetXPCap` reads the installed class XP-cap table and takes a further minimum
against a native global ceiling (`0x140249c87`–`0x140249c92`). This is another
reason not to assume that ending this component's cap guarantees visible room.

Marshal at `0x140361184` copies sprite+0x560 into CRE offset8, including base XP
at CRE0x18. Unmarshal at `0x140379de9` copies that header back. In these examined
paths, the native derived cap does not itself discard base XP at serialization.
Do not claim native caps require CDTweaks2090 solely to prevent this hypothesized
loss; that assertion is contradicted by the inspected writes. This is an offline
path finding, not a tested save/load guarantee across all mods/other writers.

`CDerivedStats::GetXP` at `0x1401532c0` reads the one character-total XP value.
For a normal two-class character it returns floor(total/2); for three classes,
floor(total/3). It does not write separate class XP totals. The single/multiclass
cap branch compares the character-total derived XP once. No full cap per class
and no extra party/class division belongs in banking.

For a dual, `GetXP` returns active XP for the active class; for the retired class
it calls `GetLevelField`, then `GetNextLevelXP` using that level. CheckStatsChange
at `0x14034e762`–`0x14034e7b1` sums active XP and that **retired-level threshold**.
If the sum exceeds the cap, the active derived allowance becomes cap minus that
threshold (or zero when the threshold already exhausts the cap).

MakeDualClass at `0x1402a87c6` sets base XP to zero directly. Exact pre-dual XP,
including progress beyond the last retired-class threshold, cannot be recovered
from the later class/level fields. A bank must capture the transition beforehand
and keep the pre/post-dual accounting distinct; it must not reinterpret retired
XP as active XP or create room merely because the active field reset.

`CAIObjectType::GetActiveInactiveClasses` selects the two class IDs using original-
class flags (base+0x08) and the composite class ID. It does **not** inspect levels
or prove that old abilities have reactivated. Therefore unequal returned class
IDs are a dual identity discriminator, not a dormant/active discriminator. Exact
reactivation timing/native callback was not established by this initial review.
The follow-up [deferred-progression investigation](2026-10-09-dual-class-deferred-progression.md)
identifies the actual level comparison and standard level-up screen boundaries.
Christopher subsequently approved immediate duals with separate old/new banks;
the earlier bank-locking proposal is not selected.

### Exact vanilla dual-cap example

A Fighter with **80,000 actual XP at level 7**, dual-classing under a **161,000
total cap**, is charged **64,000 retired XP** by the reviewed native calculation.
The new class can therefore reach **97,000 usable XP**. It is not limited to
81,000 based on the actual 80,000, and it does not receive the full 161,000.

This is not inferred from the misleading `GetNextLevelXP` function name:

- `GetXP` reads the retired level byte at `0x140153334` and passes that value
  unchanged to GetNextLevelXP at `0x14015333d`.
- GetNextLevelXP retains R8B in EDI at `0x140242af6`, formats it with `%d` at
  `0x140242b5d`–`0x140242b6d`, then looks up that exact XPLEVEL column at
  `0x140242b92`. There is no increment: level 7 selects column `7`.
- Clean `data/Default.bif` XPLEVEL.2DA (override bypassed) has FIGHTER column7 =
  64,000 and column8 = 125,000. Resource SHA-256:
  `f5f70503cfe92348056b940b90a29f0f408a125c64ab0d6aa0ec685adc2ffac0`.
  The concise extraction evidence is `xp-banking-native/vanilla-dual-example.json`;
  exact disassembly is `bg2ee-2.6.6-dual-threshold.txt`.
- CheckStatsChange subtracts that retired threshold from the cap at
  `0x14034e795`–`0x14034e7b1`. MakeDualClass had already reset the old 80,000 base
  XP to zero. Its 16,000 progress above the level-7 minimum is not retained as a
  separate native class-XP balance.
- GetNextLevel's dual branch at `0x1402426c9`–`0x1402426e3` selects the active
  subclass and jumps to its single GetNextLevelSubClass call at `0x140242919`.
  Ordinary later XP/level-ups do not advance the retired class: Fighter7 stays7.
  An external respec/level writer is outside that normal progression claim.

Consequently a separately protected 50,000 pre-dual excess and 200,000 post-dual
excess cannot be treated as interchangeable by an exact ledger. Native mechanics
provide no place where the retired class later spends that 50,000 to advance.
Christopher subsequently chose to retain the 50,000 for the old class and assign
the 200,000 only to the new class, with release within later campaign limits.
That choice is recorded in the [handover](2026-10-09-campaign-xp-banking.md).
The research has not implemented the required deferred old-class progression.

## Bypasses and minimal additional hooks

Action370 ChangeStat calls `CGameSprite::SetAtOffset` at `0x140160983`.
The stat44 table entry resolves to `0x140372707`: RCX=actor, R8D=value,
R9D=modifier; R9D==1 adds directly to base XP, all other modes set it. This bypasses
opcode104 and must get a separate typed writer hook or be explicitly unsupported.
237/238/620 catch-up must compare their intended target against the appropriate
existing entitlement, not the capped visible XP. Their current SET must not be
reclassified as another earned award.

Other direct Lua/native writes to `m_baseStats.m_xp`, imports/respecs, character
creation and externally implemented catch-up are not covered. A complete scan of
all arbitrary external writers is impossible from this engine binary; declare
supported native award paths and a writer API/context contract instead.

Existing opcode403 is not a lossless first-award installation strategy: native
`EEex.cpp:4514` registers per-recipient screen effects; `4608` looks up that actor's
vector and `4610` returns before Lua when it is empty. Polling to attach403 can
miss the first award. Existing lists-resolved listeners run after effect-list
resolution, and cannot replace the proven pre-write boundary. The global native
entry shim avoids per-actor attachment timing altogether when installed at startup.

The next bounded production-design work is to validate this observer's ABI in a
separately approved disposable run, add independently guarded ChangeStat and
pre-dual writer contexts, then integrate a coherent transactional bank operation.
Keep source metadata separate from economic origin: an additive104 alone cannot
tell a quest reward from a catch-up grant.

## Checks actually run and shortest remaining native check

`check-results.json`: both exact executable signatures and relocatable prologues
passed; actual opcode104 machine instructions passed **15 emulator cases per
build (30 total)**. Cases include boundary crossings, consecutive/huge amounts,
unsigned overflow, loss/zero, SET/percentage and nonpermanent mode. These execute
only the 224-byte leaf in Unicorn with synthetic actor/effect memory, not the game.
Lua5.1 parsed the observer and passed snapshot/proposal/error/exclusion/reentrancy/
repeated-callback/mode classification checks. Absent native capabilities rejected
installation. No engine bridge was assembled/executed; no runtime/save/transition
acceptance is claimed. Mod XP multipliers, UI, SR/non-SR runtime combinations and
multiplayer were not run.

Reproduce from the worktree (the analysis dependencies are isolated under C:/tmp):

```powershell
$env:PYTHONPATH='C:/tmp/xp-banking-analysis-deps'
python research/xp-banking-native/check_probe.py `
  "<BG2EE 2.6.6.0 install>/Baldur.exe" `
  "%USERPROFILE%/CEBG-Tests/Combined-20260908/game/Baldur.exe"
```

Dependency versions: Capstone5.0.9, pefile2024.8.26, Unicorn2.1.4 and installed
Lupa Lua5.1. Only textual disassembly/check results are retained in this research
directory; no game executable or resource blob is included.

Separately authorized native acceptance should load the observer before any game
actor awards and inspect its bounded records: award7 to parties of1/3/6; individual
award7; one kill, scribe, lock, trap and AddXP2DA; direct104 ADD/SET/loss; consecutive
cap-crossing awards. Verify base/derived XP independently and unchanged native
awards. Verify first award after load/recruitment, callback failure, and guarded
own-write suppression. Only after that should a mutating transactional prototype
be tested, with save/reload and dual/release cases added. No invocation or game
launch is authorized by this checklist.

## Alternative: native base XP as the retained ledger

**Credible simpler candidate for ordinary single/multiclass characters; not an
accepted complete implementation.** The preceding evidence changes the original
storage assumption: ordinary native awards add the full entitlement to saved base
XP, while the native cap limits derived XP. A second persistent balance is not
intrinsically required to retain ordinary excess XP. Keeping base XP untouched and
applying a save-bound campaign restriction at the existing cap boundary would
avoid dividing awards again, copying each award into another ledger, or issuing
an XP grant when a cap rises. A transition would change the allowed derived value
and refresh effects; it would not credit base XP again.

Additional 2.6.6 instruction evidence is retained in
`xp-banking-native/bg2ee-2.6.6-native-bank.txt` and `*-native-bank-writers.txt`:

| Consumer/path | Evidence | Implication |
|---|---|---|
| Character experience text and Lua stats | GetExperience sets R13=sprite+0x1120 at `0x140353e46`; its XP calls pass that derived object. GetExperienceEntry sets RBX=sprite+0x1120 at `0x140354cb6`, calls GetXP at `0x140354d52`, and formats the result at `0x140354e2c`–`0x140354e3b`. UpdateLuaStats calls GetExperience at `0x140380883`. | Inspected native display reports capped usable XP; a separate status would report retained excess from base XP. UI mods reading base directly need separate review. |
| Level-up button | Copies sprite+0x1120 into a temporary derived object at `0x1402a84d1`–`0x1402a84dd`, then calls GetNextLevel at `0x1402a84f1`. | Availability follows derived XP. The function also has independent spell-choice checks; its return is not exclusively an XP test. |
| Next-level calculation | GetNextLevel carries its supplied derived pointer to GetNextLevelSubClass; the latter calls derived GetXP at `0x1402429f8`. | Native single/multiclass class splitting and rounding remain in force. Retained base XP is not used directly here. |
| OnLevelUp base write | R15=sprite+0x560 at `0x1402bb560`; `cmp`/`cmovb`/`mov` at `0x1402bb7a8`–`0x1402bb7b1` writes max(requested XP, existing base XP). | This examined write does not truncate a higher retained base value to the cap. Complete cancel/commit and alternate UI acceptance remain necessary. |
| Script XP equality/greater/less branches | The three adjacent native branches at `0x140156f29` onward call GetXPCap, read derived XP (or derived active+retired for duals), then take the minimum before comparison: e.g. `0x14015704f`–`0x14015705d`. | Native script XP comparisons already hide excess. Catch-up that computes a delta from these capped results can repeatedly over-credit, so owned writers must use the entitlement-aware contract. |
| Character export | Calls ordinary sprite Marshal at `0x140270219`; reads base XP at `0x1402702a0` (dual adds retired threshold) to choose CHR version. | No base-XP cap truncation was found in this export path. Imported copies/clone ownership remain policy and acceptance concerns. |
| Expansion catch-up | UpdatePartyToExpansionPack reads base XP at `0x140295d5e` / `0x140296ada`; dual branches add retired threshold. | The inspected native comparisons include retained XP, but this is not proof that EET/mod catch-up scripts do. |

The cap site has usable actor context. CheckStatsChange calls
GetCharacterPortraitNum at `0x14034e6fe` and skips its cap/availability block when
the result is -1. At the GetXPCap return (`0x14034e721`), RBX is the actor and EAX
is the existing effective cap. A new, guarded call-site interception could reduce
that result for eligible saved campaign state before the native dual/single/multi
clamp. This is a concrete next hook candidate, **not a stock EEex API or a hook
implemented by this research prototype**. A global GetXPCap replacement is less
well scoped: its explicit argument is a CAIObjectType rather than an actor, and
other script consumers also call it. Preserve installed lower caps by taking the
minimum with the native result; ending this component's restriction must return
control to the existing native/mod cap. Do not silently raise XPCAP or its global
ceiling.

Remaining design/acceptance work for this alternative:

- Save-bound campaign progression, policy, actor eligibility and grandfathered
  existing usable progress are still needed even if ordinary excess needs no
  custom balance. Do not lower an existing character's progress merely by enabling
  a new derived cap. Test first award/load/join and effect recalculation timing.
- Base XP is a net native value, not an immutable lifetime-earnings history.
  Absolute SET, percentage changes, intended losses, catch-up and respec can
  overwrite it. Owned 237/238/620 and EET/mod writers need explicit coordination.
  Direct additive ChangeStat naturally increases this candidate's retained value;
  its bypass of104 then ceases to be a storage-loss issue, while source semantics
  and destructive SET still matter.
- MakeDualClass still resets base XP. Capture exact pre-reset XP and keep the
  pre-dual retained portion assigned to the old class under the approved policy.
  The retired level threshold cannot reconstruct it. The simple one-field model
  alone cannot satisfy dual retention or distinguish pre/post-dual earnings.
- Temporary XP effects, level drain, imported/exported characters, previews,
  summons and clones need ownership/usable-XP rules. A status balance must not
  infer permanent earnings from a temporary derived adjustment. Native portrait
  membership alone is not a complete anti-clone policy.
- Native base storage remains uint32. The verified additive opcode wraps at its
  limit; some display conversions use signed integers. This alternative does not
  provide an unbounded ledger or justify accepting pathological overflow.
- Remove/release/disable must refresh derived stats and explain any retained
  lower cap. Existing base XP makes ordinary recovery simpler but does not release
  separately retained pre-dual state or resolve unknown/newer policy payloads.

Recommendation for lead design: evaluate this native-storage alternative before
building a mutating per-award two-ledger transaction. Keep the op104 observer for
measurement and exceptional-writer classification. The new display/level-up
inspection above was bounded to 2.6.6; the already verified identical104 and cap
sites do not establish every 2.7.3 display/level-up path. No native cap hook was
installed and no whole-engine save/transition test was run. The subsequently
approved dual allocation is documented separately; this is not its implementation.

## Supplemental campaign evidence

`MoveToCampaign` calls `SetCampaign` at `0x140283749` and aborts on failure.
SetCampaign's success branch writes the supplied CString to CInfGame+0x9760 at
`0x14028c686`, setting the adjacent campaign flag. The source header exposes
`CInfGame.m_sCurrentCampaign` (`Baldur-v2.6.6.0.h:48440`). Campaign save/load binding
was not independently completed in this focused XP review; root owns that proof.
