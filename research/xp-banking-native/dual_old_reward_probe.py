"""Execute native level-up CLAB routing offline; never starts a game.

Native LevelUp, AddNewSpecialAbilities, AddClassAbilities pre-loop, class
selection, level access, and usability instructions execute. The CLAB loop is
observed as its exact half-open level interval, then skipped. Thus this proves
duplicate delivery requests, not execution of arbitrary AP_/GA_ resources.
Derived-stat lifecycle and external game/environment calls are explicit doubles.
"""
import json
import struct
from collections import deque
from pathlib import Path

import capstone
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *
from dual_proficiency_probe import load, EXES

ROOT = Path(__file__).parent
LAYOUTS = [(7,8,1,2,0x48,0x46),(7,16,2,1,0x46,0x48),
           (9,8,4,2,0x48,0x46),(9,64,2,4,0x46,0x48),
           (8,8,3,2,0x48,0x46),(8,32,2,3,0x46,0x48),
           (13,16,4,1,0x48,0x46),(13,64,1,4,0x46,0x48),
           (14,16,3,1,0x46,0x48),(14,32,1,3,0x48,0x46),
           (15,32,4,3,0x48,0x46),(15,64,3,4,0x46,0x48),
           (16,8,11,2,0x48,0x46),(16,128,2,11,0x46,0x48),
           (18,32,12,3,0x48,0x46),(18,256,3,12,0x46,0x48)]


def run():
    reports = []
    for version in EXES:
        pe, names, _ = load(version)
        base = pe.OPTIONAL_HEADER.ImageBase
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(base, pe.OPTIONAL_HEADER.SizeOfImage)
        uc.mem_write(base, pe.get_memory_mapped_image())
        arena = 0x2000000
        uc.mem_map(arena, 0x50000)
        actor, screen, before, projected = arena, arena+0x6000, arena+0x8000, arena+0xa000
        chitin, game, charscreen = arena+0xc000, arena+0xe000, arena+0x18000
        table, vtable, get_ai, stop = arena+0x1a000, arena+0x1b000, arena+0x1c000, arena+0x1c100
        stack = arena+0x48000-8
        q = lambda at, n: uc.mem_write(at, struct.pack('<Q', n))
        d = lambda at, n: uc.mem_write(at, struct.pack('<I', n))
        u64 = lambda at: struct.unpack('<Q', uc.mem_read(at, 8))[0]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
        level = names['CScreenCreateChar::LevelUp']
        add = names['CGameSprite::AddClassAbilities']
        level_ins = list(md.disasm(pe.get_data(level-base, 0x1c0), level))
        add_ins = list(md.disasm(pe.get_data(add-base, 0x34e), add))
        # Source-derived global chitin indirection. Do not guess relocated VAs.
        globals_found = []
        for instructions in (level_ins, add_ins):
            for i, ins in enumerate(instructions[:-1]):
                if ins.mnemonic == 'mov' and ins.op_str.startswith('rax, qword ptr [rip'):
                    nxt = instructions[i+1]
                    if '[rax + 0x10b8]' in nxt.op_str or '[rax + 0x1090]' in nxt.op_str:
                        at = ins.address+ins.size+ins.operands[1].mem.disp
                        q(at, chitin); globals_found.append(at)
        assert globals_found
        q(chitin+0x1090, game); q(chitin+0x10b8, charscreen)
        q(vtable+0x20, get_ai)
        # These offsets identify exact audited instructions in both pinned builds.
        interval_at = add+0x13d  # cmp esi,eax, after native usable-level routing
        finish_at = add+0x2d8   # loop exit: sprite virtual GetAI
        first_special_call = next(i.address for i in level_ins if i.mnemonic == 'call'
            and i.operands[0].type == capstone.CS_OP_IMM
            and i.operands[0].imm == names['CGameSprite::AddNewSpecialAbilities'])
        assert bytes(uc.mem_read(interval_at, 2)) == bytes.fromhex('3bf0')
        assert bytes(uc.mem_read(finish_at, 3)) == bytes.fromhex('498b07')
        boundary_names = ['CGameObjectArray::GetDeny', 'CRuleTables::GetClassAbilityTable',
            'CDerivedStats::CDerivedStats', 'CDerivedStats::operator=', 'CDerivedStats::~CDerivedStats',
            'CString::~CString', 'CGameSprite::AddNewSpellsPriest',
            'CGameSprite::FilterSpecialAbilities', 'DSOUND_FreeDeviceHandle',
            'CScreenCreateChar::CheckDropEquipment', 'CGameSprite::ProcessEffectList',
            '__security_check_cookie']
        boundaries = {names[n]: n for n in boundary_names}
        state = {}; recent = deque(maxlen=12)

        def hook(u, at, size, _):
            recent.append(hex(at))
            if at == stop: u.emu_stop(); return
            if at == first_special_call and state['project']:
                assert u.reg_read(UC_X86_REG_RDX) == before
                # Proposed scoped bridge behavior; not a tested installed hook.
                u.reg_write(UC_X86_REG_RDX, projected)
            if at == add:
                state['class'] = u.reg_read(UC_X86_REG_RDX) & 255
            if at == interval_at:
                start = u.reg_read(UC_X86_REG_RSI) & 0xffffffff
                if start & 0x80000000: start -= 0x100000000
                end = u.reg_read(UC_X86_REG_RAX) & 0xffffffff
                # Negative indexes fall back to the default cell, never a grant.
                state['intervals'].append((state['class'], max(0, start), end))
                u.reg_write(UC_X86_REG_RIP, finish_at); return
            if at != get_ai and at not in boundaries: return
            rcx, rdx = (u.reg_read(r) for r in (UC_X86_REG_RCX, UC_X86_REG_RDX))
            result = 0
            if at == get_ai: assert rcx == actor; result = actor+0x4b68
            else:
                name = boundaries[at]
                if name == 'CGameObjectArray::GetDeny':
                    assert rcx == 123; q(rdx, actor)
                elif name == 'CRuleTables::GetClassAbilityTable': result = table
                elif name == 'CDerivedStats::CDerivedStats': u.mem_write(rcx, b'\0'*0xca8); result = rcx
                elif name == 'CDerivedStats::operator=':
                    u.mem_write(rcx, bytes(u.mem_read(rdx, 0xca8))); result = rcx
                elif name == 'CGameSprite::AddNewSpellsPriest':
                    assert rcx == actor; state['priest_calls'] += 1
                elif name == '__security_check_cookie': result = u.reg_read(UC_X86_REG_RAX)
            rsp = u.reg_read(UC_X86_REG_RSP)
            u.reg_write(UC_X86_REG_RAX, result)
            u.reg_write(UC_X86_REG_RIP, u64(rsp)); u.reg_write(UC_X86_REG_RSP, rsp+8)

        uc.hook_add(UC_HOOK_CODE, hook)
        cases = []
        for layout in LAYOUTS:
            overall, flags, active, old, active_off, old_off = layout
            for label, old_before, old_after, active_before, active_after, reactivate in [
                ('ordinary-reactivation',10,10,1,11,True),
                ('combined-reactivation',10,11,1,12,True),
                ('combined-dormant',10,11,1,10,False),
                ('old-only-dormant',10,11,1,1,False),
                ('active-only-dormant',10,10,1,9,False),
            ]:
                for project in (False, True):
                    uc.mem_write(actor, b'\0'*0x5800); uc.mem_write(screen, b'\0'*0x1000)
                    uc.mem_write(before, b'\0'*0xca8); uc.mem_write(projected, b'\0'*0xca8)
                    q(actor, vtable); d(actor+0x568, flags); d(actor+0x4ea4, 1)
                    for typ in (actor+0x30, actor+0x4b68):
                        uc.mem_write(typ+0xb, bytes([overall])); d(typ+0xc, 123)
                    for derived in (actor+0x1120, actor+0x1dc8):
                        uc.mem_write(derived+active_off, bytes([active_after]))
                        uc.mem_write(derived+old_off, bytes([old_after]))
                    uc.mem_write(before+active_off, bytes([active_before]))
                    uc.mem_write(before+old_off, bytes([old_before]))
                    uc.mem_write(projected, bytes(uc.mem_read(before,0xca8)))
                    uc.mem_write(projected+old_off, bytes([old_after]))
                    q(screen+0x9a8,before); d(screen+0x9cc,int(reactivate))
                    state.update(project=project, intervals=[], priest_calls=0)
                    q(stack,stop)
                    for reg,value in ((UC_X86_REG_RSP,stack),(UC_X86_REG_RCX,screen),(UC_X86_REG_RDX,actor)):
                        uc.reg_write(reg,value)
                    try: uc.emu_start(level,stop,count=200000)
                    except Exception:
                        print(version,layout,label,project,list(recent)); raise
                    old_requests = [level for cls,lo,hi in state['intervals'] if cls == old for level in range(lo+1,hi+1)]
                    active_requests = [level for cls,lo,hi in state['intervals'] if cls == active for level in range(lo+1,hi+1)]
                    expected_old = list(range(1,old_after+1)) if reactivate else []
                    if not project and label == 'combined-reactivation':
                        expected_old = list(range(old_before+1,old_after+1))+expected_old
                    assert old_requests == expected_old, (version,layout,label,project,state,old_requests,expected_old)
                    assert active_requests == list(range(active_before+1,active_after+1)), (layout,label,state)
                    assert state['priest_calls'] == 1
                    cases.append(dict(overall=overall,old=old,active=active,scenario=label,
                        projected_first_before=project,old_requests=old_requests,active_requests=active_requests))
        reports.append(dict(version=version,cases=len(cases),results=cases))
    (ROOT/'dual-old-reward-routing-results.json').write_text(json.dumps(reports,indent=2)+'\n')
    return reports


if __name__ == '__main__':
    print(json.dumps([dict(version=r['version'],cases=r['cases']) for r in run()]))
