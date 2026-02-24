# AGENTS.md — SWML-Agent Development Guide

## Project Overview

SWML-Agent is a physics-based coding agent built on SWML (Shunsuke's World Model Logic).
It runs locally via Ollama with zero external dependencies.

**Core principle**: Tasks are energy states in Ω-space. The agent minimizes action S = ∫(T−V)dt.

## Architecture

```
swml-agent.py (single file)
├── ANSI Colors & Terminal utilities
├── SWML Core
│   ├── OmegaState — Phase tracking with Hamiltonian (H = T + V)
│   ├── VariationalPlanner — Plan scoring by predicted action
│   └── Metrics (entropy, efficiency η, action integral S)
├── Ollama Client
│   ├── Chat API (streaming)
│   ├── Model listing & info
│   └── Token tracking
├── Tools (10 built-in)
│   ├── read_file, write_file, edit_file, patch_file
│   ├── run_command, list_files, search_files
│   ├── think (reasoning), checkpoint, undo (git)
│   └── [extensible — add via ToolRegistry.register()]
├── GitCheckpoint — Auto-save/rollback via git
├── Agent Loop
│   ├── Phase detection (OBSERVE/PLAN/EXECUTE/VERIFY)
│   ├── Tool approval flow
│   ├── Multi-turn conversation
│   └── Ω-state rendering
└── CLI (argparse)
    ├── Interactive mode (Ω ❯ prompt)
    ├── One-shot mode (-p "prompt")
    └── Commands (/status, /models, /help, etc.)
```

## Design Principles

1. **Single file** — Everything in `swml-agent.py`. No packages, no imports beyond stdlib.
2. **Zero dependencies** — Only Python standard library. No pip install.
3. **Physics-first** — Every design decision maps to SWML concepts:
   - Phases → quantum states in Ω-space
   - Energy (H=T+V) → measurable complexity + uncertainty
   - Action (S=∫Ldt) → total computational effort
   - Efficiency (η) → how close to optimal path
4. **Local-first** — Ollama backend. No API keys, no cloud, no cost.
5. **Readable** — This is also a teaching tool. Code should be self-documenting.

## Coding Conventions

- **Python 3.8+ compatible** — No walrus operator, no match/case
- **Type hints** — Use them in function signatures
- **Docstrings** — Every class and public method
- **Constants** — UPPER_SNAKE_CASE at module level
- **Error handling** — Always catch exceptions in tools, never crash the agent loop
- **Output** — Use C.COLOR constants for terminal output. Respect NO_COLOR env var.

## SWML Concepts Reference

| Physics | Agent Equivalent |
|---------|-----------------|
| Hamiltonian H = T + V | Total energy of current phase |
| Kinetic energy T | Complexity of action being performed |
| Potential energy V | Uncertainty/entropy remaining |
| Lagrangian L = T - V | Net directed effort |
| Action S = ∫L dt | Total computational cost of task |
| Variational principle δS = 0 | Optimal execution path |
| Ground state | VERIFY phase (H = 0.3, minimum energy) |
| Phase transition | Moving between OBSERVE/PLAN/EXECUTE/VERIFY |
| Entropy | Shannon entropy of phase distribution |

## Adding New Tools

```python
def _tool_my_tool(param1: str, param2: int = 0) -> str:
    """Description of what this tool does."""
    try:
        # Do work
        return "Success message"
    except Exception as e:
        return f"Error: {e}"

# In build_tool_registry():
reg.register("my_tool", "Human-readable description",
    {"type": "object", "properties": {
        "param1": {"type": "string", "description": "What this param does"},
        "param2": {"type": "integer", "description": "Optional param"},
    }, "required": ["param1"]},
    _tool_my_tool)
```

## Testing

Run the test suite:
```bash
python -m pytest tests/ -v
# Or without pytest:
python tests/test_omega.py
```

## Contributing

1. Fork the repo
2. Create a feature branch
3. Keep everything in single file (swml-agent.py) unless it's tests or install scripts
4. Add tests for new features
5. Submit a PR with clear description mapping to SWML concepts

## Philosophy

> "The same math that describes particle physics can describe AI agents."
> — Shunsuke Hayashi

This project proves that claim. Every feature should reinforce it.
