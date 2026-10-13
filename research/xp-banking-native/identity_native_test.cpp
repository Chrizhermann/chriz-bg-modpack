// Native Windows shim contract checks with explicit synthetic engine methods.
// identity_probe.py separately executes real PE entry/trampoline windows.
#include "identity_native.h"
#include <cassert>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <cstdio>
#include <string>
#include <vector>

namespace {
bool strip = false, preview = false, nested = false, throw_copy = false;
char original_actor, copied_actor, nested_actor, imported_actor;
int lifetime_calls = 0, destructions = 0, checks = 0;
CBMI_Reason expected = CBMI_SAVE;
std::vector<std::string> pushed;
std::string argument;
void check_impl(bool value, int line) { ++checks; if (!value) throw std::runtime_error("identity assertion " + std::to_string(checks) + " failed at line " + std::to_string(line)); }
#define check(value) check_impl((value), __LINE__)
CBMI_View view(void* actor) { CBMI_View result{}; check(CBMI_Query(actor, &result) == 1); return result; }
void fake_construct(void* actor) { ++lifetime_calls; CBMI_View v{}; check(CBMI_Query(actor, &v) == 1); }
void fake_destruct(void*) { ++destructions; }
uintptr_t fake_marshal(void* actor, void* a, void* b, void* c, unsigned char d) {
    check(a == reinterpret_cast<void*>(0x11112222));
    check(b == reinterpret_cast<void*>(0x33334444));
    check(c == reinterpret_cast<void*>(0x55556666)); check(d == 0xAB);
    auto v = view(actor);
    check(v.current == expected && v.serializing);
    check(!CBMI_CanMutate(actor, v.incarnation));
    auto other = view(&imported_actor);
    check(!CBMI_CanMutate(&imported_actor, other.incarnation));
    return 0xF1F2333344445555;
}
uintptr_t marshal(void* actor) {
    return CBMI_Marshal(actor, reinterpret_cast<void*>(0x11112222),
        reinterpret_cast<void*>(0x33334444), reinterpret_cast<void*>(0x55556666), 0xAB);
}
void* fake_copy(void* actor, int a, int b, int c, int d) {
    check(a == -7 && b == 22 && c == 0x7171 && d == -12345);
    if (throw_copy) throw std::runtime_error("synthetic native unwind");
    check(marshal(actor) == 0xF1F2333344445555);
    void* created = nested ? &nested_actor : &copied_actor;
    CBMI_Construct(created);
    auto cv = view(created);
    check(cv.birth == expected && !cv.eligible && !cv.owner_token[0]);
    if (!nested) {
        nested = true;
        check(CBMI_Copy(actor, a,b,c,d) == &nested_actor);
        nested = false;
        check(view(created).current == expected);
    }
    // The actual Copy makes a second marshal/unmarshal pass. Keep reason alive.
    check(marshal(actor) == 0xF1F2333344445555);
    return created;
}
uintptr_t fake_export(void* game, int id, void* name, int quiet) {
    check(game == reinterpret_cast<void*>(1) && id == -555 && name == reinterpret_cast<void*>(2) && quiet == 9);
    check(marshal(&original_actor) == 0xF1F2333344445555);
    return 0x8182838485868788;
}
int fake_import(void* game, void* name, void* version, unsigned char flag) {
    check(game == reinterpret_cast<void*>(1) && name == reinterpret_cast<void*>(2));
    check(version == reinterpret_cast<void*>(3) && flag == 0xF5);
    CBMI_Construct(&imported_actor);
    check(view(&imported_actor).birth == CBMI_CHR_IMPORT);
    return -123456;
}
const char* read_string(void*, int index, size_t* length) { check(index == 1); *length = argument.size(); return argument.c_str(); }
const char* push_string(void*, const char* value) { pushed.emplace_back(value); return value; }
void push_bool(void*, int value) { pushed.emplace_back(value ? "true" : "false"); }
}
int run() {
    CBMI_Config cfg{1, {reinterpret_cast<uintptr_t>(fake_copy), reinterpret_cast<uintptr_t>(fake_marshal),
        reinterpret_cast<uintptr_t>(fake_export), reinterpret_cast<uintptr_t>(fake_import),
        reinterpret_cast<uintptr_t>(fake_construct), reinterpret_cast<uintptr_t>(fake_destruct)},
        reinterpret_cast<uintptr_t>(read_string), reinterpret_cast<uintptr_t>(push_string),
        reinterpret_cast<uintptr_t>(push_bool), reinterpret_cast<uintptr_t>(&strip), reinterpret_cast<uintptr_t>(&preview)};
    check(!CBMI_Configure(nullptr)); check(CBMI_Configure(&cfg)); check(!CBMI_Configure(&cfg));
    CBMI_View missing{}; check(!CBMI_Query(&original_actor,&missing));
    CBMI_Construct(&original_actor); CBMI_Construct(&imported_actor);
    auto first = view(&original_actor);
    check(first.birth == CBMI_WORLD && first.eligible && !first.serializing);
    check(std::strlen(first.owner_token) == 32 && CBMI_CanMutate(&original_actor,first.incarnation));
    check(!CBMI_CanMutate(&original_actor,first.incarnation+1));
    check(marshal(&original_actor) == 0xF1F2333344445555);
    check(!view(&original_actor).serializing);
    expected = CBMI_CHR_EXPORT;
    check(CBMI_CharacterExport(reinterpret_cast<void*>(1),-555,reinterpret_cast<void*>(2),9) == 0x8182838485868788);
    check(view(&original_actor).current == CBMI_WORLD);
    for (auto r : {CBMI_OTHER_COPY,CBMI_MAGICAL_CLONE,CBMI_PREVIEW}) {
        expected = r; strip = r == CBMI_MAGICAL_CLONE; preview = r == CBMI_PREVIEW;
        check(CBMI_Copy(&original_actor,-7,22,0x7171,-12345) == &copied_actor);
        check(view(&copied_actor).birth == r && !view(&copied_actor).eligible);
        check(view(&original_actor).eligible && view(&original_actor).current == CBMI_WORLD);
        check(std::strcmp(view(&original_actor).owner_token,first.owner_token) == 0);
    }
    strip = preview = false;
    throw_copy = true;
    try { CBMI_Copy(&original_actor,-7,22,0x7171,-12345); check(false); }
    catch (const std::runtime_error&) { check(view(&original_actor).current == CBMI_WORLD); }
    throw_copy = false;
    expected = CBMI_CHR_IMPORT;
    check(CBMI_CharacterImport(reinterpret_cast<void*>(1),reinterpret_cast<void*>(2),reinterpret_cast<void*>(3),0xF5) == -123456);
    check(view(&imported_actor).birth == CBMI_CHR_IMPORT && view(&imported_actor).eligible);
    check(std::strcmp(view(&imported_actor).owner_token,first.owner_token) != 0);
    CBMI_Destruct(&original_actor); check(!CBMI_Query(&original_actor,&missing));
    CBMI_Construct(&original_actor);
    check(view(&original_actor).incarnation != first.incarnation);
    check(std::strcmp(view(&original_actor).owner_token,first.owner_token) != 0);
    char hex[32]; std::snprintf(hex,sizeof(hex),"%llx",static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(&original_actor)));
    argument=hex; check(CBMI_LuaQuery(nullptr) == 7 && pushed.size() == 7);
    check(pushed[0] == "world" && pushed[1] == "world" && pushed[5] == "true" && pushed[6] == "true");
    for (const char* bad : {"", "-1", "0x1111", "123x", "fffffffffffffffff"}) { argument=bad; check(CBMI_LuaQuery(nullptr) == 0); }
    int foreign_result=1;
    std::thread t([&] { foreign_result=CBMI_Query(&original_actor,&missing); }); t.join(); check(!foreign_result);
    check(destructions == 1 && lifetime_calls >= 10);
    std::printf("{\"native_shim_assertions\":%d,\"actual_game_execution\":false}\n",checks);
    return 0;
}
int main() {
    try { return run(); }
    catch (const std::exception& e) { std::fprintf(stderr,"%s\n",e.what()); return 1; }
}
