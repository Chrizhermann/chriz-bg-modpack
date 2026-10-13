"""Concrete dispatch/action-construction/message lifetime entry trampolines.
Exact prefixes were read in both images by dispatch_native_audit.py. Original
EH handlers remain attached to native bodies; these nonthrowing partial
prologues need only their actual saved-register/stack unwind operations.
"""
from item_detours import plan as entry_plan
SITES={
    'apply146':('405556574157488dac2448ffffff4881ecb8010000','011506001501370006f0047003600250',True),
    'apply148':('48895c2418','0105020005340300',False),
    'action_default':('40534883ec50','0106020006920230',True),
    'add_message':('48895c2408','0105020005340100',False),
    'fire_message_run':('40534883ec60','0106020006b20230',True),
    'fire_message_destroy':('48895c2408','0105020005340100',False),
}
def plan(name,entry,relay,wrapper,observed):
    return entry_plan(name,entry,relay,wrapper,observed,definitions=SITES)
