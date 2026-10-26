"""Read-only dispatch/lifetime ABI evidence from the actual pinned images.
Never maps executable memory or invokes any native function.
"""
import bisect,collections,hashlib,json,re,struct
from pathlib import Path
import capstone,pefile
from generate_decode_profiles import EXES,EEEX,signature
ROOT=Path(__file__).resolve().parent

def audit(version,path,digest):
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
    pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
    rows=[(int(a,16),n) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines()
          for a,_,n in [line.partition('\t')] if a.startswith('0x')]
    ordered=sorted({a for a,_ in rows});named={n:a for a,n in rows}
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
    def body(address):return pe.get_data(address-base,ordered[ordered.index(address)+1]-address)
    def instructions(address):return list(cs.disasm(body(address),address))
    dispatch=[named['CGameEffectCastSpell::ApplyEffect'],named['CGameEffectCastSpellPoint::ApplyEffect']]
    ctors={a for a,n in rows if n=='CAIAction::CAIAction'}
    message_default=[]
    for address in dispatch:
        code=instructions(address);matches=[]
        for i,ins in enumerate(code):
            if ins.mnemonic!='call' or ins.operands[0].type!=capstone.x86.X86_OP_IMM or ins.operands[0].imm not in ctors:continue
            prior=code[max(0,i-3):i]
            # Both actual bodies explicitly construct the inline action at
            # message+10h; their temporary stack actions have other locations.
            if any(p.mnemonic=='lea' and p.op_str in ('rcx, [r14 + 0x10]','rcx, [rsi + 0x10]') for p in prior):
                matches.append((ins.address+ins.size,ins.operands[0].imm))
        assert len(matches)==1;message_default.append(matches[0])
    assert message_default[0][1]==message_default[1][1]
    default=message_default[0][1]
    # Resolve the actual FireSpell vtable by its independently named Run and
    # subtype slots, not by a nearest folded-destructor symbol label.
    tables=[]
    for ins in instructions(dispatch[0]):
        if ins.mnemonic!='lea' or ins.operands[0].reg!=capstone.x86.X86_REG_RAX or ins.operands[1].type!=capstone.x86.X86_OP_MEM:continue
        mem=ins.operands[1].mem
        if mem.base!=capstone.x86.X86_REG_RIP:continue
        address=ins.address+ins.size+mem.disp
        data=pe.get_data(address-base,56)
        if len(data)==56:
            slots=struct.unpack('<7Q',data)
            if slots[3]==named['CMessageFireSpell::GetMsgSubType'] and slots[6]==named['CMessageFireSpell::Run']:
                tables.append((address,slots))
    assert len(tables)==1
    table,slots=tables[0];destroy=slots[0]
    definitions=[('apply146',dispatch[0]),('apply148',dispatch[1]),('action_default',default),
                 ('add_message',named['CMessageHandler::AddMessage']),('fire_message_run',slots[6]),('fire_message_destroy',destroy)]
    result=dict(version=version,sha256=digest,message_action_constructor_returns=[pc-base for pc,_ in message_default],
        fire_message_vtable_rva=table-base,fire_message_vtable_slots=[pc-base for pc in slots],functions=[])
    for label,address in definitions:
        end=ordered[ordered.index(address)+1]
        rf=next(r for r in pe.DIRECTORY_ENTRY_EXCEPTION if r.struct.BeginAddress==address-base)
        unwind_rva=rf.struct.UnwindData;head=pe.get_data(unwind_rva,4);count=head[2]
        unwind=pe.get_data(unwind_rva,4+((count+1)&~1)*2)
        result['functions'].append(dict(label=label,rva=address-base,size=end-address,prefix=body(address)[:32].hex(),
            unwind=unwind.hex(),signature=signature(pe,label,address-base,end-address),
            instructions=[f'{ins.address-base:08x} {ins.mnemonic} {ins.op_str}' for ins in instructions(address)[:16]]))
    result['fire_message_destroy_body']=[f'{ins.address-base:08x} {ins.mnemonic} {ins.op_str}' for ins in instructions(destroy)]
    result.update(witness_evidence(pe,base,rows,ordered,instructions,dispatch,default,message_default))
    result.update(action_value_evidence(pe,base,rows,base+result['empty_sentinel_global'],result['string_functions']))
    return result

def reachable(pe,base,entries,bounds):
    """Instructions reachable from the entries by direct control flow and MSVC
    jump tables (32-bit image-relative entries indexed off an image-base
    register), so tables and padding between bodies are never decoded."""
    image=pe.get_memory_mapped_image();cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    starts=sorted(bounds);code={};work=list(entries)
    def bound(address):
        i=bisect.bisect_right(starts,address)-1
        return bounds[starts[i]] if i>=0 else (address,address)
    while work:
        address=work.pop();path=[]
        while address not in code:
            ins=next(cs.disasm(image[address-base:address-base+16],address),None)
            if ins is None:break
            code[address]=ins;path=path[-8:]+[ins];m,op=ins.mnemonic,ins.op_str
            if m.startswith('j') and op.startswith('0x'):
                if m=='jmp':address=int(op,16);continue
                work.append(int(op,16))
            elif m=='jmp':
                table=[p for p in path if p.mnemonic=='mov' and '*4 + ' in p.op_str and p.op_str.split(', ')[1].startswith('dword ptr [')]
                if not op.startswith('qword') and table:
                    rows=base+int(table[-1].op_str.split('*4 + ')[1].rstrip(']'),16);begin,end=bound(address)
                    while True:
                        target=base+struct.unpack('<I',image[rows-base:rows-base+4])[0]
                        if not begin<=target<end:break
                        work.append(target);rows+=4
                break
            elif m in ('ret','int3','ud2','hlt'):break
            address+=ins.size
    return code

def string_block_sites(pe,base,rows,nil):
    """Every reachable locked operation in the image, attributed to its
    function. Inline CString code must name the shared empty string (nil: its
    pointer and header globals and the block itself) to initialise or skip
    it, so a function that both locks and names it, or locks a data-0Ch
    operand, must be a CString member. Also every member storing into a block
    header."""
    ordered=sorted({a for a,_ in rows});names=dict(rows)
    text=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text')
    t0,t1=base+text.VirtualAddress,base+text.VirtualAddress+text.Misc_VirtualSize
    bounds={base+r.struct.BeginAddress:(base+r.struct.BeginAddress,base+r.struct.EndAddress) for r in pe.DIRECTORY_ENTRY_EXCEPTION}
    for i,a in enumerate(ordered):
        if t0<=a<t1 and a not in bounds:bounds[a]=(a,ordered[i+1] if i+1<len(ordered) else t1)
    code=reachable(pe,base,bounds,bounds)
    def start(address):return ordered[bisect.bisect_right(ordered,address)-1]
    locked={};naming=set();members=set()
    for address,ins in sorted(code.items()):
        op=ins.op_str;owner=start(address)
        if '[rip ' in op:
            disp=op.split('[rip ')[1].split(']')[0].replace(' ','')
            if address+ins.size+int(disp,16) in nil:naming.add(owner)
        if ins.mnemonic.startswith('lock '):locked.setdefault(owner,[]).append(ins)
        elif names[owner].startswith('CString::') and op.startswith('dword ptr [') and ins.mnemonic in ('mov','inc','dec','add','sub','and','or','xor'):
            inside=op[len('dword ptr ['):].split(']')[0]
            if inside.split(' ')[0] not in ('rsp','rbp','rip') and inside.endswith((' - 0xc',' - 8',' - 4')):members.add(owner)
    strings=[];others={}
    for owner,found in sorted(locked.items()):
        if names[owner].startswith('CString::'):
            members.add(owner);strings+=[dict(rva=i.address-base,function=names[owner],instruction=f'{i.mnemonic} {i.op_str}') for i in found]
        else:
            assert owner not in naming and not any(' - 0xc]' in i.op_str for i in found),names[owner]
            others[names[owner]]=others.get(names[owner],0)+len(found)
    covered=sum(ins.size for ins in code.values())
    return strings,[dict(rva=a-base,name=names[a]) for a in sorted(members)],others,covered

def witness_evidence(pe,base,rows,ordered,instructions,dispatch,default,message_default):
    """Facts the value-carried CAIAction witness relies on (action_witness.hpp)."""
    named={n:a for a,n in rows}
    def text(code):return [f'{ins.address-base:08x} {ins.mnemonic} {ins.op_str}' for ins in code]
    def target(ins):return ins.operands[0].imm if ins.operands and ins.operands[0].type==capstone.x86.X86_OP_IMM else None
    def rip(ins):return ins.address+ins.size+ins.operands[1].mem.disp
    # Native construction stores the static empty sentinel, read from the same
    # global as the other two empty strings, into m_source (+80h).
    ctor=instructions(default);sentinels={}
    for prior,store in zip(ctor,ctor[1:]):
        if prior.mnemonic=='mov' and prior.op_str.startswith('rax, qword ptr [rip + ') and store.mnemonic=='mov' and \
           store.op_str in ('qword ptr [rbx + 0x60], rax','qword ptr [rbx + 0x68], rax','qword ptr [rbx + 0x80], rax'):
            sentinels[store.op_str.split('+ ')[1][:4]]=rip(prior)
    assert set(sentinels)=={'0x60','0x68','0x80'} and len(set(sentinels.values()))==1
    # The exact owned message: the audited constructor call builds its action
    # at message+10h, so the witness field is message+90h. Its only native
    # write before AddMessage is one CString::operator= from the stack action.
    vtables,assigns=[],set()
    for address,(pc,_) in zip(dispatch,message_default):
        code=instructions(address);at=next(i for i,ins in enumerate(code) if ins.address+ins.size==pc)
        register=code[at-2].op_str.split('[')[1].split(' ')[0]
        assert code[at-2].op_str==f'rcx, [{register} + 0x10]' and code[at-1].op_str==f'qword ptr [{register}], rax'
        lea=next(ins for ins in reversed(code[:at]) if ins.mnemonic=='lea' and ins.op_str.startswith('rax, [rip + '))
        vtables.append(rip(lea))
        tail=code[at:];writes=[i for i,ins in enumerate(tail) if f'[{register} + 0x90]' in ins.op_str]
        assert len(writes)==1 and tail[writes[0]].op_str==f'rcx, [{register} + 0x90]'
        call=next(ins for ins in tail[writes[0]:writes[0]+4] if ins.mnemonic=='call');assigns.add(target(call))
        assert any(ins.mnemonic=='call' and target(ins)==named['CMessageHandler::AddMessage'] for ins in tail[writes[0]:])
    assert len(set(vtables))==1 and len(assigns)==1
    table=vtables[0];slots=struct.unpack('<7Q',pe.get_data(table-base,56))
    assert slots[0]==named["CMessageInsertAction::`scalar_deleting_destructor'"]
    assert slots[3]==named['CMessageInsertAction::GetMsgSubType'] and slots[6]==named['CMessageInsertAction::Run']
    # CString ABI: refs at data-0Ch. Copies share a block whose refs >= 0;
    # replacement/destruction lock-decrement and free only at zero; every
    # reviewed writer first copies a block whose refs > 1.
    def shaped(address,required):
        joined='\n'.join(ins.mnemonic+' '+ins.op_str for ins in instructions(address))
        return all(item in joined for item in required)
    copy=[a for a,n in rows if n=='CString::CString' and
          shaped(a,['mov rax, qword ptr [rdx]','cmp dword ptr [rax - 0xc], 0','mov qword ptr [rcx], rax','lock inc dword ptr [rax - 0xc]'])]
    assert len(copy)==1
    reviewed={'copy':(copy[0],['cmp dword ptr [rax - 0xc], 0','lock inc dword ptr [rax - 0xc]']),
              'assign':(assigns.pop(),['cmp rcx, rax','lock xadd dword ptr [rcx], eax','lock inc dword ptr [rax - 0xc]']),
              'destroy':(named['CString::~CString'],['lock xadd dword ptr [rdx], eax','sub eax, 1']),
              'assign_copy':(named['CString::AssignCopy'],['cmp dword ptr [rax - 0xc], 1']),
              'copy_before_write':(named['CString::CopyBeforeWrite'],['cmp dword ptr [rdi - 0xc], 1']),
              'get_buffer':(named['CString::GetBuffer'],['cmp dword ptr [rbp - 0xc], 1']),
              'concat_in_place':(named['CString::ConcatInPlace'],['cmp dword ptr [rsi - 0xc], 1'])}
    strings={}
    for label,(address,required) in reviewed.items():
        assert shaped(address,required),label
        size=ordered[ordered.index(address)+1]-address
        strings[label]=dict(rva=address-base,size=size,signature=signature(pe,'CString '+label,address-base,size),
            body=text(instructions(address)))
    # Destruction returns early for the shared sentinel and frees only when the
    # decremented count reaches zero.
    jumps=[ins.mnemonic for ins in instructions(named['CString::~CString']) if ins.mnemonic.startswith('j')]
    assert jumps[:2]==['je','jg']
    # The shared empty string: its data-pointer global (above), the header
    # global destruction compares against, and the static block itself.
    header_global=next(rip(ins) for ins in instructions(named['CString::~CString']) if ins.mnemonic=='cmp')
    header,=struct.unpack('<Q',pe.get_data(header_global-base,8))
    assert struct.unpack('<Q',pe.get_data(sentinels['0x80']-base,8))[0]==header+12
    nil={sentinels['0x80'],header_global,*range(header,header+16)}
    # CString is never inlined: every locked operation outside its members is
    # unrelated, and only the reviewed copy and assignment add a holder.
    locked,members,unrelated,covered=string_block_sites(pe,base,rows,nil)
    def within(row,label):return strings[label]['rva']<=row['rva']<strings[label]['rva']+strings[label]['size']
    adds=[row for row in locked if row['instruction'].startswith('lock inc')]
    assert len(adds)==2 and within(adds[0],'copy') and within(adds[1],'assign'),adds
    return dict(witness_message_offset=0x10,witness_field_offset=0x80,empty_sentinel_global=sentinels['0x80']-base,
        empty_header_global=header_global-base,insert_message_vtable_rva=table-base,
        insert_message_vtable_slots=[pc-base for pc in slots],string_functions=strings,
        string_lock_sites=locked,string_block_members=members,unrelated_lock_functions=unrelated,reachable_code_bytes=covered)

def action_value_evidence(pe,base,rows,sentinel,strings):
    """How native code handles CAIAction values (action_witness.hpp). An action
    holds CAIObjectTypes at +08h/+20h/+38h and the CStrings m_string1 (+60h),
    m_string2 (+68h) and m_source (+80h). In each .pdata body an action at R+A
    is recognised when [R+A+60h/68h/80h] reach CString members and
    [R+A+08h/20h/38h] reach CAIObjectType members (as `this` or argument), or
    when the empty-string pointer is stored into +60h/+68h/+80h (inline
    construction) beside those CAIObjectType members. Recorded: the CString
    members that touch m_source, every other direct read or write of its
    pointer, every address of m_source formed for any use other than as
    `this` or argument of the next member call, bulk copies in bodies that
    handle actions, and the save/load functions that reach CAIAction members.
    Pattern-based: a body that handles an action through none of these shapes
    stays outside this proof (action-witness-evidence.md)."""
    X=capstone.x86;image=pe.get_memory_mapped_image();names=dict(rows);ordered=sorted(names)
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
    # Sub-registers name their 64-bit register, so `mov eax, ecx` reads rcx.
    canonical={f'r{n}{s}':f'r{n}' for n in range(8,16) for s in ('','d','w','b')}
    for wide,parts in (('rax','eax ax al ah'),('rbx','ebx bx bl bh'),('rcx','ecx cx cl ch'),('rdx','edx dx dl dh'),
                       ('rsi','esi si sil'),('rdi','edi di dil'),('rbp','ebp bp bpl'),('rsp','esp sp spl')):
        canonical.update({part:wide for part in (wide,*parts.split())})
    def register(reg):
        name=cs.reg_name(reg);return canonical.get(name,name)
    members={a:n for a,n in rows if n.startswith(('CString::','CAIObjectType::'))}
    actions={a for a,n in rows if n.startswith('CAIAction::')}
    copiers={a for a,n in rows if n in ('memcpy','memmove','memcpy_s','memmove_s')}
    vector=('movups','movdqu','movaps','movdqa','vmovups','vmovdqu','vmovaps','vmovdqa')
    def owner(address):
        start=ordered[bisect.bisect_right(ordered,address)-1];return names[start],address-start
    bodies={}
    for r in pe.DIRECTORY_ENTRY_EXCEPTION:
        b,e=base+r.struct.BeginAddress,base+r.struct.EndAddress;bodies[b]=max(bodies.get(b,b),e)
    used=collections.Counter();stores=0;direct=[];aliases=[];addresses=0;bulk=[];saving=set();bodies_with_actions=0;actions_found=0
    def site(ins):
        name,offset=owner(ins.address);return f'{name}+{offset:#x} {ins.mnemonic} {ins.op_str}'
    for b,e in sorted(bodies.items()):
        name,_=owner(b)
        if name.startswith(('CString::','CAIObjectType::')):continue
        code=list(cs.disasm(image[b-base:e-base],b))
        calls=[];formed={};held=set();empty=collections.defaultdict(set);handles=False;run=[];copies=[]
        for ins in code:
            m=ins.mnemonic
            if m in vector and ('xmmword ptr' in ins.op_str or 'ymmword ptr' in ins.op_str):run.append(ins)
            elif m not in vector+('mov','lea','add','sub'):
                if len(run)>=16:copies.append(site(run[0]))
                run=[]
            if m.startswith('rep movs'):copies.append(site(ins))
            if m in ('call','jmp') and ins.operands and ins.operands[0].type==X.X86_OP_IMM:
                target=ins.operands[0].imm
                if target in copiers:copies.append(site(ins))
                if m=='call' and target in actions:handles=True
                if m=='call' and target in members:
                    for slot,reg in (('this',X.X86_REG_RCX),('arg',X.X86_REG_RDX)):
                        if reg in formed:calls.append((*formed[reg],target,slot))
            if m in ('call','ret','jmp') or m.startswith('j'):formed={};held=set();continue
            if m=='lea' and ins.operands[0].type==X.X86_OP_REG:
                mem=ins.operands[1].mem;reg=ins.operands[0].reg;held.discard(reg)
                if mem.index==0 and mem.base not in (0,X.X86_REG_RIP):formed[reg]=(mem.base,mem.disp)
                else:formed.pop(reg,None)
                continue
            if m=='mov' and len(ins.operands)==2:
                dst,src=ins.operands
                if dst.type==X.X86_OP_REG and src.type==X.X86_OP_MEM and src.mem.base==X.X86_REG_RIP and ins.address+ins.size+src.mem.disp==sentinel:
                    held.add(dst.reg);formed.pop(dst.reg,None);continue
                if dst.type==X.X86_OP_MEM and src.type==X.X86_OP_REG and src.reg in held and dst.mem.index==0:
                    empty[dst.mem.base].add(dst.mem.disp);continue
            for reg in ins.regs_access()[1]:formed.pop(reg,None);held.discard(reg)
        if len(run)>=16:copies.append(site(run[0]))
        if handles and re.search('marshal|save|load|serial|archive',name,re.I):saving.add(name)
        strings_at={(r,d) for r,d,t,_ in calls if members[t].startswith('CString::')}
        objects_at={(r,d) for r,d,t,_ in calls if members[t].startswith('CAIObjectType::')}
        def framed(r,a):return all((r,a+o) in objects_at for o in (8,0x20,0x38))
        found={(r,d-0x80) for r,d in strings_at if (r,d-0x20) in strings_at and (r,d-0x18) in strings_at and framed(r,d-0x80)}
        found|={(r,d-0x60) for r,disps in empty.items() for d in disps if d+8 in disps and d+0x20 in disps and framed(r,d-0x60)}
        if handles or found:bulk+=copies # bulk copies matter only where actions are handled
        if not found:continue
        bodies_with_actions+=1;actions_found+=len(found);fields={(r,a+0x80) for r,a in found}
        for r,d,t,slot in calls:
            if (r,d) in fields:used[(t,slot)]+=1
        held=set();formed_at={}  # register -> site of a formed m_source address
        for ins in code:
            m=ins.mnemonic;read,written=ins.regs_access()
            # A formed address may only be the this/argument of a member call.
            member=m=='call' and ins.operands and ins.operands[0].type==X.X86_OP_IMM and ins.operands[0].imm in members
            consumed={'rcx','rdx'} if member else set()
            for reg in read:
                name=register(reg)
                if name in formed_at and name not in consumed:aliases.append(formed_at.pop(name))
            for name in consumed:formed_at.pop(name,None)
            for reg in written:formed_at.pop(register(reg),None)
            if m=='mov' and len(ins.operands)==2 and ins.operands[0].type==X.X86_OP_REG and ins.operands[1].type==X.X86_OP_MEM \
               and ins.operands[1].mem.base==X.X86_REG_RIP and ins.address+ins.size+ins.operands[1].mem.disp==sentinel:
                held.add(ins.operands[0].reg);continue
            hit=any(op.type==X.X86_OP_MEM and op.mem.index==0 and (op.mem.base,op.mem.disp) in fields for op in ins.operands)
            if hit and m=='lea':formed_at[register(ins.operands[0].reg)]=site(ins);addresses+=1
            elif hit:
                if m=='mov' and ins.operands[0].type==X.X86_OP_MEM and ins.operands[1].type==X.X86_OP_REG and ins.operands[1].reg in held:stores+=1
                else:direct.append(site(ins))
            if m in ('call','ret','jmp') or m.startswith('j'):
                aliases+=formed_at.values();formed_at={};held=set();continue
            for reg in written:held.discard(reg)
        aliases+=formed_at.values()
    labels={base+row['rva']:label for label,row in strings.items()}
    # m_source is reached only through the reviewed copy, assignment and
    # destruction bodies, and only inline construction stores its pointer.
    assert {labels.get(t) for t,_ in used}=={'copy','assign','destroy'},used
    assert stores and not direct,direct
    # Every bulk copy in a body that handles actions, reviewed one by one: the
    # multiplayer marshal copies string text (GetBuffer data) into its message
    # buffer, QuickLoad copies the CRE header into m_baseStats (+560h onward),
    # ProcessEffectList copies derived stats (+1B40h) into their saved copy
    # (+5070h). None copies a CAIAction or a CString pointer.
    reviewed={'CMessageInsertResponse::MarshalMessage':3,'CGameSprite::QuickLoad':1,'CGameSprite::ProcessEffectList':2}
    assert collections.Counter(entry.split('+')[0] for entry in bulk)==reviewed,bulk
    # Only the multiplayer message marshal and QuickLoad's reset of m_curAction
    # reach CAIAction members among save/load functions: queued and current
    # actions are not part of a save.
    assert saving=={'CMessageInsertResponse::MarshalMessage','CMessageInsertResponse::UnmarshalMessage','CGameSprite::QuickLoad'},saving
    return dict(action_value_bodies=bodies_with_actions,action_values=actions_found,
        m_source_members=[dict(label=labels[t],rva=t-base,role=slot,sites=n) for (t,slot),n in sorted(used.items())],
        m_source_empty_stores=stores,m_source_direct_accesses=direct,m_source_addresses=addresses,m_source_aliases=aliases,
        action_body_bulk_copies=bulk,
        action_save_load_functions=sorted(saving))

def main():
    for version,path,digest,_ in EXES:
        out=audit(version,path,digest)
        (ROOT/('dispatch-audit-'+version+'.json')).write_text(json.dumps(out,indent=2)+'\n',newline='\n')
        print(version,[(x['label'],hex(x['rva']),x['unwind']) for x in out['functions']])
if __name__=='__main__':main()
