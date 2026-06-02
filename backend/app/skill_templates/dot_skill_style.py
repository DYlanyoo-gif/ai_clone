from __future__ import annotations

from app.skill_templates.base import (
    SkillTemplate, register_template,
    DEEP_ANALYSIS_SYSTEM_PROMPT, DEEP_STYLE_CARD_SYSTEM_PROMPT,
    CHAT_SYSTEM_TEMPLATE,
)

# ── Dot-skill style: Relationship-based profiles ──
# Uses the unified deep analysis prompt (14-module Markdown report) and
# deep style card prompt (10-section executable style card).
# The relationship type context is passed in the user prompt, not hardcoded.

register_template(SkillTemplate(
    template_name="dot_colleague",
    target_type="colleague",
    description="同事 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))

register_template(SkillTemplate(
    template_name="dot_friend",
    target_type="friend",
    description="朋友 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))

register_template(SkillTemplate(
    template_name="dot_family",
    target_type="family",
    description="家人/亲人 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))

register_template(SkillTemplate(
    template_name="dot_lover",
    target_type="lover",
    description="伴侣/白月光 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))

register_template(SkillTemplate(
    template_name="dot_other",
    target_type="other",
    description="其他 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))
