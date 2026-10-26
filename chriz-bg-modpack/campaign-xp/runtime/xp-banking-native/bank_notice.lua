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
-- An opcode-104 XP change the bank cannot take runs the game's own effect; no
-- refusal may stop the effect list (CEBG #19). A stat44 setter write (script
-- ChangeStat) it cannot take runs the game's own setter code, counted as
-- "write" too, so the log line says "code". A change whose actor's lifetime
-- ended while the bank prepared it (status 11) ran nothing: it gets its own log
-- line. So does a setter write kept unwritten (status 12): another thread
-- created or destroyed a character at the address of its character, which may
-- now be another; the line lists what was kept. These are loader-log lines
-- only: nothing technical is shown in the game (Christopher, 2026-10-25). The
-- native counts are process-wide: each loaded game counts from its start and
-- logs each line once.
local fallbackWhy={[2]="not on the game thread",[3]="no actor identity",
 [4]="an earlier XP change awaits reconciliation",[5]="the bank refused it",
 [7]="it did not finish normally and its journal awaits reconciliation",
 [8]="it changed while the bank prepared it",[9]="the game was saving",
 [10]="another XP change of that character was in progress"}
local function fallbackCount()
 local total,award,writer,ended,kept,keptList=M.fallbacks()
 assert(type(total)=="number"and total>=0 and total%1==0,
  type(award)=="string"and award or"Native XP fallback count unavailable")
 assert(ended==nil or type(ended)=="number"and ended>=0 and ended%1==0,"Native ended-lifetime count unavailable")
 assert(kept==nil or type(kept)=="number"and kept>=0 and kept%1==0 and type(keptList)=="string",
  "Native kept-write count unavailable")
 return total,award,writer,ended,kept,keptList
end
local function logEnded(ended)
 if M.endedLogged then return end
 if ended==nil then M.endedLogged=true;return end -- This count source has none.
 local count=ended-M.endedBase
 if count<=0 then return end
 M.endedLogged=true
 report(("%d XP change%s in this game (%d since launch) wrote nothing: the character's lifetime ended while the bank prepared %s (status 11). Later ones in this game are not logged.")
  :format(count,count==1 and""or"s",ended,count==1 and"it"or"them"))
end
local function logKept(kept,list)
 if M.keptLogged then return end
 if kept==nil then M.keptLogged=true;return end -- This count source has none.
 local count=kept-M.keptBase
 if count<=0 then return end
 M.keptLogged=true
 report(("%d XP setter write%s in this game (%d since launch: %s) %s kept and not applied: another thread created or destroyed a character at %s, which may now hold another character (status 12). XP is not banked again until the game restarts. Later ones in this game are not logged.")
  :format(count,count==1 and""or"s",kept,list,count==1 and"was"or"were",
   count==1 and"the address of the character it was meant for"or"the addresses of the characters they were meant for"))
end
function M.FlushFallbacks()
 if not M.installed or not M.fallbacks or (M.fallbackLogged and M.endedLogged and M.keptLogged) then
  return true,0
 end
 local ok,total,award,writer,ended,kept,keptList=pcall(fallbackCount)
 if not ok then M.fallbacks=nil;report(total);return false,0,tostring(total)end
 logEnded(ended)
 logKept(kept,keptList)
 if M.fallbackLogged then return true,0 end
 local count=total-M.fallbackBase
 if count<=0 then return true,0 end
 M.fallbackLogged=true
 local last={}
 if fallbackWhy[award]then last[#last+1]="award: "..fallbackWhy[award]end
 if fallbackWhy[writer]then last[#last+1]="write: "..fallbackWhy[writer]end
 -- The process total keeps each game's line distinct; the runtime's report
 -- drops a line that repeats the one before it.
 report(("%d XP change%s in this game (%d since launch) ran the game's own code without the bank (last %s). Later ones in this game are not announced.")
  :format(count,count==1 and""or"s",total,#last>0 and table.concat(last,"; ")or"reason unknown"))
 return true,count
end
-- A destroyed game: the next one counts from here and logs its own lines.
function M.ResetGame()
 if not M.installed or not M.fallbacks then return end
 local ok,total,_,_,ended,kept=pcall(fallbackCount)
 if ok then
  M.fallbackBase,M.fallbackLogged,M.endedBase,M.endedLogged=total,false,ended or 0,false
  M.keptBase,M.keptLogged=kept or 0,false
 else M.fallbacks=nil;report(total)end
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
 M.fallbacks=nil;M.fallbackBase=nil;M.fallbackLogged=nil
 M.endedBase=nil;M.endedLogged=nil;M.keptBase=nil;M.keptLogged=nil
 return true
end
function M.Install(o)
 assert(not M.installed and o and o.researchOnly==true,"Explicit research notice setup required")
 assert(o.runtime and type(o.runtime.PendingNotices)=="function"and type(o.runtime.AckNotice)=="function"
  and type(o.runtime.Status)=="function","Saved runtime notice APIs required")
 assert(o.reset and type(o.reset.NativeCap)=="function","Actual native cap reader required")
 assert(o.fallbacks==nil or type(o.fallbacks)=="function","Native XP fallback count must be a function")
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
 -- The bridges count from zero; they load with this bootstrap, before any game.
 M.fallbacks=o.fallbacks;M.fallbackBase=0;M.fallbackLogged=false
 M.endedBase=0;M.endedLogged=false;M.keptBase=0;M.keptLogged=false
 M.listener=function(sprite)
  local ok,problem=pcall(M.Flush,sprite);if not ok then report(problem)end
  ok,problem=pcall(M.FlushFallbacks);if not ok then report(problem)end
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
