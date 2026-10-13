/* Contract tests against a deliberately FAKE detached backend. This does not
 * simulate or claim that the Infinity Engine provides any of these callbacks. */
#include "dual_transaction.h"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <vector>
#include <cstring>
#include <thread>

static unsigned checks = 0, scenarios = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); std::abort(); } } while(0)

struct Fake {
    CBMD_Context *context = nullptr;
    CBMD_Snapshot live{{1,2,3,42},7,19,800000,800000,300000,200000,0,
                        200000,0x4000,2,4,10,10,12};
    CBMD_Plan plan{800000,750000,1000000,11,0,0};
    CBMD_Preview preview{};
    CBMD_Receipt applied{};
    uint64_t handle = 0, transaction = 0;
    int captures = 0, prepares = 0, commits = 0, discards = 0;
    int callbacks = 0;
    int commit_outcome = CBMD_APPLIED, resolve_outcome = CBMD_UNKNOWN;
    bool fail_capture = false, fail_prepare = false, fail_choose = false;
    bool throw_prepare = false, throw_choose = false, throw_commit = false;
    bool throw_resolve = false, apply_before_error = false, bad_receipt = false;
    bool tamper_preview = false, reenter = false, race_at_commit = false;
    int nested = -1;
    int fake_hp = 101, fake_prof = 2;
    std::vector<int> unrelated_effects{3,17,81};
    CBMD_Request request() const { return {live.actor, live.ledger_revision,live.old_usable_xp,91}; }
    CBMD_EngineV1 engine(uint32_t caps = CBMD_BASE_REQUIRED) {
        return {CBMD_ABI,sizeof(CBMD_EngineV1),caps,this,capture,prepare,choose,inspect,commit,resolve,discard};
    }
    static Fake &f(void *v) { return *static_cast<Fake *>(v); }
    static int capture(void *v, const CBMD_Actor *, CBMD_Snapshot *out) {
        auto &s=f(v); ++s.callbacks; ++s.captures;
        if (s.fail_capture) return 0;
        *out=s.live; return 1;
    }
    static int prepare(void *v,const CBMD_Request *,const CBMD_Snapshot *before,
                       uint64_t tx,uint64_t *handle,CBMD_Plan *plan) {
        auto &s=f(v); ++s.callbacks; ++s.prepares;
        if (s.reenter) { uint32_t p; s.nested=CBMD_GetPhase(s.context,&p); }
        s.handle=123; *handle=s.handle; s.transaction=tx; *plan=s.plan;
        s.preview={*before,1,1}; s.preview.projected.old_level=s.plan.target_old_level;
        if (s.throw_prepare) throw std::runtime_error("prepare");
        return s.fail_prepare ? 0 : 1;
    }
    static int choose(void *v,uint64_t,const void *choice,size_t bytes) {
        auto &s=f(v); ++s.callbacks;
        if (s.throw_choose) throw std::runtime_error("choose");
        if (s.fail_choose || !choice || bytes!=sizeof(int)) return 0;
        s.preview.pending_choices=*static_cast<const int *>(choice)==0 ? 1u : 0u;
        ++s.preview.choice_revision; return 1;
    }
    static int inspect(void *v,uint64_t,CBMD_Preview *out) {
        auto &s=f(v); ++s.callbacks; *out=s.preview;
        if (s.tamper_preview) ++out->projected.native_base_xp;
        return 1;
    }
    static int commit(void *v,uint64_t,uint64_t tx,const CBMD_Snapshot *before,
                      const CBMD_Plan *plan,uint64_t choice,CBMD_Receipt *out) {
        auto &s=f(v); ++s.callbacks; ++s.commits;
        if (s.reenter) { CBMD_Receipt r; s.nested=CBMD_Commit(s.context,choice,&r); }
        if (s.race_at_commit) ++s.live.actor_revision;
        if (s.live.actor_revision!=before->actor_revision
            || s.live.ledger_revision!=before->ledger_revision) return CBMD_UNCHANGED;
        if (s.commit_outcome==CBMD_APPLIED || s.apply_before_error) {
            s.live.old_level=plan->target_old_level;
            ++s.live.actor_revision; ++s.live.ledger_revision;
            s.fake_hp+=3; ++s.fake_prof;
            s.applied={s.live,tx,choice}; *out=s.applied;
            if (s.bad_receipt) ++out->after.active_usable_xp;
        }
        if (s.throw_commit) throw std::runtime_error("commit uncertainty");
        return s.commit_outcome;
    }
    static int resolve(void *v,uint64_t,uint64_t,CBMD_Receipt *out) {
        auto &s=f(v); ++s.callbacks;
        if (s.throw_resolve) throw std::runtime_error("resolve");
        *out=s.applied; return s.resolve_outcome;
    }
    static void discard(void *v,uint64_t handle) {
        auto &s=f(v); ++s.callbacks; CHECK(handle==s.handle); ++s.discards; s.handle=0;
    }
};
struct Fixture {
    Fake fake;
    explicit Fixture(uint32_t caps=CBMD_BASE_REQUIRED) {
        ++scenarios; auto e=fake.engine(caps); CHECK(CBMD_Create(&e,&fake.context)==CBMD_OK);
    }
    ~Fixture() {
        uint32_t phase=0; CHECK(CBMD_GetPhase(fake.context,&phase)==CBMD_OK);
        if (phase==CBMD_CHOOSING) CHECK(CBMD_Cancel(fake.context)==CBMD_OK);
        CHECK(phase!=CBMD_COMMIT_UNKNOWN); CHECK(CBMD_Destroy(fake.context)==CBMD_OK);
    }
    int begin() { auto r=fake.request(); return CBMD_Begin(fake.context,&r); }
    uint64_t ready() {
        CHECK(begin()==CBMD_OK); int choice=1;
        CHECK(CBMD_Choose(fake.context,&choice,sizeof(choice))==CBMD_OK);
        CBMD_Preview p{}; CHECK(CBMD_GetPreview(fake.context,&p)==CBMD_OK);
        CHECK(p.pending_choices==0); return p.choice_revision;
    }
};

static void wrong_thread_calls(Fake &f) {
    const int callbacks=f.callbacks;
    const auto handle=f.handle;
    uint32_t phase_before=0,phase_after=0;
    CHECK(CBMD_GetPhase(f.context,&phase_before)==CBMD_OK);
    int results[10]{};
    auto request=f.request();
    auto engine=f.engine();
    std::thread worker([&] {
        CBMD_Context *other=nullptr;
        CBMD_Preview preview{}; CBMD_Receipt receipt{}; uint32_t phase=99; int choice=1;
        results[0]=CBMD_Create(&engine,&other);
        results[1]=CBMD_Begin(f.context,&request);
        results[2]=CBMD_Choose(f.context,&choice,sizeof(choice));
        results[3]=CBMD_GetPreview(f.context,&preview);
        results[4]=CBMD_Commit(f.context,2,&receipt);
        results[5]=CBMD_Cancel(f.context);
        results[6]=CBMD_Resolve(f.context,&receipt);
        results[7]=CBMD_GetPhase(f.context,&phase);
        results[8]=CBMD_Reset(f.context);
        results[9]=CBMD_Destroy(f.context);
    });
    worker.join();
    for(auto result:results) CHECK(result==CBMD_WRONG_THREAD);
    CHECK(f.callbacks==callbacks && f.handle==handle);
    CHECK(CBMD_GetPhase(f.context,&phase_after)==CBMD_OK && phase_after==phase_before);
}

int main() {
    // Capabilities/callbacks are requirements, not proof that an engine has them.
    for (unsigned bit=0;bit<11;++bit) if (CBMD_BASE_REQUIRED & (1u<<bit)) {
        ++scenarios; Fake f; auto e=f.engine(CBMD_BASE_REQUIRED & ~(1u<<bit));
        CHECK(CBMD_Create(&e,&f.context)==CBMD_UNSUPPORTED); CHECK(f.context==nullptr);
        CHECK(f.captures==0);
    }
    { ++scenarios; Fake f; auto e=f.engine(); e.abi=2;
      CHECK(CBMD_Create(&e,&f.context)==CBMD_UNSUPPORTED); e=f.engine(); e.commit=nullptr;
      CHECK(CBMD_Create(&e,&f.context)==CBMD_UNSUPPORTED); e=f.engine(); --e.struct_size;
      CHECK(CBMD_Create(&e,&f.context)==CBMD_UNSUPPORTED); }
    { Fixture t; auto rev=t.ready(); auto &f=t.fake; CBMD_Receipt r{};
      CHECK(f.live.old_level==10 && f.fake_hp==101 && f.fake_prof==2);
      CHECK(f.live.native_base_xp==200000 && f.live.old_usable_xp==800000);
      CHECK(CBMD_Commit(f.context,rev,&r)==CBMD_OK);
      CHECK(f.live.old_level==11 && f.fake_hp==104 && f.fake_prof==3);
      CHECK(f.live.active_usable_xp==200000 && f.live.native_base_xp==200000);
      CHECK(f.live.old_usable_xp==800000 && f.live.old_frozen_total==800000);
      CHECK(f.live.ledger_revision==8 && f.live.actor_revision==20);
      CHECK(f.unrelated_effects==std::vector<int>({3,17,81}));
      CHECK(CBMD_Commit(f.context,rev,&r)==CBMD_ALREADY_COMMITTED && f.commits==1);
      CHECK(CBMD_Resolve(f.context,&r)==CBMD_ALREADY_COMMITTED);
      CHECK(CBMD_Reset(f.context)==CBMD_OK); f.plan.target_old_level=11;
      CHECK(t.begin()==CBMD_NO_LEVEL && f.commits==1); }
    { Fixture t; CHECK(t.begin()==CBMD_OK); CBMD_Preview p{}; CBMD_Receipt r{};
      CHECK(CBMD_GetPreview(t.fake.context,&p)==CBMD_OK);
      CHECK(CBMD_Commit(t.fake.context,p.choice_revision,&r)==CBMD_CHOICES_PENDING);
      CHECK(CBMD_Cancel(t.fake.context)==CBMD_OK);
      CHECK(t.fake.live.old_level==10 && t.fake.live.ledger_revision==7 && t.fake.fake_prof==2);
      CHECK(t.begin()==CBMD_OK); CHECK(t.fake.commits==0); }
    { Fixture t; CHECK(t.begin()==CBMD_OK); int choice=1; CBMD_Receipt r{};
      CHECK(CBMD_Choose(t.fake.context,&choice,sizeof(choice))==CBMD_OK);
      CHECK(CBMD_Commit(t.fake.context,2,&r)==CBMD_STALE); }
    { Fixture t; auto rev=t.ready(); int choice=1; CBMD_Receipt r{};
      CHECK(CBMD_Choose(t.fake.context,&choice,sizeof(choice))==CBMD_OK);
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_STALE); }
    { Fixture t; auto rev=t.ready(); ++t.fake.live.actor_revision; CBMD_Receipt r{};
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_STALE && t.fake.commits==0); }
    { Fixture t; auto rev=t.ready(); ++t.fake.live.ledger_revision; CBMD_Receipt r{};
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_STALE && t.fake.commits==0); }
    { Fixture t; auto rev=t.ready(); ++t.fake.live.actor.incarnation; CBMD_Receipt r{};
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_STALE && t.fake.commits==0); }
    { Fixture t; auto rev=t.ready(); t.fake.race_at_commit=true; CBMD_Receipt r{};
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_ADAPTER_ERROR);
      CHECK(t.fake.live.old_level==10 && t.fake.fake_prof==2); }
    { Fixture t; auto r=t.fake.request(); ++r.old_class_xp_target;
      CHECK(CBMD_Begin(t.fake.context,&r)==CBMD_STALE && t.fake.prepares==0); }
    { Fixture t; auto r=t.fake.request(); r.manual_action_id=0;
      CHECK(CBMD_Begin(t.fake.context,&r)==CBMD_INVALID && t.fake.captures==0); }
    { Fixture t; t.fake.live.original_old_bank=0; // policy neutral: exact no-bank baseline is accepted
      CHECK(t.begin()==CBMD_OK); }
    { Fixture t; t.fake.plan.old_xp_target++; CHECK(t.begin()==CBMD_INVALID); }
    { Fixture t; t.fake.plan.target_threshold=800001; CHECK(t.begin()==CBMD_INVALID); }
    { Fixture t; t.fake.plan.next_threshold=800000; CHECK(t.begin()==CBMD_INVALID); }
    { Fixture t; t.fake.plan.target_old_level=9; CHECK(t.begin()==CBMD_INVALID); }
    { Fixture t; t.fake.plan.at_table_max=1; t.fake.plan.next_threshold=0;
      CHECK(t.begin()==CBMD_OK); }
    { Fixture t; t.fake.live.active_level=11; CHECK(t.begin()==CBMD_UNSUPPORTED);
      CHECK(t.fake.live.old_level==10 && t.fake.fake_prof==2 && t.fake.discards==1); }
    { Fixture t(CBMD_BASE_REQUIRED|CBMD_REVERSIBLE_OLD_USABILITY); t.fake.live.active_level=11;
      CHECK(t.begin()==CBMD_OK); /* fake capability, not native acceptance */ }
    { Fixture t; t.fake.live.active_level=9; CHECK(t.begin()==CBMD_OK); }
    { Fixture t; t.fake.tamper_preview=true; CHECK(t.begin()==CBMD_INVALID);
      CHECK(t.fake.discards==1 && t.fake.live.native_base_xp==200000); }
    for (int field=0;field<16;++field) {
      Fixture t; auto rev=t.ready(); auto &p=t.fake.preview.projected;
      switch(field) {
        case 0: ++p.actor.incarnation; break;
        case 1: ++p.actor.owner_hi; break;
        case 2: ++p.actor.object_id; break;
        case 3: ++p.ledger_revision; break;
        case 4: ++p.actor_revision; break;
        case 5: ++p.old_frozen_total; break;
        case 6: ++p.old_usable_xp; break;
        case 7: ++p.original_old_bank; break;
        case 8: ++p.active_usable_xp; break;
        case 9: ++p.active_bank; break;
        case 10: ++p.native_base_xp; break;
        case 11: ++p.kit; break;
        case 12: ++p.old_class; break;
        case 13: ++p.active_class; break;
        case 14: ++p.old_level_at_dual; break;
        case 15: ++p.active_level; break;
      }
      CBMD_Receipt r{}; CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_INVALID);
      CHECK(t.fake.commits==0 && t.fake.live.old_level==10); }
    { Fixture t; t.fake.reenter=true; auto rev=t.ready(); CHECK(t.fake.nested==CBMD_REENTRANT);
      CBMD_Receipt r{}; CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_OK);
      CHECK(t.fake.nested==CBMD_REENTRANT && t.fake.commits==1); }
    { Fixture a,b; CHECK(a.begin()==CBMD_OK); CHECK(b.begin()==CBMD_BUSY);
      CHECK(CBMD_Cancel(a.fake.context)==CBMD_OK); CHECK(b.begin()==CBMD_OK); }
    { Fixture t; t.fake.throw_prepare=true; CHECK(t.begin()==CBMD_ADAPTER_ERROR);
      CHECK(t.fake.discards==1 && t.fake.live.old_level==10); }
    { Fixture t; t.fake.fail_capture=true; CHECK(t.begin()==CBMD_ADAPTER_ERROR); }
    { Fixture t; t.fake.fail_prepare=true; CHECK(t.begin()==CBMD_ADAPTER_ERROR); }
    for (int throwing=0;throwing<2;++throwing) {
      Fixture t; auto rev=t.ready(); t.fake.throw_choose=throwing!=0; t.fake.fail_choose=!throwing;
      int choice=1; CHECK(CBMD_Choose(t.fake.context,&choice,sizeof(choice))==CBMD_ADAPTER_ERROR);
      CBMD_Receipt r{}; CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_ADAPTER_ERROR);
      CHECK(t.fake.live.old_level==10); }
    for (int uncertainty=0;uncertainty<3;++uncertainty) {
      Fixture t; auto rev=t.ready(); auto &f=t.fake; CBMD_Receipt r{};
      f.apply_before_error=true; f.commit_outcome=uncertainty==2 ? CBMD_APPLIED : CBMD_UNKNOWN;
      f.throw_commit=uncertainty==1; f.bad_receipt=uncertainty==2;
      CHECK(CBMD_Commit(f.context,rev,&r)==CBMD_INDETERMINATE);
      CHECK(CBMD_Commit(f.context,rev,&r)==CBMD_INDETERMINATE && f.commits==1);
      CHECK(CBMD_Cancel(f.context)==CBMD_INDETERMINATE);
      CHECK(CBMD_Destroy(f.context)==CBMD_INDETERMINATE);
      CHECK(CBMD_Reset(f.context)==CBMD_INDETERMINATE);
      CHECK(CBMD_Resolve(f.context,&r)==CBMD_INDETERMINATE);
      f.throw_resolve=true; CHECK(CBMD_Resolve(f.context,&r)==CBMD_INDETERMINATE);
      f.throw_resolve=false; f.resolve_outcome=CBMD_APPLIED;
      CHECK(CBMD_Resolve(f.context,&r)==CBMD_OK && f.live.old_level==11);
      CHECK(f.fake_hp==104 && f.fake_prof==3 && f.commits==1); }
    { Fixture t; auto rev=t.ready(); t.fake.commit_outcome=CBMD_UNKNOWN; CBMD_Receipt r{};
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_INDETERMINATE);
      t.fake.resolve_outcome=CBMD_UNCHANGED; CHECK(CBMD_Resolve(t.fake.context,&r)==CBMD_OK);
      CHECK(t.fake.live.old_level==10 && t.fake.live.ledger_revision==7); CHECK(t.begin()==CBMD_OK); }
    { Fixture t; auto rev=t.ready(); t.fake.commit_outcome=CBMD_UNCHANGED; CBMD_Receipt r{};
      CHECK(CBMD_Commit(t.fake.context,rev,&r)==CBMD_ADAPTER_ERROR);
      CHECK(t.fake.live.old_level==10 && t.fake.fake_hp==101); }
    { Fixture t; wrong_thread_calls(t.fake); // idle calls cannot claim the screen
      auto rev=t.ready(); wrong_thread_calls(t.fake); // preview/choices survive
      Fixture competitor; CHECK(competitor.begin()==CBMD_BUSY);
      CBMD_Receipt receipt{}; CHECK(CBMD_Commit(t.fake.context,rev,&receipt)==CBMD_OK);
      wrong_thread_calls(t.fake); // completed receipt cannot be cleared/destroyed
      CHECK(CBMD_Commit(t.fake.context,rev,&receipt)==CBMD_ALREADY_COMMITTED);
      CHECK(competitor.begin()==CBMD_OK); }
    { Fixture t; auto rev=t.ready(); t.fake.commit_outcome=CBMD_UNKNOWN;
      CBMD_Receipt receipt{}; CHECK(CBMD_Commit(t.fake.context,rev,&receipt)==CBMD_INDETERMINATE);
      wrong_thread_calls(t.fake); // only owner may resolve a native uncertainty
      Fixture competitor; CHECK(competitor.begin()==CBMD_BUSY);
      t.fake.resolve_outcome=CBMD_UNCHANGED;
      CHECK(CBMD_Resolve(t.fake.context,&receipt)==CBMD_OK);
      CHECK(competitor.begin()==CBMD_OK); }
    std::printf("{\"scenarios\":%u,\"checks\":%u,\"backend\":\"fake detached contract only\","
                "\"engine_binding_executed\":false,\"game_launched\":false}\n",scenarios,checks);
}
