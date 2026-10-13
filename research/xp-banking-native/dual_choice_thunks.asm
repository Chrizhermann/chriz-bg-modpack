EXTERN CBMDC_Active:PROC
EXTERN CBMDC_Inactive:PROC
PUBLIC CBMDC_ActiveThunk
PUBLIC CBMDC_InactiveThunk
.code
; Four callsites in OnProficiencyPlusMinusButtonClick carry screen in RDI.
; Preserve native four args and add borrowed screen as fifth, no class toggles.
CBMDC_ActiveThunk PROC FRAME
    sub rsp,28h
    .allocstack 28h
    .endprolog
    mov qword ptr [rsp+20h],rdi
    call CBMDC_Active
    add rsp,28h
    ret
CBMDC_ActiveThunk ENDP
CBMDC_InactiveThunk PROC FRAME
    sub rsp,28h
    .allocstack 28h
    .endprolog
    mov qword ptr [rsp+20h],rdi
    call CBMDC_Inactive
    add rsp,28h
    ret
CBMDC_InactiveThunk ENDP
END
