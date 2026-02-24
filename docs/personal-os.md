# SWML-Agent Personal OS — Context Engineering Architecture

## Philosophy

SWML-Agent doesn't just run code — it understands *you*.

Inspired by the principle that **context engineering > prompt engineering**,
SWML-Agent uses a file-based personal operating system that lives alongside your code.

The agent loads only what it needs (progressive disclosure), tracks your decisions
(episodic memory), and speaks in your voice (identity encoding).

## Directory Structure

When you run `swml-agent --init`, it creates:

```
.swml/
├── AGENT.md            # Agent behavior rules + decision table
├── IDENTITY.md         # Who you are (voice, values, goals)
├── CONTEXT.md          # Current project context (auto-updated)
├── memory/
│   ├── decisions.jsonl  # Key decisions with reasoning + outcomes
│   ├── failures.jsonl   # What went wrong + root cause + prevention
│   └── insights.jsonl   # Lessons learned, patterns discovered
├── sessions/
│   ├── latest.json      # Current session state
│   └── archive/         # Past sessions (auto-archived)
└── skills/
    └── README.md        # Custom skills (user-defined workflows)
```

## Progressive Disclosure (3 Levels)

### Level 1: Routing (always loaded)
- `AGENT.md` — 50-100 lines. Decision table mapping requests to actions.
- Tells the agent "this is a coding task" vs "this is a refactoring task"

### Level 2: Context (loaded per-task)
- `IDENTITY.md` — Voice, values, coding style preferences
- `CONTEXT.md` — Current project state, recent changes, active branches

### Level 3: Data (loaded on-demand)
- `memory/*.jsonl` — Historical decisions, failures, insights
- `sessions/*.json` — Conversation history for continuity
- `skills/*.md` — Custom workflows (e.g., /deploy, /review)

## AGENT.md Format

```markdown
# Agent Rules

## Decision Table
| User says | Action |
|-----------|--------|
| "fix bug" | OBSERVE: read error log → PLAN: identify root cause → EXECUTE: edit → VERIFY: run tests |
| "add feature" | OBSERVE: read related code → PLAN: design → EXECUTE: implement → VERIFY: test |
| "refactor" | OBSERVE: understand current → PLAN: identify improvements → EXECUTE: edit → VERIFY: compare |

## Coding Style
- Prefer functional over OOP
- Always add type hints
- Tests before implementation (TDD)

## Constraints
- Never delete files without confirmation
- Always run tests after changes
- Commit with conventional commit messages
```

## IDENTITY.md Format

```markdown
# Identity

## Voice (1-10 scale)
- Formal/Casual: 4
- Technical/Simple: 8
- Reserved/Expressive: 5
- Humble/Confident: 7

## Values
- Correctness > Speed
- Simplicity > Cleverness
- Tested > Untested

## Goals (current)
1. Ship v1.0 of the API
2. 90%+ test coverage
3. Clean documentation
```

## Memory System

### decisions.jsonl
```json
{"date": "2026-02-24", "decision": "Use SQLite over PostgreSQL", "reasoning": "Single-user app, no need for server", "alternatives": ["PostgreSQL", "MongoDB"], "outcome": "pending"}
```

### failures.jsonl
```json
{"date": "2026-02-24", "what": "Deploy failed on production", "root_cause": "Missing env var DATABASE_URL", "prevention": "Add env check to startup script", "severity": 8}
```

### insights.jsonl
```json
{"date": "2026-02-24", "insight": "Small PRs get reviewed 3x faster", "source": "observed over 2 weeks", "applies_to": ["git-workflow", "code-review"]}
```

## How It Maps to SWML

| Personal OS concept | SWML equivalent |
|---|---|
| Progressive disclosure | Minimizing V (potential/uncertainty) |
| Decision memory | Reducing action S by reusing past optimal paths |
| Failure tracking | Avoiding high-energy states (known failure modes) |
| Identity encoding | Constraining the agent's Ω-space to preferred regions |
| Session persistence | Continuity of the wave function across time |

The agent isn't just coding — it's evolving its understanding of you
and your project, converging toward your personal ground state.
```

## Integration with Ω-Space

When SWML-Agent loads your `.swml/` directory:

1. **OBSERVE phase uses** `AGENT.md` + `CONTEXT.md` to understand the request
2. **PLAN phase uses** `memory/decisions.jsonl` to reference past approaches
3. **EXECUTE phase uses** `IDENTITY.md` for coding style constraints
4. **VERIFY phase uses** `memory/failures.jsonl` to check known failure patterns

Each file reduces the agent's potential energy V (uncertainty),
making the path to ground state shorter and more efficient.
