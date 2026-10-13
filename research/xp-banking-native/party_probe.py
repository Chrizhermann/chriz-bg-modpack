"""Read-only party boundary audit and actual native membership execution.

No game is launched. External list/string/UI callees are inert fixtures; the
AddCharacterToParty body, inline object lookup and membership writes are real.
"""
import json
from pathlib import Path
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn import x86_const as x
from identity_probe import DEFAULT_CACHE, DEFAULT_EXES, MD

ROOT = Path(__file__).resolve().parent


def check(pe, start, site, name, actor_id, party_size):
    base = pe.OPTIONAL_HEADER.ImageBase
    game, sprite, stack, stop = 0x3000000, 0x4000000, 0x5000000, 0x5010000
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    uc.mem_write(base, pe.get_memory_mapped_image())
    uc.mem_map(game, 0x10000); uc.mem_map(sprite, 0x10000); uc.mem_map(stack, 0x20000)
    uc.mem_write(game+0x6600, b'\xff'*24); uc.mem_write(game+0x6618, b'\xff'*24)
    uc.mem_write(game+0x6630, party_size.to_bytes(2, 'little'))
    uc.mem_write(sprite+0x570, (12345).to_bytes(4, 'little'))
    instructions = list(MD.disasm(pe.get_data(start, 0x2F0), base+start))
    cookie_call=max(ins.address for ins in instructions if ins.mnemonic=='call')
    # Independently selected inline object-array fields by the instructions
    # which read them, not guessed offsets into the global object registry.
    for ins in instructions:
        if ins.mnemonic == 'cmp' and ins.op_str.startswith('word ptr [rip'):
            address = ins.address+ins.size+ins.operands[0].mem.disp
            uc.mem_write(address, (10).to_bytes(2, 'little'))
        if ins.mnemonic == 'lea' and ins.op_str.startswith('rax, [rip'):
            array = ins.address+ins.size+ins.operands[1].mem.disp
            if actor_id >= 0:
                index = (actor_id >> 16) & 0x7FFF
                uc.mem_write(array+index*16, (actor_id & 0xFFFF).to_bytes(2, 'little'))
                uc.mem_write(array+index*16+8, sprite.to_bytes(8, 'little'))
    uc.reg_write(x.UC_X86_REG_RCX, game)
    uc.reg_write(x.UC_X86_REG_RDX, actor_id & 0xFFFFFFFF)
    uc.reg_write(x.UC_X86_REG_R8, 0xFFFF)
    uc.reg_write(x.UC_X86_REG_RSP, stack+0x8008)
    uc.mem_write(stack+0x8008, stop.to_bytes(8, 'little'))
    events = []

    def instruction(cpu, address, size, _):
        ins = next(MD.disasm(bytes(cpu.mem_read(address, size)), address))
        if ins.mnemonic != 'call': return
        if address == base+site:
            assert ins.operands[0].imm == base+name
            assert cpu.reg_read(x.UC_X86_REG_RCX) == sprite
            members = [int.from_bytes(cpu.mem_read(game+0x6618+i*4,4),'little') for i in range(6)]
            assert actor_id in members
            assert int.from_bytes(cpu.mem_read(sprite+0x570,4),'little') == 12345
            events.append((address, members.index(actor_id)))
        # This audit concerns the caller's actual placement. The separate DLL
        # test invokes the native bridge; no external method is emulated here.
        # MSVC's security-cookie helper has its special preserving ABI. The
        # method's BOOL return has already been set when it reaches that call.
        if address != cookie_call: cpu.reg_write(x.UC_X86_REG_RAX, 0)
        cpu.reg_write(x.UC_X86_REG_RIP, address+size)

    uc.hook_add(UC_HOOK_CODE, instruction)
    uc.emu_start(base+start, stop, count=2000)
    assert uc.reg_read(x.UC_X86_REG_RIP) == stop
    expected = actor_id >= 0 and party_size < 6
    assert len(events) == int(expected)
    assert uc.reg_read(x.UC_X86_REG_RAX) == int(expected)
    assert int.from_bytes(uc.mem_read(sprite+0x570,4),'little') == 12345
    if expected: assert events[0][1] == party_size


def main():
    profiles, report = {}, {}
    for version, executable in DEFAULT_EXES.items():
        pe = pefile.PE(str(executable)); base = pe.OPTIONAL_HEADER.ImageBase
        folder = 'v2.6.6.0' if version == '2.6' else 'v2.7.3.0'
        names = {}
        for line in (DEFAULT_CACHE/folder/'bg2ee/function_names.db').read_text().splitlines():
            address, _, name = line.partition('\t')
            if address.startswith('0x'): names[int(address,16)-base] = name
        start = next(at for at, name in names.items() if name == 'CInfGame::AddCharacterToParty')
        name = next(at for at, name in names.items() if name == 'CGameSprite::GetNameRef')
        instructions = list(MD.disasm(pe.get_data(start, 0x2F0), base+start))
        calls = [i.address-base for i in instructions if i.mnemonic=='call' and i.operands[0].imm==base+name]
        assert len(calls)==1
        site=calls[0]
        profiles[version] = {'gameTimestamp':pe.FILE_HEADER.TimeDateStamp,
            'gameSize':pe.OPTIONAL_HEADER.SizeOfImage, 'site':site, 'target':name,
            'caller':start, 'callerBytes':pe.get_data(start,0x2F0).hex(),
            'targetBytes':pe.get_data(name, min(at for at in names if at>name)-name).hex()}
        for actor_id in [-1,0x10002,0x20003]:
            for size in [0,3,5,6]: check(pe,start,site,name,actor_id,size)
        report[version]={'native_membership_boundaries':12,'xp_unchanged':True}
    def lua(v):
        if isinstance(v,str): return json.dumps(v)
        if isinstance(v,int): return str(v)
        return '{'+','.join('['+json.dumps(k)+']='+lua(x) for k,x in v.items())+'}'
    (ROOT/'party_profiles.lua').write_text('-- Generated by party_probe.py; audited native caller and callee.\nreturn '+lua(profiles)+'\n')
    (ROOT/'party-check-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
