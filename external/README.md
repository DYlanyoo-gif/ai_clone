# External Skill Repositories

This directory stores upstream repositories as Git submodules. They are kept separate from AI Clone glue code.

| Directory | Upstream | Status | Used For |
|-----------|----------|--------|----------|
| `external/nuwa-skill` | https://github.com/alchaincyf/nuwa-skill | imported | Read README / SKILL / references to generate Nuwa-compatible profile skill packages |
| `external/colleague-skill` | https://github.com/titanwings/colleague-skill | imported | Read README / SKILL / prompts to generate dot-skill-compatible Persona + Work packages |

AI Clone does not automatically run upstream collectors, writer tools, host installers, or unstable CLI flows. Generated packages are written under:

```text
generated_skills/{profile_slug}/nuwa/
generated_skills/{profile_slug}/colleague/
```

Generated ZIP files include only generated package files. They do not include uploaded source files, SQLite databases, `.env`, secret credentials, or Git remotes.

Runtime validation is handled by AI Clone glue code, not by these upstream repositories:

- L4: compatible package generated
- L5a: local structure validation passed
- L5b: local dry-run simulation completed
- L5c: actual external runtime execution, which must be performed manually after installing the package into Codex, Claude Code, Hermes, or another compatible runtime
