#include "infinity_loader_common_api.h"
#include "lua_bindings_core_api.h"
#include "startup.h"
#include <limits>
#include <cstring>
namespace {
struct DigestCall{lua_State* state;int function;};
int bank_actor(uintptr_t expected,CBMS_BankActorChain* output,void* user) {
    auto& call=*static_cast<DigestCall*>(user);auto* L=call.state;const int top=lua_gettop(L);
    if(expected>9007199254740991ULL)return 0;
    lua_pushvalue(L,call.function);lua_pushnumber(L,static_cast<double>(expected));
    if(lua_pcall(L,1,1,0)||lua_type(L,-1)!=LUA_TTABLE){lua_settop(L,top);return 0;}
    CBMS_BankActorChain result{};bool valid=true;
    auto field=[&](const char* key){lua_pushstring(L,key);lua_rawget(L,-2);};
    auto number=[&](const char* key)->uintptr_t{
        field(key);const auto value=lua_tonumber(L,-1);
        const bool ok=lua_type(L,-1)==LUA_TNUMBER&&value>=1&&value<=9007199254740991.0;
        const auto integer=ok?static_cast<uintptr_t>(value):0;
        if(!ok||static_cast<double>(integer)!=value)valid=false;
        lua_settop(L,lua_gettop(L)-1);return integer;
    };
    const auto schema=number("schema");if(schema!=1)valid=false;result.schema=1;
    result.entry=number("entry");result.handler=number("handler");
    auto bytes=[&](const char* key,unsigned char out[7]){
        field(key);size_t size{};const auto* value=lua_type(L,-1)==LUA_TSTRING?lua_tolstring(L,-1,&size):nullptr;
        auto nibble=[](char c)->int{return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;};
        if(!value||size!=14)valid=false;
        else for(unsigned i=0;i<7;++i){const auto a=nibble(value[2*i]),b=nibble(value[2*i+1]);if(a<0||b<0)valid=false;else out[i]=static_cast<unsigned char>((a<<4)|b);}
        lua_settop(L,lua_gettop(L)-1);
    };
    bytes("original",result.original);bytes("replacement",result.replacement);
    lua_settop(L,top);if(!valid||result.entry!=expected)return 0;*output=result;return 1;
}
int digest(const char* name,const char* extension,unsigned char output[32],void* user) {
    auto& call=*static_cast<DigestCall*>(user);auto* L=call.state;const int top=lua_gettop(L);
    lua_pushvalue(L,call.function);lua_pushstring(L,name);lua_pushstring(L,extension);
    const int status=lua_pcall(L,2,1,0);size_t length{};
    const char* text=status==0&&lua_type(L,-1)==LUA_TSTRING?lua_tolstring(L,-1,&length):nullptr;
    bool valid=text&&length==64;
    auto nibble=[](char c)->int{return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;};
    for(unsigned i=0;valid&&i<32;++i){const auto a=nibble(text[2*i]),b=nibble(text[2*i+1]);if(a<0||b<0)valid=false;else output[i]=static_cast<unsigned char>((a<<4)|b);}
    lua_settop(L,top);return valid?1:0;
}
int start(lua_State* L) {
    size_t size{};const auto* bytes=lua_type(L,1)==LUA_TSTRING?lua_tolstring(L,1,&size):nullptr;
    DigestCall call{L,2};
    DigestCall bank{L,3};
    const int ok=bytes&&size<=UINT32_MAX&&lua_type(L,2)==LUA_TFUNCTION?
        CBMS_StartCurrentWithBank(bytes,static_cast<uint32_t>(size),digest,&call,
            lua_type(L,3)==LUA_TFUNCTION?bank_actor:nullptr,&bank):0;
    lua_pushboolean(L,ok);lua_pushstring(L,ok?"":CBMS_StartupError());return 2;
}
int status(lua_State* L){const auto ok=CBMS_StartupHealthy();lua_pushboolean(L,ok);lua_pushstring(L,CBMS_StartupError());return 2;}
int retained(lua_State* L){lua_pushboolean(L,CBMS_StartupRetained());return 1;}
}
void CBMS_OpenStartup(lua_State* L) {
    lua_pushcclosure(L,start,0);lua_setglobal(L,"CBMS_NativeStart");
    lua_pushcclosure(L,status,0);lua_setglobal(L,"CBMS_NativeStatus");
    lua_pushcclosure(L,retained,0);lua_setglobal(L,"CBMS_NativeRetained");
}
