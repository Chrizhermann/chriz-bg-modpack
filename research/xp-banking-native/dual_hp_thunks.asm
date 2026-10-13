; Research-only x64 thunks for audited native instruction boundaries.
; No startup installer. Inputs/outputs verified against both native builds.
EXTERN CBMDH_Capture:PROC
EXTERN CBMDH_Record:PROC
PUBLIC CBMDH_ManualCallThunk
PUBLIC CBMDH_ContributionThunk
.code

; Replace ONLY ResetLevelUpPanel's call GetHitPoints with call this thunk.
; Original fifth argument is byte[RSP+28h]. R14 is the actual borrowed sprite.
; Native Win64 entry RSP%16=8; new frame supplies aligned call+six arguments.
CBMDH_ManualCallThunk PROC FRAME
    sub rsp,38h
    .allocstack 38h
    .endprolog
    movzx eax,byte ptr [rsp+60h]
    mov qword ptr [rsp+20h],rax
    mov qword ptr [rsp+28h],r14
    call CBMDH_Capture
    add rsp,38h
    ret
CBMDH_ManualCallThunk ENDP

; Invoked by CALL at RollHitPoints' add r13d,eax / inc r15d (six bytes).
; An injected CALL pushes8: entry alignment is8mod16. Preserve ALL volatile GP,
; flags and XMM registers; replay displaced instructions only after restoration.
; Caller resumes at original next cmp; installed trampoline uses CALL+NOP.
CBMDH_ContributionThunk PROC
    pushfq
    push rax
    push rcx
    push rdx
    push r8
    push r9
    push r10
    push r11
    sub rsp,88h
    movdqu xmmword ptr [rsp+20h],xmm0
    movdqu xmmword ptr [rsp+30h],xmm1
    movdqu xmmword ptr [rsp+40h],xmm2
    movdqu xmmword ptr [rsp+50h],xmm3
    movdqu xmmword ptr [rsp+60h],xmm4
    movdqu xmmword ptr [rsp+70h],xmm5
    mov ecx,r15d
    mov edx,eax
    call CBMDH_Record
    movdqu xmm0,xmmword ptr [rsp+20h]
    movdqu xmm1,xmmword ptr [rsp+30h]
    movdqu xmm2,xmmword ptr [rsp+40h]
    movdqu xmm3,xmmword ptr [rsp+50h]
    movdqu xmm4,xmmword ptr [rsp+60h]
    movdqu xmm5,xmmword ptr [rsp+70h]
    add rsp,88h
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdx
    pop rcx
    pop rax
    popfq
    add r13d,eax
    inc r15d
    ret
CBMDH_ContributionThunk ENDP
END
