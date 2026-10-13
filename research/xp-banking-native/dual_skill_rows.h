#pragma once
#include <cstddef>
#include <cstdint>
#define CBMDS_API extern "C" __declspec(dllexport)
struct CBMDS_Binding;
struct CBMDS_Row {uint32_t id,name_strref;int32_t base,display,limit,percentage;};
enum {CBMDS_OK=0,CBMDS_INVALID=1,CBMDS_IMAGE=2,CBMDS_THREAD=3,CBMDS_IDENTITY=4,CBMDS_RULES=5};
CBMDS_API int CBMDS_Bind(const void*,size_t,CBMDS_Binding**);
CBMDS_API int CBMDS_Query(CBMDS_Binding*,void* rules,void* actor,uint8_t old,uint32_t kit,CBMDS_Row* seven);
CBMDS_API int CBMDS_Destroy(CBMDS_Binding*);
CBMDS_API bool CBMDS_OnThread(CBMDS_Binding*);
