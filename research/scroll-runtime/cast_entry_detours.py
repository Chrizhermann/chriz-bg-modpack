"""Audited eight native cast/child entry prefixes and partial unwind recipes."""
from item_detours import plan as entry_plan
SITES={
 'CGameEffect::FireSpell':('405553564154488d6c24d14881ece8000000','0112060012011d0006c0046003300250',True),
 'CGameAIBase::FireSpell':('48895c2420','0105020005340400',False),
 'CGameAIBase::FireSpellPoint':('48895c2420','0105020005340400',False),
 'CGameAIBase::ForceSpell':('48895c2418','0105020005340300',False),
 'CGameAIBase::ForceSpellPoint':('48895c2420','0105020005340400',False),
 'CGameSprite::Spell':('40555357415541564157488dac2478ffffff4881ec88010000','01190800190131000af008e006d0047003300250',True),
 'CGameSprite::SpellPoint':('4055535741554157488d6c24d04881ec30010000','011407001401260008f006d00470033002500000',True),
 'CSpell::GetAbilityEffect':('4053555657415641574883ec58','010d07000da209f007e005700460035002300000',True),
}
def plan(name,entry,relay,wrapper,observed):return entry_plan(name,entry,relay,wrapper,observed,definitions=SITES)
