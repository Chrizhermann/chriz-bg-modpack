#include "dual_native_proficiency.h"
#include <atomic>
#include <cstring>
#include <initializer_list>
#include <new>
#include <charconv>

namespace {
struct Signature { uint32_t rva, size; uint64_t hash; };
struct Build { uint32_t image_size; Signature functions[18]; };
// Actual instruction hashes generated from the two audited offline images.
#include "dual_native_proficiency_builds.inc"
enum Function { Slots, Classes, ClassId, Level, ClassString, StringDestroy,
                TableGet, LevelField, ClassProficiency, ProficiencyIndex, MaximumProficiency,
                ThiefSkillLevelUp, HPConBonus, HPRollClass, SetSkillValue, IsUsable, NextSubClass, SetLevel };
struct String { const char *text; };
struct Table {
    void *resource; char resref[8]; String *columns, *rows, *cells;
    String fallback; int16_t width, height; uint32_t padding;
};
static_assert(sizeof(void *) == 8 && sizeof(Table) == 0x38, "native x64 ABI");
static_assert(offsetof(Table, columns) == 0x10 && offsetof(Table, width) == 0x30,
              "native C2DArray ABI");
std::atomic<uint64_t> next_thread{1}, engine_thread{0};
uint64_t allocate_thread() {
    auto n = next_thread.load();
    while (n != UINT64_MAX) if (next_thread.compare_exchange_weak(n, n + 1)) return n;
    return 0;
}
} // namespace
// Out-of-line environmental boundary also identified by the offline emulator;
// it is not an engine reward callback or a way to select arbitrary owner IDs.
extern "C" __declspec(noinline) uint64_t CBMDP_ThreadToken() {
    static thread_local const auto token = allocate_thread();
    return token;
}
struct CBMDP_Binding { const unsigned char *image; const Build *build; uint64_t owner; };
namespace {
uint64_t hash_bytes(const unsigned char *p, size_t n) {
    uint64_t result = 14695981039346656037ULL;
    for (size_t i = 0; i < n; ++i) result = (result ^ p[i]) * 1099511628211ULL;
    return result;
}
bool matches(const unsigned char *image, size_t size, const Build &build) {
    if (size != build.image_size) return false;
    for (const auto &s : build.functions)
        if (s.rva > size || s.size > size - s.rva || hash_bytes(image+s.rva,s.size)!=s.hash)
            return false;
    return true;
}
template<class T> T function(const CBMDP_Binding &b, Function n) {
    return reinterpret_cast<T>(const_cast<unsigned char *>(b.image)+b.build->functions[n].rva);
}
bool unsigned_cell(const char *text, uint32_t &out) {
    if (!text) return false;
    size_t i=0;
    while (i<128 && (text[i]==' ' || text[i]=='\t' || text[i]=='\r' || text[i]=='\n')) ++i;
    if (i<128 && text[i]=='+') ++i;
    bool digit=false; uint32_t n=0;
    for (; i<128 && text[i]>='0' && text[i]<='9'; ++i) {
        digit=true; auto d=static_cast<uint32_t>(text[i]-'0');
        if (n>(UINT32_MAX-d)/10) return false;
        n=n*10+d;
    }
    if (!digit) return false;
    while (i<128 && (text[i]==' ' || text[i]=='\t' || text[i]=='\r' || text[i]=='\n')) ++i;
    if (i==128 || text[i]) return false;
    out=n; return true;
}
bool signed_cell(const char *text,int32_t &out) {
    if (!text) return false;
    size_t i=0;
    while(i<128 && (text[i]==' ' || text[i]=='\t' || text[i]=='\r' || text[i]=='\n')) ++i;
    if(i==128) return false;
    const bool negative=text[i]=='-';
    uint32_t value=0;
    if(!unsigned_cell(text+i+(negative ? 1:0),value)
        || value>(negative ? uint32_t{0x80000000}:uint32_t{INT32_MAX})) return false;
    out=negative ? static_cast<int32_t>(-static_cast<int64_t>(value)) : static_cast<int32_t>(value);
    return true;
}
using GetClasses=void (*)(const void *,uint8_t *,uint8_t *);
using GetClass=uint8_t (*)(const void *);
using GetLevel=uint8_t (*)(const void *,uint8_t,uint8_t);
using GetClassString=String *(*)(void *,String *,uint8_t,uint32_t);
using DestroyString=void (*)(String *);
using GetAt=String *(*)(Table *,const String *,const String *);
using GetSlots=uint32_t (*)(void *,const void *,const void *,const void *,uint8_t);
using GetClassProficiency=uint16_t (*)(void *,uint8_t,uint8_t,uint8_t,int32_t,uint32_t,uint32_t);
using GetProficiencyIndex=int32_t (*)(void *,uint8_t,uint32_t);
using GetMaximumProficiency=int32_t (*)(void *,int32_t,uint8_t);
bool valid_table(const Table &t) {
    return t.width>=0 && t.height>=0 && (!t.width || t.columns)
        && (!t.height || t.rows) && (!t.width || !t.height || t.cells);
}
const char *cell(const Table &t,int x,int y) {
    if (x<0 || y<0 || x>=t.width || y>=t.height) return t.fallback.text;
    return t.cells[y*t.width+x].text;
}
}

int CBMDP_Bind(const void *image, size_t size, CBMDP_Binding **out) {
    if (!image || !out) return CBMDP_INVALID;
    const auto token=CBMDP_ThreadToken();
    if (!token) return CBMDP_WRONG_THREAD;
    const auto owner=engine_thread.load();
    if (owner && owner!=token) return CBMDP_WRONG_THREAD;
    const Build *selected=nullptr;
    for (const auto &b: builds) if(matches(static_cast<const unsigned char *>(image),size,b)) selected=&b;
    if (!selected) return CBMDP_UNSUPPORTED_IMAGE;
    auto *binding=new(std::nothrow) CBMDP_Binding{static_cast<const unsigned char *>(image),selected,token};
    if (!binding) return CBMDP_INVALID;
    uint64_t empty=0;
    if (!engine_thread.compare_exchange_strong(empty,token) && empty!=token) {
        delete binding; return CBMDP_WRONG_THREAD;
    }
    *out=binding; return CBMDP_OK;
}
int CBMDP_Destroy(CBMDP_Binding *b) {
    if (!b) return CBMDP_INVALID;
    if (CBMDP_ThreadToken()!=b->owner) return CBMDP_WRONG_THREAD;
    delete b; return CBMDP_OK;
}
int CBMDP_IsEngineThread(){const auto owner=engine_thread.load();return owner&&owner==CBMDP_ThreadToken();}
int CBMDP_GetOldTarget(CBMDP_Binding* b,void* rules,const void* type,const void* before,
 uint8_t wanted_active,uint8_t wanted_old,uint32_t xp,CBMDP_OldTarget* out){
 if(!b||!rules||!type||!before||!out)return CBMDP_INVALID;
 if(CBMDP_ThreadToken()!=b->owner)return CBMDP_WRONG_THREAD;
 if(!matches(b->image,b->build->image_size,*b->build))return CBMDP_UNSUPPORTED_IMAGE;
 uint8_t active=0,old=0;function<GetClasses>(*b,Classes)(type,&active,&old);
 const auto overall=function<GetClass>(*b,ClassId)(type);
 if(!wanted_active||!wanted_old||active!=wanted_active||old!=wanted_old||active==old||active==overall)
  return CBMDP_NOT_EXPECTED_DUAL;
 const auto prior=function<GetLevel>(*b,Level)(before,overall,old);
 if(!prior)return CBMDP_INVALID_PROJECTION;
 auto* table=reinterpret_cast<Table*>(static_cast<unsigned char*>(rules)+0x9a0);
 if(!valid_table(*table))return CBMDP_INVALID_PROFS;
 String row{};function<GetClassString>(*b,ClassString)(rules,&row,old,0x4000);
 bool valid=false;uint8_t target=prior;
 for(unsigned step=0;step<256;++step){
  const auto next=static_cast<uint8_t>(target+1);char digits[4]{};
  const auto converted=std::to_chars(digits,digits+3,unsigned(next));*converted.ptr=0;
  const String column{digits};const auto* v=function<GetAt>(*b,TableGet)(table,&column,&row);
  int32_t threshold=0;
  if(!v||!signed_cell(v->text,threshold))break;
  if(threshold==-1||xp<static_cast<uint32_t>(threshold)){valid=true;break;}
  // A nonterminal wrap would lower the actual selected old level. Treat it as
  // malformed progression rather than let the byte loop revisit earlier rows.
  if(!next)break;
  target=next;
 }
 function<DestroyString>(*b,StringDestroy)(&row);
 if(!valid)return CBMDP_INVALID_PROFS;
 alignas(8) unsigned char projected[0x228]{};
 projected[0x46]=prior;std::memcpy(projected+0x60,&xp,4);
 using Native=void(*)(void*,uint8_t,uint8_t,uint8_t,uint8_t,void*);
 function<Native>(*b,NextSubClass)(rules,old,old,old,0,projected);
 const auto result=function<GetLevel>(*b,Level)(projected,old,old);
 if(result!=target)return CBMDP_NATIVE_MISMATCH;
 *out={xp,prior,result,active,old};return CBMDP_OK;
}
namespace {
int oldProjection(CBMDP_Binding* b,void* rules,const void* type,const void* before,uint8_t active,uint8_t old,
 uint32_t xp,CBMDP_OldTarget& levels,unsigned char* after){
 const auto status=CBMDP_GetOldTarget(b,rules,type,before,active,old,xp,&levels);if(status)return status;
 std::memcpy(after,before,0x228);const auto overall=function<GetClass>(*b,ClassId)(type);
 function<void(*)(void*,uint8_t,uint8_t,uint8_t)>(*b,SetLevel)(after,overall,old,levels.target);return CBMDP_OK;
}
}
int CBMDP_GetOldPlan(CBMDP_Binding* b,void* rules,const void* type,const void* before,uint8_t active,uint8_t old,
 uint32_t xp,uint32_t kit,CBMDP_OldPlan* out){
 if(!out)return CBMDP_INVALID;alignas(8) unsigned char after[0x228];CBMDP_OldTarget levels{};
 auto status=oldProjection(b,rules,type,before,active,old,xp,levels,after);if(status)return status;
 CBMDP_Result prof{};status=CBMDP_GetSlots(b,rules,type,before,after,active,old,&prof);if(status)return status;
 CBMDP_SkillBudget skills{};status=CBMDP_GetSkillBudget(b,rules,type,before,after,active,old,kit,&skills);if(status)return status;
 *out={levels,prof.picks,skills.points};return CBMDP_OK;
}
int CBMDP_GetOldCap(CBMDP_Binding* b,void* rules,const void* type,const void* before,uint8_t active,uint8_t old,
 uint32_t xp,uint32_t kit,uint32_t stat,CBMDP_ChoiceCap* out){
 if(!out)return CBMDP_INVALID;alignas(8) unsigned char after[0x228];CBMDP_OldTarget levels{};
 const auto status=oldProjection(b,rules,type,before,active,old,xp,levels,after);if(status)return status;
 return CBMDP_GetChoiceCap(b,rules,type,after,active,old,kit,stat,out);
}
int CBMDP_GetSlots(CBMDP_Binding *b, void *rules, const void *type,
    const void *before, const void *after, uint8_t wanted_active, uint8_t wanted_old,
    CBMDP_Result *out) {
    if (!b || !rules || !type || !before || !after || !out) return CBMDP_INVALID;
    if (CBMDP_ThreadToken()!=b->owner) return CBMDP_WRONG_THREAD;
    // Recheck actual routine bytes: do not call stale addresses after hot-patching.
    if (!matches(b->image,b->build->image_size,*b->build)) return CBMDP_UNSUPPORTED_IMAGE;
    uint8_t active=0,old=0;
    function<GetClasses>(*b,Classes)(type,&active,&old);
    const auto overall=function<GetClass>(*b,ClassId)(type);
    if (!wanted_active || !wanted_old || active!=wanted_active || old!=wanted_old
        || active==old || active==overall) return CBMDP_NOT_EXPECTED_DUAL;
    auto level=function<GetLevel>(*b,Level);
    const auto old_before=level(before,overall,old), old_after=level(after,overall,old);
    if (old_after<old_before || level(before,overall,active)!=level(after,overall,active))
        return CBMDP_INVALID_PROJECTION;
    // Native helper only reads these level fields. A deferred projection must not
    // covertly alter the other independent class slot either (triple-class data).
    const auto *left=static_cast<const uint8_t *>(before), *right=static_cast<const uint8_t *>(after);
    unsigned different=0;
    for (const size_t offset: {size_t{0x46},size_t{0x48},size_t{0x4a}})
        if (left[offset]!=right[offset]) ++different;
    if (different>(old_before!=old_after ? 1U : 0U)) return CBMDP_INVALID_PROJECTION;
    String row{};
    function<GetClassString>(*b,ClassString)(rules,&row,old,0x4000);
    auto *table=reinterpret_cast<Table *>(static_cast<unsigned char *>(rules)+0x118);
    const String first{"FIRST_LEVEL"}, rate{"RATE"};
    uint32_t first_n=0,rate_n=0;
    // Follow the actual native lookup, including a valid table default and the
    // engine's first-row behavior. Explicit vanilla-shaped rows are not required.
    bool valid=valid_table(*table);
    if (valid) {
        const auto get=function<GetAt>(*b,TableGet);
        const auto *f=get(table,&first,&row), *r=get(table,&rate,&row);
        valid=f && r && unsigned_cell(f->text,first_n) && unsigned_cell(r->text,rate_n)
            && first_n<=INT32_MAX && rate_n>0 && rate_n<=INT32_MAX;
    }
    function<DestroyString>(*b,StringDestroy)(&row);
    if (!valid) return CBMDP_INVALID_PROFS;
    // Concrete native function call, including the actual fifth stack argument.
    const auto picks=function<GetSlots>(*b,Slots)(rules,type,before,after,1);
    const auto expected=(old_before==0 && old_after==1) ? first_n
        : uint32_t(old_after)/rate_n-uint32_t(old_before)/rate_n;
    if (picks!=expected) return CBMDP_NATIVE_MISMATCH;
    *out=CBMDP_Result{picks,first_n,rate_n,active,old,old_before,old_after};
    return CBMDP_OK;
}

int CBMDP_GetChoiceCap(CBMDP_Binding *b,void *rules,const void *type,const void *after,
    uint8_t wanted_active,uint8_t wanted_old,uint32_t old_kit,uint32_t stat,CBMDP_ChoiceCap *out) {
    if (!b || !rules || !type || !after || !out) return CBMDP_INVALID;
    if (CBMDP_ThreadToken()!=b->owner) return CBMDP_WRONG_THREAD;
    if (!matches(b->image,b->build->image_size,*b->build)) return CBMDP_UNSUPPORTED_IMAGE;
    uint8_t active=0,old=0;
    function<GetClasses>(*b,Classes)(type,&active,&old);
    const auto overall=function<GetClass>(*b,ClassId)(type);
    if (!wanted_active || !wanted_old || active!=wanted_active || old!=wanted_old
        || active==old || active==overall) return CBMDP_NOT_EXPECTED_DUAL;
    const auto level=function<GetLevel>(*b,Level)(after,overall,old);
    auto *raw=static_cast<unsigned char *>(rules);
    const auto &weapons=*reinterpret_cast<Table *>(raw+0x1998);
    const auto &kits=*reinterpret_cast<Table *>(raw+0x2610);
    const auto &maximum=*reinterpret_cast<Table *>(raw+0x150);
    if (!valid_table(weapons) || !valid_table(kits) || !valid_table(maximum)
        || weapons.width<=0 || weapons.height<=0) return CBMDP_INVALID_PROFS;
    // These native sscanf outputs are otherwise uninitialized on malformed
    // cells. Validate only the cells the selected native branch will consume.
    const uint32_t kit_row=old_kit & ~uint32_t{0x4000};
    if ((old_kit & 0x4000) && kit_row) {
        uint32_t kit_class=0,index=0;
        const int row=kit_row<=INT32_MAX ? static_cast<int>(kit_row) : -1;
        if (!unsigned_cell(cell(kits,7,row),kit_class)) return CBMDP_INVALID_PROFS;
        if (kit_class==old && !unsigned_cell(cell(kits,5,row),index)) return CBMDP_INVALID_PROFS;
        if (kit_class==old && index>INT32_MAX) return CBMDP_INVALID_PROFS;
    }
    const auto column=function<GetProficiencyIndex>(*b,ProficiencyIndex)(rules,old,old_kit);
    bool found=false;
    int32_t expected=0;
    for (int row=0;row<weapons.height;++row) {
        uint32_t id=0;
        if (!unsigned_cell(cell(weapons,0,row),id) || id>INT32_MAX) return CBMDP_INVALID_PROFS;
        if (id!=stat) continue;
        if (!signed_cell(cell(weapons,column,row),expected) || expected>INT16_MAX || expected<INT16_MIN)
            return CBMDP_INVALID_PROFS;
        found=true;break;
    }
    if (!found) { *out=CBMDP_ChoiceCap{0,0,0}; return CBMDP_OK; }
    // The stock helper compares explicit class arguments. Selecting old for all
    // three means its single-class branch applies the old kit column directly.
    const auto weapon=static_cast<int16_t>(function<GetClassProficiency>(*b,ClassProficiency)(rules,old,old,old,0,stat,old_kit));
    const auto level_max=function<GetMaximumProficiency>(*b,MaximumProficiency)(rules,level,old);
    if (weapon!=expected) return CBMDP_NATIVE_MISMATCH;
    const int32_t minimum=weapon<level_max ? weapon:level_max;
    *out=CBMDP_ChoiceCap{weapon,level_max,minimum>0 ? static_cast<uint32_t>(minimum):0};
    return CBMDP_OK;
}

int CBMDP_GetSkillBudget(CBMDP_Binding *b,void *rules,const void *type,const void *before,
    const void *after,uint8_t wanted_active,uint8_t wanted_old,uint32_t old_kit,CBMDP_SkillBudget *out) {
    if (!b || !rules || !type || !before || !after || !out) return CBMDP_INVALID;
    if (CBMDP_ThreadToken()!=b->owner) return CBMDP_WRONG_THREAD;
    if (!matches(b->image,b->build->image_size,*b->build)) return CBMDP_UNSUPPORTED_IMAGE;
    uint8_t active=0,old=0;
    function<GetClasses>(*b,Classes)(type,&active,&old);
    const auto overall=function<GetClass>(*b,ClassId)(type);
    if (!wanted_active || !wanted_old || active!=wanted_active || old!=wanted_old
        || active==old || active==overall) return CBMDP_NOT_EXPECTED_DUAL;
    const auto level=function<GetLevel>(*b,Level);
    const uint32_t from=level(before,overall,old),to=level(after,overall,old);
    if (!from || to<from || level(before,overall,active)!=level(after,overall,active))
        return CBMDP_INVALID_PROJECTION;
    const auto &kits=*reinterpret_cast<Table *>(static_cast<unsigned char *>(rules)+0x2610);
    auto *skills=reinterpret_cast<Table *>(static_cast<unsigned char *>(rules)+0x3238);
    if (!valid_table(kits) || !valid_table(*skills)) return CBMDP_INVALID_PROFS;
    const uint32_t kit_row=old_kit & ~uint32_t{0x4000};
    if ((old_kit & 0x4000) && kit_row) {
        uint32_t kit_class=0;
        const int row=kit_row<=INT32_MAX ? static_cast<int>(kit_row):-1;
        if (!unsigned_cell(cell(kits,7,row),kit_class)) return CBMDP_INVALID_PROFS;
    }
    // GetThiefSkillsLevelUp uses the ACTIVE class then GetClassString and the
    // THIEFSKL LEVEL_POINTS cell. This extension selects the old class explicitly
    // through the same native string/table helpers; it never rewrites actor type.
    String row{};
    function<GetClassString>(*b,ClassString)(rules,&row,old,old_kit);
    const String column{"LEVEL_POINTS"};
    const auto *value=function<GetAt>(*b,TableGet)(skills,&column,&row);
    uint32_t per_level=0;
    const bool valid=value && unsigned_cell(value->text,per_level) && per_level<=INT32_MAX;
    function<DestroyString>(*b,StringDestroy)(&row);
    if (!valid || (to>from && per_level>UINT32_MAX/(to-from))) return CBMDP_INVALID_PROFS;
    *out=CBMDP_SkillBudget{per_level,to-from,per_level*(to-from)};
    return CBMDP_OK;
}

int CBMDP_RollOldHP(CBMDP_Binding *b,void *rules,const void *type,const void *before,
    const void *after,uint8_t wanted_active,uint8_t wanted_old,uint32_t old_kit,
    uint8_t constitution,CBMDP_HPRolls *out) {
    if (!b || !rules || !type || !before || !after || !out) return CBMDP_INVALID;
    if (CBMDP_ThreadToken()!=b->owner) return CBMDP_WRONG_THREAD;
    if (!matches(b->image,b->build->image_size,*b->build)) return CBMDP_UNSUPPORTED_IMAGE;
    uint8_t active=0,old=0;
    function<GetClasses>(*b,Classes)(type,&active,&old);
    const auto overall=function<GetClass>(*b,ClassId)(type);
    if (!wanted_active || !wanted_old || active!=wanted_active || old!=wanted_old
        || active==old || active==overall) return CBMDP_NOT_EXPECTED_DUAL;
    const auto level=function<GetLevel>(*b,Level);
    const uint32_t from=level(before,overall,old),to=level(after,overall,old);
    if (!from || to<from || level(before,overall,active)!=level(after,overall,active))
        return CBMDP_INVALID_PROJECTION;
    CBMDP_HPRolls pending{};
    if (to==from) { *out=pending;return CBMDP_OK; }
    // The audited higher RollHitPoints reads only GetLevel and kit from these
    // arguments. These are private scalar projections, not CDerivedStats clones:
    // no reference-owned lists and no constructor/destructor side effects.
    alignas(8) unsigned char left[0x228]{},right[0x228]{};
    std::memcpy(left+0x224,&old_kit,sizeof(old_kit));
    std::memcpy(right+0x224,&old_kit,sizeof(old_kit));
    using Con=void(*)(void*,uint8_t,uint8_t,int32_t*,int32_t*);
    using Roll=int32_t(*)(void*,uint8_t,uint8_t,const void*,const void*,int32_t,int32_t,int32_t);
    function<Con>(*b,HPConBonus)(rules,old,constitution,&pending.native_con_bonus,&pending.native_minimum_roll);
    int64_t total=0;
    for (uint32_t n=from+1;n<=to;++n) {
        left[0x46]=static_cast<unsigned char>(n-1);right[0x46]=static_cast<unsigned char>(n);
        // Explicit single-class arguments select the old class/kit's normal HP
        // rules. Divisor1, useKit1 match the native single-class path; the actor
        // remains a dual throughout. Each native roll is retained separately.
        const int32_t hp=function<Roll>(*b,HPRollClass)(rules,old,old,left,right,
            pending.native_minimum_roll,1,1);
        if (hp<1 || total+hp>INT32_MAX) return CBMDP_NATIVE_MISMATCH;
        pending.samples[pending.count++]={n,hp};total+=hp;
    }
    pending.total=static_cast<int32_t>(total);*out=pending;return CBMDP_OK;
}

int CBMDP_RollOldPlan(CBMDP_Binding*b,void*rules,const void*type,const void*before,
 uint8_t active,uint8_t old,uint32_t xp,uint32_t kit,uint8_t constitution,CBMDP_HPRolls*out){
 if(!out)return CBMDP_INVALID;alignas(8) unsigned char after[0x228];CBMDP_OldTarget levels{};
 const auto status=oldProjection(b,rules,type,before,active,old,xp,levels,after);if(status)return status;
 return CBMDP_RollOldHP(b,rules,type,before,after,active,old,kit,constitution,out);
}

int CBMDP_ApplyOldSkills(CBMDP_Binding *b,void *rules,void *actor,const void *before,
    const void *after,uint8_t active,uint8_t old,uint32_t kit,
    const CBMDP_SkillChoices *choices,uint32_t *unused) {
    if(!b||!rules||!actor||!before||!after||!choices||!unused)return CBMDP_INVALID;
    if(CBMDP_ThreadToken()!=b->owner)return CBMDP_WRONG_THREAD;
    auto *sprite=static_cast<unsigned char*>(actor);
    const void *type=sprite+0x4b68;
    CBMDP_SkillBudget budget{};
    const int status=CBMDP_GetSkillBudget(b,rules,type,before,after,active,old,kit,&budget);
    if(status!=CBMDP_OK)return status;
    using Usable=int32_t(*)(const void*,uint8_t,int32_t);
    if(function<Usable>(*b,IsUsable)(type,old,1))return CBMDP_NOT_EXPECTED_DUAL;
    // CGameSprite::SetSkillValue's actual seven jump-table destinations, same on
    // both audited builds. Verify the caller's captured current values before
    // any mutation, and preserve every byte outside these native owned fields.
    constexpr size_t offsets[]={0x5c2,0x5bf,0x5c1,0x5c0,0x59d,0x5bc,0x5bd};
    uint32_t spent=0;
    for(unsigned i=0;i<7;++i){
        if(sprite[offsets[i]]!=choices->before[i]||choices->selected[i]<choices->before[i])
            return CBMDP_INVALID_PROJECTION;
        spent+=choices->selected[i]-choices->before[i];
    }
    if(spent>budget.points)return CBMDP_INVALID_PROJECTION;
    using Set=void(*)(void*,uint8_t,uint8_t);
    // Audited setter has only a bounds dispatch and one byte store per branch;
    // it calls no Lua, allocator, effect processor, message or external handler.
    // Engine-thread confinement prevents observation between these seven stores.
    for(uint8_t i=0;i<7;++i)if(choices->selected[i]!=choices->before[i])
        function<Set>(*b,SetSkillValue)(actor,i,choices->selected[i]);
    *unused=budget.points-spent;return CBMDP_OK;
}
int CBMDP_ApplyOldPlanSkills(CBMDP_Binding*b,void*rules,void*actor,uint8_t active,uint8_t old,
 uint32_t xp,uint32_t kit,const CBMDP_SkillChoices*choices,uint32_t*unused){
 if(!actor||!choices||!unused)return CBMDP_INVALID;
 const auto*type=static_cast<unsigned char*>(actor)+0x4b68;const auto*before=static_cast<unsigned char*>(actor)+0x1120;
 alignas(8) unsigned char after[0x228];CBMDP_OldTarget levels{};
 const auto status=oldProjection(b,rules,type,before,active,old,xp,levels,after);if(status)return status;
 return CBMDP_ApplyOldSkills(b,rules,actor,before,after,active,old,kit,choices,unused);
}
