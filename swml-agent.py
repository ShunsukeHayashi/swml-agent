#!/usr/bin/env python3
"""
swml-agent — Physics-based coding agent powered by local LLMs

The world's first coding agent built on SWML (Shunsuke's World Model Logic).
Tasks are treated as energy states in Ω-space. The agent minimizes action
along the optimal execution path — just like nature does.

Single file. Zero dependencies. Fully local via Ollama.

Usage:
    python swml-agent.py                          # interactive mode
    python swml-agent.py -p "create a web server" # one-shot
    python swml-agent.py --model qwen3:8b         # specify model
    python swml-agent.py -y                       # auto-approve tools

Author: Shunsuke Hayashi (@swml_lab)
License: MIT
"""

import json
import os
import sys
import re
import time
import signal
import argparse
import subprocess
import shutil
import threading
import traceback
import urllib.request
import urllib.error
import platform
import math
import hashlib
import difflib
import glob
from pathlib import Path
from datetime import datetime

__version__ = "0.2.0"

# ════════════════════════════════════════════════════════════════════════════════
# ANSI Colors & Terminal
# ════════════════════════════════════════════════════════════════════════════════

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    GRAY    = "\033[90m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"
    BCYAN   = "\033[96m"
    BMAGENTA= "\033[95m"

    @classmethod
    def disable(cls):
        for attr in dir(cls):
            if attr.isupper() and isinstance(getattr(cls, attr), str):
                setattr(cls, attr, "")

if os.name == "nt":
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        m = ctypes.c_ulong()
        k.GetConsoleMode(h, ctypes.byref(m))
        k.SetConsoleMode(h, m.value | 0x0004)
    except Exception:
        pass

if not sys.stdout.isatty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
    C.disable()

def term_width():
    try:
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80

# ════════════════════════════════════════════════════════════════════════════════
# SWML Core — Ω-Space, Hamiltonian, Variational Principle
# ════════════════════════════════════════════════════════════════════════════════

class OmegaState:
    """Agent state in Ω-space with measurable energy.
    
    The Hamiltonian H(q,p,t) governs the agent's evolution:
      H = T(kinetic/complexity) + V(potential/uncertainty)
    
    The agent traverses: OBSERVE → PLAN → EXECUTE → VERIFY
    minimizing total action S = ∫ L dt where L = T - V
    """
    
    PHASES = ["OBSERVE", "PLAN", "EXECUTE", "VERIFY"]
    PHASE_SYMBOLS = {"OBSERVE": "🔭", "PLAN": "📐", "EXECUTE": "⚡", "VERIFY": "✓"}
    
    # Energy decomposition: (kinetic=complexity, potential=uncertainty)
    PHASE_ENERGY = {
        "OBSERVE": (0.3, 0.9),  # Low action, high uncertainty
        "PLAN":    (0.5, 0.5),  # Building structure, reducing uncertainty
        "EXECUTE": (0.9, 0.2),  # High action, low uncertainty
        "VERIFY":  (0.2, 0.1),  # Minimal — ground state
    }
    
    def __init__(self):
        self.phase = "OBSERVE"
        self.phase_index = 0
        self.step_count = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.start_time = time.time()
        self.history = []  # [(phase, T, V, timestamp)]
        self._record()
    
    def transition(self, new_phase):
        if new_phase in self.PHASES and new_phase != self.phase:
            old = self.phase
            self.phase = new_phase
            self.phase_index = self.PHASES.index(new_phase)
            self.step_count += 1
            self._record()
            return old, new_phase
        return None, None
    
    def _record(self):
        T, V = self.PHASE_ENERGY[self.phase]
        self.history.append((self.phase, T, V, time.time()))
    
    @property
    def T(self):
        return self.PHASE_ENERGY[self.phase][0]
    
    @property
    def V(self):
        return self.PHASE_ENERGY[self.phase][1]
    
    @property
    def H(self):
        """Hamiltonian H = T + V (total energy)"""
        return self.T + self.V
    
    @property
    def L(self):
        """Lagrangian L = T - V"""
        return self.T - self.V
    
    def action_integral(self):
        """S = ∫ L dt — total action along the path."""
        if len(self.history) < 2:
            return 0.0
        S = 0.0
        for i in range(1, len(self.history)):
            T_prev, V_prev = self.history[i-1][1], self.history[i-1][2]
            dt = self.history[i][3] - self.history[i-1][3]
            L = T_prev - V_prev  # Lagrangian
            S += L * dt
        return S
    
    def entropy(self):
        """Shannon entropy of phase distribution — measures exploration breadth."""
        counts = {}
        for h in self.history:
            counts[h[0]] = counts.get(h[0], 0) + 1
        total = len(self.history)
        if total == 0:
            return 0.0
        H = 0.0
        for c in counts.values():
            p = c / total
            if p > 0:
                H -= p * math.log2(p)
        return H
    
    def efficiency(self):
        """η = 1 - (actual_action / worst_case_action). Higher = more efficient."""
        if len(self.history) < 2:
            return 1.0
        elapsed = self.history[-1][3] - self.history[0][3]
        if elapsed <= 0:
            return 1.0
        worst_S = 1.2 * elapsed  # worst case: stuck in OBSERVE (T=0.3, V=0.9, H=1.2)
        actual_S = abs(self.action_integral())
        return max(0.0, min(1.0, 1.0 - actual_S / worst_S)) if worst_S > 0 else 1.0

    def render(self, task_desc="", compact=False):
        elapsed = time.time() - self.start_time
        S = self.action_integral()
        eta = self.efficiency()
        
        # Phase progression
        phases_str = ""
        for i, p in enumerate(self.PHASES):
            sym = self.PHASE_SYMBOLS[p]
            if p == self.phase:
                phases_str += f"{C.BGREEN}{C.BOLD}{sym} {p}{C.RESET}"
            elif i < self.phase_index:
                phases_str += f"{C.GREEN}{sym} {p}{C.RESET}"
            else:
                phases_str += f"{C.DIM}{sym} {p}{C.RESET}"
            if i < len(self.PHASES) - 1:
                phases_str += f" {C.DIM}→{C.RESET} "
        
        # Energy bars
        w = 15
        t_bar = "▓" * int(self.T * w) + "░" * (w - int(self.T * w))
        v_bar = "▓" * int(self.V * w) + "░" * (w - int(self.V * w))
        
        # Efficiency gauge
        eta_pct = int(eta * 100)
        eta_color = C.BGREEN if eta > 0.7 else C.YELLOW if eta > 0.4 else C.RED
        
        w_box = 58
        border = "═" * (w_box - 2)
        
        lines = [
            f"{C.CYAN}╔{border}╗{C.RESET}",
            f"{C.CYAN}║{C.RESET} {phases_str}",
            f"{C.CYAN}║{C.RESET}",
            f"{C.CYAN}║{C.RESET}  {C.BOLD}H{C.RESET}={self.H:.2f}  {C.DIM}T{C.RESET}={self.T:.1f} {t_bar}  {C.DIM}V{C.RESET}={self.V:.1f} {v_bar}",
            f"{C.CYAN}║{C.RESET}  {C.BOLD}S{C.RESET}={S:+.3f}  {C.DIM}steps{C.RESET}={self.step_count}  {C.DIM}tools{C.RESET}={self.tool_calls}  {C.DIM}t{C.RESET}={elapsed:.1f}s",
            f"{C.CYAN}║{C.RESET}  {C.BOLD}η{C.RESET}={eta_color}{eta_pct}%{C.RESET}  {C.DIM}entropy{C.RESET}={self.entropy():.2f}  {C.DIM}tokens{C.RESET}={self.tokens_in}→{self.tokens_out}",
        ]
        if task_desc:
            lines.append(f"{C.CYAN}║{C.RESET}  {C.DIM}task{C.RESET}: {task_desc[:50]}")
        lines.append(f"{C.CYAN}╚{border}╝{C.RESET}")
        return "\n".join(lines)
    
    def render_trajectory(self):
        """ASCII plot of energy over time."""
        if len(self.history) < 2:
            return ""
        
        h = 8  # height
        w = min(40, len(self.history))
        
        # Sample history to fit width
        step = max(1, len(self.history) // w)
        samples = self.history[::step][:w]
        
        energies = [s[1] + s[2] for s in samples]  # H = T + V
        max_e = max(energies) if energies else 1.0
        
        grid = [[" " for _ in range(len(samples))] for _ in range(h)]
        
        for x, e in enumerate(energies):
            y = int((1 - e / max_e) * (h - 1))
            y = max(0, min(h - 1, y))
            grid[y][x] = "●"
            # Fill below
            for yy in range(y + 1, h):
                grid[yy][x] = "│"
        
        lines = [f"  {C.DIM}H(t) ↑{C.RESET}"]
        for row in grid:
            lines.append(f"  {C.DIM}│{C.RESET}{''.join(row)}")
        lines.append(f"  {C.DIM}└{'─' * len(samples)}→ t{C.RESET}")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════════
# Variational Plan Selection
# ════════════════════════════════════════════════════════════════════════════════

class VariationalPlanner:
    """Select execution plan by minimizing predicted action.
    
    Given multiple candidate plans, estimate S = ∫E·dt for each
    and choose the path of least action.
    """
    
    @staticmethod
    def score_plan(plan_text):
        """Heuristic energy scoring for a plan."""
        # Count complexity indicators
        steps = len(re.findall(r'(?:^|\n)\s*\d+[\.\)]', plan_text))
        file_ops = len(re.findall(r'(?:create|write|edit|modify|delete)\s+\w+', plan_text, re.I))
        commands = len(re.findall(r'(?:run|execute|install|pip|npm)\s', plan_text, re.I))
        
        # More steps = more action required
        T = min(1.0, 0.1 + steps * 0.15)  # kinetic energy
        V = max(0.1, 0.8 - file_ops * 0.1 - commands * 0.05)  # potential (uncertainty)
        
        estimated_time = max(1.0, steps * 5.0 + file_ops * 3.0 + commands * 8.0)
        S = (T - V) * estimated_time  # action
        
        return {
            "steps": steps,
            "file_ops": file_ops,
            "commands": commands,
            "T": T,
            "V": V,
            "S": S,
            "estimated_time": estimated_time,
        }
    
    @staticmethod
    def compare_plans(plans):
        """Score multiple plans and rank by action (lower = better)."""
        scored = []
        for i, plan in enumerate(plans):
            score = VariationalPlanner.score_plan(plan)
            score["index"] = i
            score["plan"] = plan
            scored.append(score)
        scored.sort(key=lambda x: x["S"])
        return scored


# ════════════════════════════════════════════════════════════════════════════════
# Git Checkpoint System
# ════════════════════════════════════════════════════════════════════════════════

class GitCheckpoint:
    """Auto-checkpoint changes via git for safety."""
    
    @staticmethod
    def is_git_repo():
        try:
            r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                             capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def checkpoint(message="swml-agent auto-checkpoint"):
        if not GitCheckpoint.is_git_repo():
            return None
        try:
            subprocess.run(["git", "add", "-A"], capture_output=True, timeout=10)
            r = subprocess.run(["git", "commit", "-m", message, "--allow-empty"],
                             capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                # Get short hash
                h = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
                return h.stdout.strip()
        except Exception:
            pass
        return None
    
    @staticmethod
    def rollback():
        if not GitCheckpoint.is_git_repo():
            return False
        try:
            r = subprocess.run(["git", "reset", "--hard", "HEAD~1"],
                             capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False


# ════════════════════════════════════════════════════════════════════════════════
# Ollama Client
# ════════════════════════════════════════════════════════════════════════════════

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def ollama_chat(model, messages, tools=None, stream=True):
    body = {"model": model, "messages": messages, "stream": stream}
    if tools:
        body["tools"] = tools
    
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=300)
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Cannot connect to Ollama at {OLLAMA_URL}.\n"
            f"Start with: ollama serve\n{e}"
        )
    
    if stream:
        return _stream_response(resp)
    else:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def _stream_response(resp):
    full_content = ""
    tool_calls = []
    eval_count = 0
    prompt_eval_count = 0
    
    for line in resp:
        if not line.strip():
            continue
        try:
            chunk = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        
        msg = chunk.get("message", {})
        content = msg.get("content", "")
        if content:
            sys.stdout.write(content)
            sys.stdout.flush()
            full_content += content
        
        if msg.get("tool_calls"):
            tool_calls.extend(msg["tool_calls"])
        
        if chunk.get("eval_count"):
            eval_count = chunk["eval_count"]
        if chunk.get("prompt_eval_count"):
            prompt_eval_count = chunk["prompt_eval_count"]
        
        if chunk.get("done"):
            break
    
    if full_content:
        print()
    
    return {
        "content": full_content,
        "tool_calls": tool_calls,
        "tokens_in": prompt_eval_count,
        "tokens_out": eval_count,
    }


def ollama_list():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def ollama_model_info(model):
    """Get model details."""
    try:
        body = json.dumps({"name": model}).encode("utf-8")
        req = urllib.request.Request(f"{OLLAMA_URL}/api/show", data=body,
                                    headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


# ════════════════════════════════════════════════════════════════════════════════
# Tools — 10 built-in
# ════════════════════════════════════════════════════════════════════════════════

class ToolRegistry:
    def __init__(self):
        self.tools = {}
    
    def register(self, name, description, parameters, func):
        self.tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "func": func,
        }
    
    def get_ollama_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in self.tools.values()
        ]
    
    def execute(self, name, args):
        if name not in self.tools:
            return f"Error: Unknown tool '{name}'"
        try:
            return self.tools[name]["func"](**args)
        except Exception as e:
            return f"Error executing {name}: {e}\n{traceback.format_exc()}"


def _tool_read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        if p.stat().st_size > 1_000_000:
            return f"Error: File too large (>1MB). Use offset/limit."
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if offset or limit:
            start = max(0, offset - 1) if offset > 0 else 0
            end = start + limit if limit > 0 else len(lines)
            lines = lines[start:end]
            header = f"[Showing lines {start+1}-{min(end, len(lines)+start)} of {len(text.splitlines())}]\n"
            return header + "\n".join(lines)
        return text
    except Exception as e:
        return f"Error reading {path}: {e}"


def _tool_write_file(path: str, content: str) -> str:
    try:
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        lines = content.count("\n") + 1
        return f"✓ Written {len(content)} bytes ({lines} lines) to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


def _tool_edit_file(path: str, old_text: str, new_text: str) -> str:
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        content = p.read_text(encoding="utf-8")
        if old_text not in content:
            # Fuzzy match suggestion
            lines = content.splitlines()
            close = difflib.get_close_matches(old_text.splitlines()[0] if old_text else "",
                                               lines, n=3, cutoff=0.5)
            hint = f" Similar lines: {close}" if close else ""
            return f"Error: old_text not found in {path}.{hint}"
        count = content.count(old_text)
        if count > 1:
            return f"Warning: old_text appears {count} times. Be more specific."
        new_content = content.replace(old_text, new_text, 1)
        p.write_text(new_content, encoding="utf-8")
        
        # Show diff
        diff = list(difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(),
            lineterm="", n=2))
        diff_str = "\n".join(diff[:20])
        return f"✓ Edited {path}\n{diff_str}"
    except Exception as e:
        return f"Error editing {path}: {e}"


def _tool_run_command(command: str, timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=min(timeout, 120), cwd=os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output[:15000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out ({timeout}s limit)"
    except Exception as e:
        return f"Error: {e}"


def _tool_list_files(directory: str = ".", pattern: str = "**/*", max_depth: int = 3) -> str:
    try:
        p = Path(directory).resolve()
        if not p.is_dir():
            return f"Error: Not a directory: {directory}"
        
        files = []
        for f in sorted(p.glob(pattern)):
            # Depth check
            try:
                rel = f.relative_to(p)
                if len(rel.parts) > max_depth:
                    continue
            except ValueError:
                continue
            # Skip hidden
            if any(part.startswith(".") for part in rel.parts):
                continue
            
            if f.is_dir():
                files.append(f"  📁 {rel}/")
            else:
                size = f.stat().st_size
                files.append(f"  📄 {rel} ({size:,}b)")
            
            if len(files) >= 100:
                files.append("  ... (truncated at 100)")
                break
        
        return "\n".join(files) if files else "(empty)"
    except Exception as e:
        return f"Error: {e}"


def _tool_search_files(query: str, directory: str = ".", extensions: str = "") -> str:
    try:
        p = Path(directory).resolve()
        ext_list = [e.strip().lstrip(".") for e in extensions.split(",") if e.strip()] if extensions else None
        results = []
        for f in p.rglob("*"):
            if not f.is_file() or f.stat().st_size > 256_000:
                continue
            if ext_list and f.suffix.lstrip(".") not in ext_list:
                continue
            if any(part.startswith(".") for part in f.relative_to(p).parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if query.lower() in line.lower():
                        rel = f.relative_to(p)
                        results.append(f"  {rel}:{i}: {line.strip()[:120]}")
                        if len(results) >= 50:
                            return "\n".join(results) + "\n  ... (50 results, truncated)"
            except Exception:
                continue
        return "\n".join(results) if results else f"No matches for '{query}'"
    except Exception as e:
        return f"Error: {e}"


def _tool_patch_file(path: str, patches: str) -> str:
    """Apply multiple edits to a file using a simple patch format.
    Format: <<<OLD\nold text\n===\nnew text\n>>>
    """
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        content = p.read_text(encoding="utf-8")
        
        # Parse patches
        parts = re.findall(r'<<<OLD\n(.*?)\n===\n(.*?)\n>>>', patches, re.DOTALL)
        if not parts:
            return "Error: No valid patches found. Format: <<<OLD\\nold\\n===\\nnew\\n>>>"
        
        applied = 0
        for old, new in parts:
            if old in content:
                content = content.replace(old, new, 1)
                applied += 1
        
        if applied > 0:
            p.write_text(content, encoding="utf-8")
            return f"✓ Applied {applied}/{len(parts)} patches to {path}"
        return f"Error: None of {len(parts)} patches matched"
    except Exception as e:
        return f"Error: {e}"


def _tool_think(thought: str) -> str:
    """Internal reasoning tool — think through a problem without side effects."""
    return f"[Thought recorded: {len(thought)} chars]"


def _tool_checkpoint(message: str = "") -> str:
    """Create a git checkpoint of current changes."""
    msg = message or f"swml-agent checkpoint @ {datetime.now().strftime('%H:%M:%S')}"
    sha = GitCheckpoint.checkpoint(msg)
    if sha:
        return f"✓ Checkpoint created: {sha} — \"{msg}\""
    return "No git repo found or nothing to commit."


def _tool_undo() -> str:
    """Undo last checkpoint (git reset --hard HEAD~1)."""
    if GitCheckpoint.rollback():
        return "✓ Rolled back to previous checkpoint."
    return "Error: Could not rollback. No git repo or no previous commit."


def build_tool_registry():
    reg = ToolRegistry()
    
    reg.register("read_file", "Read a file. Use offset/limit for large files.",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "offset": {"type": "integer", "description": "Start line (1-indexed)"},
            "limit": {"type": "integer", "description": "Max lines to read"},
        }, "required": ["path"]},
        _tool_read_file)
    
    reg.register("write_file", "Write content to a file (creates dirs if needed)",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
        }, "required": ["path", "content"]},
        _tool_write_file)
    
    reg.register("edit_file", "Replace exact text in a file. Shows diff.",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_text": {"type": "string", "description": "Exact text to find"},
            "new_text": {"type": "string", "description": "Replacement text"},
        }, "required": ["path", "old_text", "new_text"]},
        _tool_edit_file)
    
    reg.register("patch_file", "Apply multiple edits using <<<OLD/===/>>> format",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path"},
            "patches": {"type": "string", "description": "Patches in <<<OLD\\nold\\n===\\nnew\\n>>> format"},
        }, "required": ["path", "patches"]},
        _tool_patch_file)
    
    reg.register("run_command", "Execute a shell command",
        {"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell command"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
        }, "required": ["command"]},
        _tool_run_command)
    
    reg.register("list_files", "List files in directory (recursive)",
        {"type": "object", "properties": {
            "directory": {"type": "string", "description": "Directory path"},
            "pattern": {"type": "string", "description": "Glob pattern (default: **/*)"},
            "max_depth": {"type": "integer", "description": "Max depth (default: 3)"},
        }, "required": []},
        _tool_list_files)
    
    reg.register("search_files", "Search for text across files (grep-like)",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to search"},
            "directory": {"type": "string", "description": "Directory to search"},
            "extensions": {"type": "string", "description": "File extensions (comma-sep)"},
        }, "required": ["query"]},
        _tool_search_files)
    
    reg.register("think", "Think through a problem. No side effects.",
        {"type": "object", "properties": {
            "thought": {"type": "string", "description": "Your reasoning"},
        }, "required": ["thought"]},
        _tool_think)
    
    reg.register("checkpoint", "Save current state as a git checkpoint",
        {"type": "object", "properties": {
            "message": {"type": "string", "description": "Checkpoint message"},
        }, "required": []},
        _tool_checkpoint)
    
    reg.register("undo", "Undo last checkpoint (rollback)",
        {"type": "object", "properties": {}, "required": []},
        _tool_undo)
    
    return reg


# ════════════════════════════════════════════════════════════════════════════════
# System Prompt
# ════════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are SWML-Agent, a coding agent built on SWML (Shunsuke's World Model Logic).

You operate in Ω-space with four phases, each with measurable energy:
- OBSERVE (H=1.2): Understand the task. Read files, explore the codebase.
- PLAN (H=1.0): Structure the solution. Identify the minimum-energy path.
- EXECUTE (H=1.1): Write code, create files, run commands.
- VERIFY (H=0.3): Test the result. Confirm correctness. Ground state.

Your goal: minimize total action S = ∫(T-V)dt — do the right thing in the fewest steps.

## Principles (from Hamiltonian mechanics)
1. **Least action**: Don't over-engineer. The simplest working solution wins.
2. **Energy conservation**: Time spent observing reduces time spent debugging.
3. **Phase transitions**: Move forward. Don't oscillate between OBSERVE and EXECUTE.
4. **Ground state**: Always end in VERIFY. Untested code has high potential energy.

## Rules
1. Read before writing. Observe before planning.
2. Make minimal, precise changes. Small edits > full rewrites.
3. Always verify — run the code or tests after changes.
4. Use `think` tool for complex reasoning before acting.
5. Use `checkpoint` before risky changes. Use `undo` if things break.
6. Be direct. No filler.

## Tools (10)
read_file, write_file, edit_file, patch_file, run_command, list_files, search_files, think, checkpoint, undo"""


# ════════════════════════════════════════════════════════════════════════════════
# Agent
# ════════════════════════════════════════════════════════════════════════════════

class SWMLAgent:
    def __init__(self, model, auto_approve=False, verbose=False):
        self.model = model
        self.auto_approve = auto_approve
        self.verbose = verbose
        self.omega = OmegaState()
        self.tools = build_tool_registry()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.max_turns = 40
        self.task_desc = ""
    
    def _detect_phase(self, content, has_tools):
        c = (content or "").lower()
        
        if has_tools:
            # Check tool names to determine phase
            return "EXECUTE"
        
        if any(w in c for w in ["let me read", "looking at", "examining", "let me check",
                                 "i see the", "the file contains", "understand"]):
            return "OBSERVE"
        elif any(w in c for w in ["plan", "approach", "strategy", "i'll ", "steps:",
                                   "here's what", "let me think"]):
            return "PLAN"
        elif any(w in c for w in ["test", "verify", "check", "confirm", "works",
                                   "looks good", "success", "passed", "all done"]):
            return "VERIFY"
        elif any(w in c for w in ["writ", "creat", "edit", "implement", "add", "fix"]):
            return "EXECUTE"
        return None
    
    def _approve_tool(self, name, args):
        if self.auto_approve:
            return True
        if name == "think":
            return True  # always allow thinking
        
        print(f"\n{C.YELLOW}⚡ {name}{C.RESET}")
        for k, v in args.items():
            dv = str(v)
            if len(dv) > 300:
                dv = dv[:300] + f"... ({len(dv)} chars)"
            print(f"   {C.DIM}{k}{C.RESET}: {dv}")
        
        try:
            ans = input(f"  {C.YELLOW}Allow? [Y/n] {C.RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans in ("", "y", "yes")
    
    def run_turn(self, user_input=None):
        if user_input:
            self.messages.append({"role": "user", "content": user_input})
        
        # Show Ω state
        print(f"\n{self.omega.render(self.task_desc)}")
        
        # Call LLM
        print(f"\n{C.CYAN}{'─' * min(56, term_width())}{C.RESET}")
        try:
            result = ollama_chat(
                self.model, self.messages,
                tools=self.tools.get_ollama_tools(),
                stream=True,
            )
        except ConnectionError as e:
            print(f"\n{C.RED}{e}{C.RESET}")
            return False
        except Exception as e:
            print(f"\n{C.RED}Error: {e}{C.RESET}")
            traceback.print_exc()
            return False
        
        content = result.get("content", "")
        tool_calls = result.get("tool_calls", [])
        self.omega.tokens_in += result.get("tokens_in", 0)
        self.omega.tokens_out += result.get("tokens_out", 0)
        
        # Phase detection
        detected = self._detect_phase(content, bool(tool_calls))
        if detected and detected != self.omega.phase:
            old, new = self.omega.transition(detected)
            if old:
                sym = self.omega.PHASE_SYMBOLS.get(new, "")
                print(f"\n  {C.MAGENTA}⟨Ω: {old} → {sym} {new}⟩{C.RESET}")
        
        # Record message
        assistant_msg = {"role": "assistant"}
        if content:
            assistant_msg["content"] = content
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        self.messages.append(assistant_msg)
        
        # Execute tools
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                
                if not self._approve_tool(name, args):
                    self.messages.append({"role": "tool", "content": "Denied by user."})
                    continue
                
                self.omega.tool_calls += 1
                t0 = time.time()
                result_text = self.tools.execute(name, args)
                dt = time.time() - t0
                
                print(f"  {C.GREEN}▶ {name}{C.RESET} {C.DIM}({dt:.1f}s, {len(result_text)} chars){C.RESET}")
                
                # Show result (truncated)
                preview = result_text[:600]
                if len(result_text) > 600:
                    preview += f"\n  {C.DIM}... ({len(result_text)} chars total){C.RESET}"
                print(f"{C.DIM}{preview}{C.RESET}")
                
                self.messages.append({"role": "tool", "content": result_text[:10000]})
            
            return True  # continue after tool use
        
        return False
    
    def run_task(self, task):
        self.omega = OmegaState()
        self.task_desc = task[:60]
        
        turn = 0
        continues = self.run_turn(user_input=task)
        while continues and turn < self.max_turns:
            turn += 1
            continues = self.run_turn()
        
        # Final state
        self.omega.transition("VERIFY")
        print(f"\n{self.omega.render(self.task_desc)}")
        
        # Trajectory
        traj = self.omega.render_trajectory()
        if traj:
            print(f"\n{C.DIM}  Energy trajectory:{C.RESET}")
            print(traj)
        
        S = self.omega.action_integral()
        eta = self.omega.efficiency()
        print(f"\n{C.GREEN}  ✓ Complete. S={S:+.3f}  η={eta*100:.0f}%  tools={self.omega.tool_calls}  tokens={self.omega.tokens_in}→{self.omega.tokens_out}{C.RESET}")


# ════════════════════════════════════════════════════════════════════════════════
# Banner & Main
# ════════════════════════════════════════════════════════════════════════════════

BANNER = f"""{C.CYAN}
  ███████╗██╗    ██╗███╗   ███╗██╗            
  ██╔════╝██║    ██║████╗ ████║██║            
  ███████╗██║ █╗ ██║██╔████╔██║██║            
  ╚════██║██║███╗██║██║╚██╔╝██║██║            
  ███████║╚███╔███╔╝██║ ╚═╝ ██║███████╗      
  ╚══════╝ ╚══╝╚══╝ ╚═╝     ╚═╝╚══════╝      
       {C.BOLD}A G E N T{C.RESET}{C.CYAN}   v{__version__}
  ─────────────────────────────────────
  Physics-based coding agent
  S = ∫(T−V)dt → min     {C.DIM}(variational principle){C.RESET}{C.CYAN}
  ─────────────────────────────────────{C.RESET}
"""

def detect_model():
    models = ollama_list()
    if not models:
        return None
    preferred = ["qwen3-coder", "qwen3:30b", "qwen3:8b"]
    for pref in preferred:
        for m in models:
            if pref in m:
                return m
    return models[0]


def main():
    parser = argparse.ArgumentParser(description="SWML-Agent — Physics-based coding agent")
    parser.add_argument("-p", "--prompt", help="One-shot prompt")
    parser.add_argument("--model", help="Ollama model name")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve tools")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    model = args.model or detect_model()
    if not model:
        print(f"{C.RED}Error: No Ollama models found.")
        print(f"Install one with: ollama pull qwen3-coder{C.RESET}")
        sys.exit(1)
    
    # Model info
    info = ollama_model_info(model)
    param_size = info.get("details", {}).get("parameter_size", "?")
    quant = info.get("details", {}).get("quantization_level", "?")
    
    print(BANNER)
    print(f"  {C.DIM}model :{C.RESET} {model} ({param_size}, {quant})")
    print(f"  {C.DIM}cwd   :{C.RESET} {os.getcwd()}")
    print(f"  {C.DIM}tools :{C.RESET} {10} built-in")
    print(f"  {C.DIM}git   :{C.RESET} {'✓' if GitCheckpoint.is_git_repo() else '✗'}")
    print()
    
    agent = SWMLAgent(model=model, auto_approve=args.yes, verbose=args.verbose)
    
    if args.prompt:
        agent.run_task(args.prompt)
        return
    
    print(f"  {C.DIM}Type your request. /help for commands. Ctrl+C to exit.{C.RESET}\n")
    
    while True:
        try:
            user_input = input(f"{C.BGREEN}Ω ❯ {C.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.DIM}Goodbye.{C.RESET}")
            break
        
        if not user_input:
            continue
        
        cmd = user_input.lower()
        
        if cmd in ("/quit", "/exit", "/q"):
            print(f"{C.DIM}Goodbye.{C.RESET}")
            break
        
        if cmd == "/status":
            print(agent.omega.render())
            traj = agent.omega.render_trajectory()
            if traj:
                print(traj)
            continue
        
        if cmd == "/models":
            models = ollama_list()
            for m in models:
                marker = " ◀" if m == model else ""
                print(f"  {m}{C.GREEN}{marker}{C.RESET}")
            continue
        
        if cmd.startswith("/model "):
            new_model = user_input[7:].strip()
            agent.model = new_model
            model = new_model
            info = ollama_model_info(new_model)
            ps = info.get("details", {}).get("parameter_size", "?")
            print(f"  Switched to {C.BOLD}{new_model}{C.RESET} ({ps})")
            continue
        
        if cmd == "/undo":
            print(_tool_undo())
            continue
        
        if cmd == "/help":
            print(f"""
  {C.BOLD}Commands:{C.RESET}
    /status   — Show Ω-state & energy trajectory
    /models   — List available models
    /model X  — Switch model
    /undo     — Rollback last git checkpoint
    /help     — This help
    /quit     — Exit

  {C.BOLD}What is Ω-space?{C.RESET}
    Tasks have energy. The agent minimizes action S = ∫(T−V)dt.
    H = T + V (Hamiltonian = total energy)
    T = kinetic (complexity of action)
    V = potential (uncertainty remaining)
    η = efficiency (lower action = higher η)
    
    Like a ball rolling downhill to the lowest energy state.
""")
            continue
        
        agent.run_task(user_input)
        print()


if __name__ == "__main__":
    main()
