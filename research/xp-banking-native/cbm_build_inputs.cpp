// What tools/sync_campaign_xp.py binds a packaged DLL to: the digest of the
// inputs its build froze, and that build's identifier. bank_build.ps1 passes
// both (CBM_BUILD_INPUTS, CBM_BUILD_ID); a builder script run on its own embeds
// neither, and no record or sync accepts its DLL. Variadic, so that an empty
// value (an unset variable in the batch line) still compiles under /W4 /WX.
#define CBM_TEXT_(...) #__VA_ARGS__
#define CBM_TEXT(...) CBM_TEXT_(__VA_ARGS__)
extern "C" __declspec(dllexport) const char CBM_BuildInputs[] =
    "cbm-build-inputs:" CBM_TEXT(CBM_BUILD_INPUTS) ":" CBM_TEXT(CBM_BUILD_ID);
