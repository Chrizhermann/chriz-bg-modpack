// Standalone table harness. Never opens the game, loader or saves.
#include "policy_table.hpp"
#include <fstream>
#include <iostream>
#include <iterator>

using cbm::scroll::PolicyTable;
int main(int argc, char** argv) {
    try {
        if (argc < 3) throw std::invalid_argument("usage: table command [item ability]");
        std::ifstream input(argv[1], std::ios::binary);
        if (!input) throw std::runtime_error("table unavailable");
        const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(input)), {});
        PolicyTable table(bytes);
        const std::string mode = argv[2];
        const std::array<std::uint8_t, 1> name{'S'};
        if (mode == "before") { (void)table.lookup(name, 0); return 2; }
        // Digests are test doubles of the host's effective-resource hash reader.
        // Python tests independently compare them to actual resource bytes.
        const auto verify = [&table](std::string_view item, std::string_view ext) -> std::optional<PolicyTable::Digest> {
            for (const auto& dep : table.dependencies()) {
                const auto trim = [](const auto& value) { return std::string_view(value.data(),
                    static_cast<std::size_t>(std::find(value.begin(), value.end(), '\0') - value.begin())); };
                if (trim(dep.name) == item && trim(dep.extension) == ext) return dep.digest;
            }
            return {};
        };
        table.verify(verify);
        if (mode == "changed" || mode == "missing") {
            try {
                table.verify([&](std::string_view item, std::string_view ext) -> std::optional<PolicyTable::Digest> {
                    if (mode == "missing") return {};
                    auto digest = verify(item, ext);
                    if (digest) (*digest)[0] ^= 1;
                    return digest;
                });
                return 3;
            } catch (const std::runtime_error&) {
                if (table.verified()) return 4;
                try { (void)table.lookup(name, 0); return 5; }
                catch (const std::logic_error&) { std::cout << "invalidated\n"; return 0; }
            }
        }
        if (mode == "lookup") {
            if (argc != 5) throw std::invalid_argument("lookup arguments missing");
            const std::string item = argv[3];
            auto raw = std::span(reinterpret_cast<const std::uint8_t*>(item.data()), item.size());
            const auto result = table.lookup(raw, static_cast<std::uint32_t>(std::stoul(argv[4])));
            if (result) std::cout << static_cast<unsigned>(result->policy) << ' ' << static_cast<unsigned>(result->reason) << '\n';
            else std::cout << "absent\n";
        } else if (mode == "fixed8") {
            const std::array<std::uint8_t, 8> fixed{'s', 0, 0, 0, 0, 0, 0, 0};
            const auto result = table.lookup(fixed, 0);
            if (!result) return 6;
            std::cout << static_cast<unsigned>(result->policy) << '\n';
        } else if (mode == "invalid_name") {
            const std::array<std::uint8_t, 8> fixed{'S', 0, 'X', 0, 0, 0, 0, 0};
            (void)table.lookup(fixed, 0);
            return 7;
        } else if (mode == "invalidate") {
            table.invalidate();
            (void)table.lookup(name, 0);
            return 8;
        } else if (mode != "parse") throw std::invalid_argument("unknown command");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
