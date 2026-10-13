#include "conditional_api.h"
#include "native_binder.hpp"
#include "decode_profiles.hpp"
#include "conditional_profiles.hpp"
#include "conditional_hook_group.hpp"
namespace {
cbm::scroll::hooks::Group entries;cbm::scroll::hooks::ConditionalGroup calls;
std::array<char,256> error{};
void fail(const char* why){const auto n=(std::min)(std::strlen(why),error.size()-1);std::memcpy(error.data(),why,n);error[n]=0;}
CBMS_ConditionalFunctions bind(uintptr_t base){
 using namespace cbm::scroll::binding;
 std::string detail;(void)cbm::scroll::binding::bind(base,detail);Image image(base);
 const auto timestamp=image.object<IMAGE_FILE_HEADER>(image.object<IMAGE_DOS_HEADER>(0).e_lfanew+4).TimeDateStamp;
 const ConditionalProfile* profile{};for(const auto& p:conditional_profiles)if(p.timestamp==timestamp)profile=&p;
 if(!profile)throw std::runtime_error("missing audited conditional scroll native profile");
 for(const auto& span:profile->spans){const auto actual=sha256(image.read(span.rva,span.size,true));if(!std::equal(actual.begin(),actual.end(),span.sha))throw std::runtime_error("conditional scroll body or lifecycle edge differs from audited ABI");}
 const auto fix=image.read(profile->fix,7,true);
 if(fix[0]!=0xE9||fix[5]!=0x90||fix[6]!=0x90)throw std::runtime_error("expected existing EEex SPLPROT context fix is absent or changed");
 int32_t relative{};std::memcpy(&relative,fix.data()+1,4);const auto target=static_cast<uintptr_t>(static_cast<int64_t>(image.address(profile->fix)+5)+relative);
 MEMORY_BASIC_INFORMATION page{};
 if(VirtualQuery(reinterpret_cast<void*>(target),&page,sizeof page)!=sizeof page||page.State!=MEM_COMMIT||page.Protect&(PAGE_GUARD|PAGE_NOACCESS))throw std::runtime_error("EEex SPLPROT fix target is unmapped");
 const auto access=page.Protect&0xFF;if(access!=PAGE_EXECUTE_READ&&access!=PAGE_EXECUTE_READWRITE&&access!=PAGE_EXECUTE_WRITECOPY)throw std::runtime_error("EEex SPLPROT fix target is not readable executable code");
 for(const auto& span:profile->spans)if(target>=image.address(span.rva)&&target<image.address(span.rva+span.size))throw std::runtime_error("EEex SPLPROT fix loops into native conditional body");
 if(target>=image.address(profile->fix)&&target<image.address(profile->fix+7))throw std::runtime_error("EEex SPLPROT fix loops into its hook site");
 CBMS_ConditionalFunctions out{};out.update=reinterpret_cast<CBMS_RepeatingUpdate>(image.address(profile->update));out.decode=reinterpret_cast<CBMS_RepeatingDecode>(image.address(profile->decoder));
 out.decode_call=image.address(profile->decode_call);out.fire326_return=image.address(profile->fire326_return);
 for(unsigned i=0;i<10;++i){out.calls[i]=image.address(profile->calls[i]);out.targets[i]=image.address(profile->targets[i]);}return out;
}
int install(const CBMS_ConditionalFunctions& f,CBMS_Runtime* runtime){
 const unsigned char prefix[]{0x40,0x53,0x41,0x56,0x48,0x83,0xEC,0x68};
 const unsigned char unwind[]{1,8,3,0,8,0xC2,4,0xE0,2,0x30,0,0},leaf[]{1,0,0,0};
 std::array<unsigned char,5> call{0xE8};const auto delta=static_cast<int64_t>(reinterpret_cast<uintptr_t>(f.decode))-static_cast<int64_t>(f.decode_call+5);
 if(delta<INT32_MIN||delta>INT32_MAX)throw std::runtime_error("repeating decoder CALL exceeds rel32 range");const auto relative=static_cast<int32_t>(delta);std::memcpy(call.data()+1,&relative,4);
 const std::array<cbm::scroll::hooks::Entry,2> recipe{{{reinterpret_cast<uintptr_t>(f.update),reinterpret_cast<uintptr_t>(CBMS_RepeatingCarrier),prefix,unwind,true},
  {f.decode_call,reinterpret_cast<uintptr_t>(CBMS_RepeatingDecodeCarrier),call,leaf,false,true}}};
 try{
  entries.install(recipe,[&](std::span<const uintptr_t> trampolines){auto actual=f;actual.update=reinterpret_cast<CBMS_RepeatingUpdate>(trampolines[0]);actual.decode=reinterpret_cast<CBMS_RepeatingDecode>(trampolines[1]);return CBMS_ConfigureConditional(runtime,&actual)==1;},[]{return CBMS_DetachConditional()==1;},[]{return CBMS_ConditionalIdle()==1;});
  calls.install(f);error.fill(0);return 1;
 }catch(...){if(entries.present()&&!calls.present()){try{entries.remove();}catch(...){}}throw;}
}
}
int CBMS_BindConditional(uintptr_t game,CBMS_ConditionalFunctions* out,char* text,uint32_t capacity){
 if(!out||!text||capacity<2)return 0;
 try{*out=bind(game);text[0]=0;return 1;}catch(const std::exception& e){const auto n=(std::min)(std::strlen(e.what()),std::size_t(capacity-1));std::memcpy(text,e.what(),n);text[n]=0;}return 0;
}
int CBMS_InstallConditionalHooks(uintptr_t game,CBMS_Runtime* runtime){try{return install(bind(game),runtime);}catch(const std::exception& e){fail(e.what());}catch(...){fail("conditional hook installation failed");}return 0;}
int CBMS_RemoveConditionalHooks(){try{entries.ready_remove();if(calls.present())calls.ready_remove();if(calls.present())calls.remove();entries.remove();error.fill(0);return 1;}catch(const std::exception& e){fail(e.what());}catch(...){fail("conditional hook removal failed");}return 0;}
const char* CBMS_ConditionalHookError(){return error.data();}
extern "C" int CBMS_ConditionalHooksPresent(){return entries.present()||calls.present()?1:0;}
#ifdef CBMS_OFFLINE_HARNESS
extern "C" CBMS_EXPORT int CBMS_TestInstallConditional(const CBMS_ConditionalFunctions* f,CBMS_Runtime* r){try{return install(*f,r);}catch(const std::exception& e){fail(e.what());}return 0;}
extern "C" CBMS_EXPORT uintptr_t CBMS_TestConditionalAllocation(int which){return which?calls.allocation():entries.allocation();}
#endif
