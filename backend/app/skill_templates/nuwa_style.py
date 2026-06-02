from __future__ import annotations

from app.skill_templates.base import (
    SkillTemplate, register_template,
    DEEP_ANALYSIS_SYSTEM_PROMPT, DEEP_STYLE_CARD_SYSTEM_PROMPT,
    CHAT_SYSTEM_TEMPLATE,
)

# ── Nuwa-style: Public figures, authors, thinkers, celebrities ──
# Uses the unified deep analysis prompt (14-module Markdown report) and
# deep style card prompt (10-section executable style card).
# The relationship type context is passed in the user prompt, not hardcoded.

register_template(SkillTemplate(
    template_name="nuwa_public_figure",
    target_type="public_figure",
    description="公众人物 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))

register_template(SkillTemplate(
    template_name="nuwa_author",
    target_type="author",
    description="作者/IP — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))

register_template(SkillTemplate(
    template_name="nuwa_celebrity",
    target_type="celebrity",
    description="知名人物 — 深度人物画像、可执行风格卡、自然语气对话",
    analysis_system_prompt=DEEP_ANALYSIS_SYSTEM_PROMPT,
    style_card_system_prompt=DEEP_STYLE_CARD_SYSTEM_PROMPT,
    chat_system_template=CHAT_SYSTEM_TEMPLATE,
))
