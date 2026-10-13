-- UNINSTALLED. Presentation only; the runtime owns event generation, saved
-- receipts and accounting. Loading this module registers nothing.
local M={installed=false}
local busy={}
local function named(sprite,text)
 -- Same generated native CString field used by pinned EEex_Debug.lua:85.
 -- A missing/unavailable display name is cosmetic and cannot gate a notice.
 local ok,name=pcall(function()return sprite.m_sName.m_pchData:get()end)
 return ok and type(name)=="string"and #name>0 and(name..": "..text)or text
end
local function report(problem)
 local message="Campaign XP notice: "..tostring(problem)
 if M.runtime and type(M.runtime.Report)=="function"then pcall(M.runtime.Report,message)
 else print(message)end
end
function M.Flush(sprite)
 if not M.installed or sprite==nil then return true,0 end
 local key
 local ok,done,why=pcall(function()
  local pending=M.runtime.PendingNotices(sprite)
  if pending==nil then return 0 end
  assert(type(pending)=="table"and type(pending.ownerKey)=="string"and type(pending.incarnation)=="string"
   and type(pending.items)=="table","Malformed owned notice queue")
  key=pending.ownerKey..":"..pending.incarnation
  if busy[key]then key=nil;return 0 end
  busy[key]=true
  local count=0
  for _,item in ipairs(pending.items)do
   assert(type(item)=="table"and type(item.key)=="string"and type(item.text)=="string","Malformed owned notice item")
   -- Display is intentionally before acknowledgment. A display error keeps
   -- this and later entries. A process crash between the two may repeat text;
   -- display and a saved acknowledgment cannot be one native transaction.
   Infinity_DisplayString(named(sprite,item.text))
   if not M.runtime.AckNotice(sprite,pending.ownerKey,pending.incarnation,item.key)then
    return count,"Notice owner or pending receipt changed during display"
   end
   count=count+1
  end
  return count
 end)
 if key then busy[key]=nil end
 if not ok then report(done);return false,0,tostring(done)end
 if why then report(why);return false,done,why end
 return true,done
end
function M.Status(sprite)
 if not M.installed then return nil,"Campaign XP presentation is not installed"end
 local ok,text=pcall(function()
  sprite=sprite or EEex_Sprite_GetSelected()
  if not sprite then return "Select a party member to see campaign XP."end
  local result=M.runtime.Status(sprite,M.reset.NativeCap(sprite))
  assert(type(result)=="string","Campaign XP status text unavailable")
  M.Flush(sprite)
  return named(sprite,result)
 end)
 if not ok then report(text);text="Campaign XP status is unavailable; see the diagnostic log."end
 local shown,problem=pcall(Infinity_DisplayString,text)
 if not shown then report(problem);return nil,tostring(problem)end
 return text
end
local function removeListener(list,listener)
 if type(list)~="table"or not listener then return end
 for i=#list,1,-1 do if list[i]==listener then table.remove(list,i)end end
end
function M.Remove()
 removeListener(M.listenerList,M.listener)
 if EEex_Action_Private_SpriteStartedActionListeners~=M.listenerList then
  removeListener(EEex_Action_Private_SpriteStartedActionListeners,M.listener)
 end
 if CBMBank_Status==M.statusGlobal then CBMBank_Status=nil end
 if M.keyCallback and type(EEex_Keybinds_Private_Definitions)=="table"then
  local current=EEex_Keybinds_Private_Definitions.CBMBank_Status
  if current and current.callback==M.keyCallback then
   EEex_Keybinds_Reset("CBMBank_Status")
   EEex_Keybinds_Private_Definitions.CBMBank_Status=nil
  end
 end
 M.installed=false;M.listener=nil;M.listenerList=nil;M.statusGlobal=nil;M.keyCallback=nil;busy={}
 return true
end
function M.Install(o)
 assert(not M.installed and o and o.researchOnly==true,"Explicit research notice setup required")
 assert(o.runtime and type(o.runtime.PendingNotices)=="function"and type(o.runtime.AckNotice)=="function"
  and type(o.runtime.Status)=="function","Saved runtime notice APIs required")
 assert(o.reset and type(o.reset.NativeCap)=="function","Actual native cap reader required")
 assert(type(Infinity_DisplayString)=="function"and type(EEex_Sprite_GetSelected)=="function"
  and type(EEex_Action_AddSpriteStartedActionListener)=="function"
  and type(EEex_Action_Private_SpriteStartedActionListeners)=="table","Native presentation/action APIs unavailable")
 assert(CBMBank_Status==nil,"Campaign XP status namespace occupied")
 if o.keybind then
  assert(type(o.keybind.keys)=="table"and #o.keybind.keys>0,"Explicit status key sequence required")
  assert(type(EEex_Keybinds_Get)=="function"and type(EEex_Keybinds_Update)=="function"
   and type(EEex_Keybinds_Reset)=="function"and type(EEex_Keybinds_Private_Definitions)=="table","Native keybind APIs unavailable")
  assert(EEex_Keybinds_Get("CBMBank_Status")==nil,"Campaign XP status keybind namespace occupied")
 end
 M.runtime=o.runtime;M.reset=o.reset
 M.listener=function(sprite)
  local ok,problem=pcall(M.Flush,sprite);if not ok then report(problem)end
  -- No action-status number and no action/queue mutation.
 end
 M.statusGlobal=function()M.Status()end
 M.listenerList=EEex_Action_Private_SpriteStartedActionListeners
 local ok,problem=pcall(function()
  EEex_Action_AddSpriteStartedActionListener(M.listener)
  CBMBank_Status=M.statusGlobal
  if o.keybind then
   M.keyCallback=function()M.Status()end
   EEex_Keybinds_Update("CBMBank_Status",{keys=o.keybind.keys,modifierKeys=o.keybind.modifierKeys or{},
    fireType=o.keybind.fireType==nil and EEex_Keybinds_FireType.UP or o.keybind.fireType,callback=M.keyCallback})
  end
  M.installed=true
 end)
 if not ok then M.Remove();error(problem)end
 return M
end
return M
