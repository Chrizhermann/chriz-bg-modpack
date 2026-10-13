// Offline assembler using the pinned loader's actual AsmJit/AsmTK sources.
// Reads assembly and writes bytes. Never executes generated/game instructions.
#include "asmjit/asmjit.h"
#include "asmtk/asmtk.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
#include <cstring>
int main(int argc,char**argv) {
    if(argc!=4)return 2;
    std::ifstream input(argv[1]);
    const std::string assembly{std::istreambuf_iterator<char>(input),{}};
    if(assembly.empty())return 3;
    asmjit::JitRuntime runtime;asmjit::CodeHolder code;
    code.init(runtime.environment());
    asmjit::x86::Assembler emitter(&code);asmtk::AsmParser parser(&emitter);
    auto error=parser.parse(assembly.c_str());
    if(!error)error=code.flatten();
    if(!error)error=code.resolveUnresolvedLinks();
    if(!error)error=code.relocateToBase(std::stoull(argv[3],nullptr,0));
    if(error){std::cerr<<asmjit::DebugUtils::errorAsString(error)<<"\n";return 4;}
    std::vector<unsigned char> bytes(code.codeSize());
    for(const auto* section:code._sections) {
        if(section->offset()+section->bufferSize()>bytes.size())return 5;
        std::memcpy(bytes.data()+section->offset(),section->data(),section->bufferSize());
    }
    std::ofstream output(argv[2],std::ios::binary);
    output.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    return output?0:6;
}
