// Test-only OS unwinder adapter. Never calls an engine or generated-code pointer.
#include <windows.h>
#include <cstdint>
extern "C" __declspec(dllexport) DWORD ScrollTestUnwind(
    std::uintptr_t image, std::uintptr_t pc, const RUNTIME_FUNCTION* function,
    const std::uint64_t* input, std::uint64_t* output) {
    CONTEXT context{};
    context.ContextFlags = CONTEXT_ALL;
    context.Rax=input[0]; context.Rbx=input[1]; context.Rcx=input[2]; context.Rdx=input[3];
    context.Rbp=input[4]; context.Rsi=input[5]; context.Rdi=input[6]; context.R8=input[7];
    context.R9=input[8]; context.R10=input[9]; context.R11=input[10]; context.R12=input[11];
    context.R13=input[12]; context.R14=input[13]; context.R15=input[14]; context.Rsp=input[15]; context.Rip=pc;
    void* data{};
    DWORD64 establisher{};
    __try {
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, image, pc, const_cast<RUNTIME_FUNCTION*>(function),
            &context, &data, &establisher, nullptr);
    } __except (EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    output[0]=context.Rax; output[1]=context.Rbx; output[2]=context.Rcx; output[3]=context.Rdx;
    output[4]=context.Rbp; output[5]=context.Rsi; output[6]=context.Rdi; output[7]=context.R8;
    output[8]=context.R9; output[9]=context.R10; output[10]=context.R11; output[11]=context.R12;
    output[12]=context.R13; output[13]=context.R14; output[14]=context.R15; output[15]=context.Rsp;
    output[16]=context.Rip;
    return 0;
}
