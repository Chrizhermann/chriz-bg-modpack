// Uninstalled observational binding to FOUR audited manual +/- callsites only.
#pragma once
#include <cstdint>
#ifdef _WIN32
#define CBMDC_API extern "C" __declspec(dllexport)
#else
#define CBMDC_API extern "C"
#endif
struct CBMDC_Config { uint32_t abi;uintptr_t set_active,set_inactive,get_active,get_inactive; };
struct CBMDC_Event {
    uint64_t sequence;
    uintptr_t sprite,screen;
    uint32_t stat,inactive,screen_mode,screen_selected_class,status;
    int32_t requested,before,after;
};
CBMDC_API int CBMDC_Configure(const CBMDC_Config*);
CBMDC_API void CBMDC_Active(void* sprite,uint32_t stat,int32_t pips,int immediate,void* screen);
CBMDC_API void CBMDC_Inactive(void* sprite,uint32_t stat,int32_t pips,int immediate,void* screen);
CBMDC_API int CBMDC_Peek(CBMDC_Event*);
CBMDC_API int CBMDC_Acknowledge(uint64_t sequence);
CBMDC_API int CBMDC_Faulted();
CBMDC_API int CBMDC_SetSink(uintptr_t sink); // actual CBMDS_OnChoice
