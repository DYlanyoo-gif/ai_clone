from __future__ import annotations

# Skill templates package.
# Import style modules to register all templates.
from app.skill_templates.base import (
    SkillTemplate, get_template, list_templates,
    register_template, safe_format_template,
)
from app.skill_templates import nuwa_style, dot_skill_style  # noqa: F401 — side-effect: register templates
