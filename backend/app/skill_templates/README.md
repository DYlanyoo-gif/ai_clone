# Skill Templates

This directory contains the skill template system for AI Clone character distillation.

## Design Philosophy

The template system is inspired by the **Skill.md** format used by projects like [nuwa-skill](https://github.com/nuwa-skill/nuwa-skill) and [dot-skill](https://github.com/dot-skill/dot-skill). These projects define structured templates that describe how an AI should analyze a person's text and emulate their communication style.

**Important**: This project does NOT copy source code from nuwa-skill or dot-skill. We implement our own compatible template layer using Chinese-language templates. If you wish to formally integrate the original repositories, please review their licenses and runtime requirements.

## Template Structure

Each `.skill.md` file defines:

| Section | Purpose |
|---------|---------|
| `name` | Template identifier |
| `target_type` | Relationship type this template targets |
| `purpose` | What this template is designed to do |
| `analysis_dimensions` | Dimensions analyzed during portrait generation |
| `style_card_rules` | Rules for generating the executable style card |
| `chat_rules` | Rules for chat behavior when using this template |
| `safety_boundaries` | Hard boundaries that must never be crossed |

## Available Templates

### nuwa_public_figure.skill.md
- **Target**: public_figure, author, celebrity
- **Style**: Deep analysis of public personas, mental models, decision heuristics
- **Source inspiration**: nuwa-skill's approach to analyzing public figures

### dot_relationship.skill.md
- **Target**: colleague, friend, family, lover, other
- **Style**: Relationship-aware analysis, adjusting intimacy and boundaries
- **Source inspiration**: dot-skill's relationship-oriented template approach

## How Templates Are Used

1. When a profile is created with a `relationship_type`, the system selects the matching template.
2. During analysis (`generate_analysis_report`), the template's analysis dimensions guide the LLM.
3. During chat, the template's style card rules and chat rules are injected into the system prompt.
4. The `.skill.md` files serve as documentation and can be imported/exported.

## Fallback

If a `.skill.md` file is missing or corrupted, the system falls back to Python-built-in templates defined in `base.py`. The system never crashes due to missing template files.

## Adding Custom Templates

1. Create a new `.skill.md` file in `templates/` following the structure above.
2. Register it in code by adding a `register_template()` call in `nuwa_style.py` or `dot_skill_style.py`.
3. Restart the backend.

## Relationship to External Projects

| Project | Our Integration | Status |
|---------|----------------|--------|
| [nuwa-skill](https://github.com/nuwa-skill/nuwa-skill) | Template concept only | No code copied |
| [dot-skill](https://github.com/dot-skill/dot-skill) | Template concept only | No code copied |

For full integration with the original repositories, check their license terms and runtime dependencies.
