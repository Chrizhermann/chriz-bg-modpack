#include "decode_carrier.hpp"
#include "decode_carrier_api.h"
#include "carrier_gate.hpp"
#include <memory>

namespace {
std::unique_ptr<cbm::scroll::DecodeCarrier> carrier;
// The originals again, for calls that may not touch `carrier` (carrier_gate.hpp).
CBMS_PreviousUnmarshal previous_original{};
CBMS_NativeDecoderTrampoline decoder_original{};
cbm::scroll::CarrierGate gate;
using Outside = cbm::scroll::CarrierGate::Outside;
bool admitted() noexcept { return gate.owner() && carrier; }
}
int CBMS_ConfigureDecodeCarrier(CBMS_PreviousUnmarshal previous, CBMS_NativeDecoderTrampoline decoder) {
    if (carrier || !previous || !decoder || previous == CBMS_UnmarshalCarrier || decoder == CBMS_DecodeCarrier) return 0;
    try { carrier = std::make_unique<cbm::scroll::DecodeCarrier>(previous, decoder); }
    catch (...) { return 0; }
    previous_original = previous; decoder_original = decoder; gate.configure(); return 1;
}
int CBMS_DetachDecodeCarrier() {
    if (!CBMS_DecodeCarrierIdle()) return 0;
    carrier.reset(); previous_original = nullptr; decoder_original = nullptr; return 1;
}
int CBMS_DecodeCarrierIdle() { return admitted() && carrier->idle() && gate.quiet() ? 1 : 0; }
void CBMS_UnmarshalCarrier(void* list, unsigned char* data, unsigned size, void* actor, unsigned char version) noexcept(false) {
    if (!admitted()) { Outside outside(gate); previous_original(list, data, size, actor, version); return; }
    carrier->unmarshal(list,data,size,actor,version);
}
void* CBMS_DecodeCarrier(const void* raw) noexcept(false) {
    if (!admitted()) { Outside outside(gate); return decoder_original(raw); }
    return carrier->decode(raw);
}
