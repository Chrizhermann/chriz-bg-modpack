// Owner-thread admission shared by every native carrier group (hooked engine
// entries and the CALL-site callbacks of the preserving stubs).
//
// A carrier runs inside engine code. It must never throw into it, and only the
// engine thread that configured its group may touch the group's state: scopes,
// counters, fault text and the core runtime. Every entry therefore asks
// `owner()` first, which reads only the configured thread. A call on any other
// thread is `Outside`: it latches CBMS_ForeignEntry, the process-wide state that
// disables every override and makes startup unhealthy, counts itself as running
// and calls the native original with its arguments unchanged. Nothing else is
// touched, so the call stays unrecorded and nothing it did can be attributed.
//
// A foreign call still inside its original keeps the group's idle check false,
// so removal refuses instead of releasing its trampoline. Configuration precedes
// every entry patch and detach follows their restoration, so the original exists
// whenever an entry is reachable. Removal still requires that no other thread
// enter a patched entry while it runs (the window before `Outside` counts).
#pragma once
#include "native_api.h"
#include <atomic>
#include <thread>

namespace cbm::scroll {
class CarrierGate {
    std::atomic<std::thread::id> owner_{};
    std::atomic<unsigned> outside_{};
public:
    void configure() noexcept { owner_.store(std::this_thread::get_id()); }
    bool owner() const noexcept { return owner_.load() == std::this_thread::get_id(); }
    bool quiet() const noexcept { return outside_.load() == 0; }
    class Outside {
        CarrierGate& gate_;
    public:
        explicit Outside(CarrierGate& gate) noexcept : gate_(gate) { gate_.outside_.fetch_add(1); CBMS_ForeignEntry(); }
        ~Outside() { gate_.outside_.fetch_sub(1); }
        Outside(const Outside&) = delete;
        Outside& operator=(const Outside&) = delete;
    };
};
} // namespace cbm::scroll
