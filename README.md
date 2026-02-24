# SWML-Agent

**Physics-based coding agent. Minimizing action in Ω-space.**

```
H = T + V    (Hamiltonian = kinetic + potential)
S = ∫(T−V)dt → min    (variational principle)
```

The world's first coding agent built on [SWML (Shunsuke's World Model Logic)](https://github.com/ShunsukeHayashi/HAYASHI_SHUNSUKE) — a mathematical framework that describes AI agent behavior using Hamiltonian mechanics and variational principles.

Tasks are energy states. The agent finds the path of least action — just like nature.

```
  ███████╗██╗    ██╗███╗   ███╗██╗            
  ██╔════╝██║    ██║████╗ ████║██║            
  ███████╗██║ █╗ ██║██╔████╔██║██║            
  ╚════██║██║███╗██║██║╚██╔╝██║██║            
  ███████║╚███╔███╔╝██║ ╚═╝ ██║███████╗      
  ╚══════╝ ╚══╝╚══╝ ╚═╝     ╚═╝╚══════╝      
       A G E N T
```

## What makes this different?

Every other coding agent is a glorified while-loop: prompt → tool call → repeat.

SWML-Agent operates in **Ω-space** — a state space where each phase has a measurable Hamiltonian:

| Phase | T (kinetic) | V (potential) | H (total) | Meaning |
|-------|------------|---------------|-----------|---------|
| 🔭 OBSERVE | 0.3 | 0.9 | 1.2 | Low action, high uncertainty |
| 📐 PLAN | 0.5 | 0.5 | 1.0 | Building structure, reducing entropy |
| ⚡ EXECUTE | 0.9 | 0.2 | 1.1 | High action, low uncertainty |
| ✓ VERIFY | 0.2 | 0.1 | 0.3 | Ground state. Convergence. |

The agent minimizes **total action S = ∫(T−V)dt** — the same principle that governs photon paths, planetary orbits, and quantum field theory.

### Real-time Ω display

```
╔════════════════════════════════════════════════════════╗
║ 🔭 OBSERVE → 📐 PLAN → ⚡ EXECUTE → ✓ VERIFY         ║
║                                                        ║
║  H=1.10  T=0.9 ▓▓▓▓▓▓▓▓▓▓▓▓▓░░  V=0.2 ▓▓▓░░░░░░░░░ ║
║  S=-0.342  steps=3  tools=5  t=14.2s                   ║
║  η=78%  entropy=1.58  tokens=1240→890                  ║
║  task: Create a Python web server with health check    ║
╚════════════════════════════════════════════════════════╝
```

Plus an ASCII energy trajectory plot showing H(t) over time.

## Quick Start

```bash
# 1. Install Ollama
# https://ollama.com/download

# 2. Pull a model
ollama pull qwen3-coder     # 30B — best quality
# or
ollama pull qwen3:8b        # 8B — faster, lighter

# 3. Run
python swml-agent.py
```

No pip install. No node_modules. No API keys. One file.

## Usage

```bash
# Interactive mode
python swml-agent.py

# One-shot
python swml-agent.py -p "Create a REST API with SQLite backend"

# Specify model
python swml-agent.py --model qwen3:8b

# Auto-approve all tool calls (yolo mode)
python swml-agent.py -y

# Switch model mid-session
Ω ❯ /model qwen3:8b
```

## Features

- 🔬 **Ω-space state tracking** — Hamiltonian decomposition (H = T + V) in real-time
- 📐 **Action integral** — S = ∫(T−V)dt measures computational "effort"
- 📊 **Efficiency metric** — η = how close to optimal path (%)
- 📈 **Energy trajectory** — ASCII plot of H(t) over time
- 🔀 **Variational planner** — Scores multiple plans by predicted action
- 🛠️ **10 built-in tools** — read, write, edit, patch, run, list, search, think, checkpoint, undo
- 💾 **Git checkpoints** — Auto-save before risky changes, undo to rollback
- 🧠 **Think tool** — Internal reasoning without side effects
- 📦 **Zero dependencies** — Python stdlib only, single file (~900 lines)
- 🏠 **Fully local** — Ollama backend, no cloud, no cost

## The Physics

In classical mechanics, nature finds the path that minimizes action:

```
S = ∫ L(q, q̇, t) dt    where L = T - V
```

**T** = kinetic energy (how hard the agent is working)
**V** = potential energy (how much uncertainty remains)
**H** = T + V (total energy, the Hamiltonian)
**S** = total action (the integral we minimize)
**η** = efficiency (1 - |S_actual| / |S_worst|)

A good agent:
- Spends minimal time in high-V states (confusion, exploration)
- Applies high-T actions only when V is already low (directed execution)
- Converges quickly to ground state (VERIFY, H=0.3)

This is the **variational principle** — the deepest optimization algorithm in physics, now applied to software engineering.

## Commands

| Command | Description |
|---------|-------------|
| `/status` | Show current Ω-state and trajectory |
| `/models` | List available Ollama models |
| `/model X` | Switch to model X |
| `/undo` | Rollback last git checkpoint |
| `/help` | Show help |
| `/quit` | Exit |

## Hardware Requirements

| Setup | Model | Speed | Quality |
|-------|-------|-------|---------|
| 8GB VRAM | qwen3:8b | ~50 tok/s | ★★★ |
| 12GB VRAM | qwen3-coder (30B Q4) | ~10-15 tok/s | ★★★★★ |
| 16GB+ VRAM | qwen3-coder (30B Q8) | ~20-30 tok/s | ★★★★★ |
| 24GB VRAM | qwen3-coder (30B FP16) | ~30-40 tok/s | ★★★★★ |

Works on Mac (Apple Silicon), Windows (NVIDIA), and Linux.

## Comparison

| | Claude Code | vibe-local | **SWML-Agent** |
|--|------------|-----------|--------------|
| Cost | $20+/mo + API | Free | **Free** |
| Local | ✗ | ✓ | **✓** |
| Dependencies | Node.js | Python | **Python (stdlib only)** |
| Lines of code | ~100k+ | ~7400 | **~900** |
| Theoretical basis | None | None | **SWML (Hamiltonian mechanics)** |
| Energy tracking | ✗ | ✗ | **✓ (H, S, η, entropy)** |
| Git checkpoints | ✗ | ✓ | **✓** |
| Variational planning | ✗ | ✗ | **✓** |

## Inspired by

- [vibe-local](https://github.com/ochyai/vibe-local) by Yoichi Ochiai — proved single-file local agents work
- [SWML Theory](https://github.com/ShunsukeHayashi/HAYASHI_SHUNSUKE) — the math behind this agent
- Hamilton, Lagrange, Feynman — the variational principle

## Author

**Shunsuke Hayashi** ([@swml_lab](https://x.com/swml_lab))

Physics M.Sc. → Factory optimization → Amazon operations management → AI agent architecture.

The same math that describes particle physics describes AI agents. This is the proof.

## License

MIT
