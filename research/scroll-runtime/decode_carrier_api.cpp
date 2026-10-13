#include "decode_carrier.hpp"
#include "decode_carrier_api.h"
#include <memory>

namespace { std::unique_ptr<cbm::scroll::DecodeCarrier> carrier; }
int CBMS_ConfigureDecodeCarrier(CBMS_PreviousUnmarshal previous, CBMS_NativeDecoderTrampoline decoder) {
    if (carrier || !previous || !decoder || previous == CBMS_UnmarshalCarrier || decoder == CBMS_DecodeCarrier) return 0;
    try { carrier = std::make_unique<cbm::scroll::DecodeCarrier>(previous, decoder); return 1; }
    catch (...) { return 0; }
}
int CBMS_DetachDecodeCarrier() {
    if (!carrier || !carrier->idle()) return 0;
    carrier.reset(); return 1;
}
int CBMS_DecodeCarrierIdle() { return carrier && carrier->idle() ? 1 : 0; }
void CBMS_UnmarshalCarrier(void* list, unsigned char* data, unsigned size, void* actor, unsigned char version) noexcept(false) {
    if (!carrier) throw std::logic_error("Unmarshal carrier entered before certified setup");
    carrier->unmarshal(list,data,size,actor,version);
}
void* CBMS_DecodeCarrier(const void* raw) noexcept(false) {
    if (!carrier) throw std::logic_error("native decoder carrier entered before certified setup");
    return carrier->decode(raw);
}
