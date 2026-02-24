# CLAUDE.md — Instructions for Claude Code

## What is this project?

SWML-Agent: a single-file, zero-dependency coding agent powered by Ollama.
Built on SWML (Shunsuke's World Model Logic) — Hamiltonian mechanics applied to AI agents.

## Key constraints

- **Single file**: All agent code lives in `swml-agent.py`. Do not split into modules.
- **Zero deps**: Python stdlib only. No pip packages. No requirements.txt.
- **Python 3.8+**: No walrus operator (:=), no match/case, no newer syntax.
- **Ollama API**: All LLM calls go through localhost:11434. Use urllib, not requests.

## Architecture (read before editing)

The file is organized in sections marked with `═══` comment banners:
1. ANSI Colors & Terminal
2. SWML Core (OmegaState, VariationalPlanner, metrics)
3. Git Checkpoint
4. Ollama Client
5. Tools (ToolRegistry + individual tool functions)
6. System Prompt
7. Agent Loop (SWMLAgent class)
8. Banner & Main

## SWML physics mapping

- `OmegaState.H` = Hamiltonian (T + V)
- `OmegaState.L` = Lagrangian (T - V)
- `OmegaState.action_integral()` = S = ∫L dt
- `OmegaState.efficiency()` = η (1 - |S|/|S_worst|)
- `OmegaState.entropy()` = Shannon entropy of phase visits
- Phases: OBSERVE(H=1.2) → PLAN(H=1.0) → EXECUTE(H=1.1) → VERIFY(H=0.3)

## When adding features

1. Map every feature to a SWML concept (energy, action, entropy, etc.)
2. Keep tool functions as standalone `_tool_xxx()` functions
3. Register tools in `build_tool_registry()`
4. Update SYSTEM_PROMPT if the agent needs to know about new tools
5. Update the Banner version number

## Testing

```bash
python tests/test_omega.py    # Unit tests for Omega state
python swml-agent.py -p "list files in current directory" -y  # Smoke test
```

## Do not

- Add external dependencies (no pip)
- Split into multiple Python files (single-file constraint)
- Remove the physics concepts (they're the whole point)
- Change the Ω ❯ prompt symbol
- Add cloud/API key requirements
