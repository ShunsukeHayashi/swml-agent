
#!/usr/bin/env python3
"""
SWML-Agent: physics-inspired coding agent for local Ollama models.
Single file, stdlib-only.
"""

import argparse
import base64
import copy
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

__version__ = "0.5.0"
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
SESSION_ROOT = Path.home() / ".swml-agent" / "sessions"
DEFAULT_CONTEXT_LIMIT = 32768


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    @classmethod
    def disable(cls):
        for k in dir(cls):
            if k.isupper() and isinstance(getattr(cls, k), str):
                setattr(cls, k, "")


if os.name == "nt":
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel.GetConsoleMode(handle, ctypes.byref(mode))
        kernel.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

if not sys.stdout.isatty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
    C.disable()


def term_width():
    try:
        return shutil.get_terminal_size((100, 24)).columns
    except Exception:
        return 100


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def approx_tokens(text):
    return max(1, len(text) // 4) if text else 0


class Spinner:
    def __init__(self, label="LLM inference"):
        self.label = label
        self.frames = ["|", "/", "-", "\\"]
        self.i = 0
        self.stop_event = threading.Event()
        self.thread = None
        self.toks = 0
        self.t0 = 0

    def set_tokens(self, n):
        self.toks = n or 0

    def start(self):
        self.t0 = time.time()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=0.3)
        sys.stdout.write("\r" + " " * (term_width() - 1) + "\r")
        sys.stdout.flush()

    def _run(self):
        while not self.stop_event.is_set():
            dt = max(0.001, time.time() - self.t0)
            msg = f"{C.DIM}{self.frames[self.i]} {self.label} out={self.toks} tok {self.toks/dt:.1f} tok/s{C.RESET}"
            sys.stdout.write("\r" + msg[: term_width() - 1].ljust(term_width() - 1))
            sys.stdout.flush()
            self.i = (self.i + 1) % len(self.frames)
            time.sleep(0.08)


class OmegaState:
    PHASES = ["OBSERVE", "PLAN", "EXECUTE", "VERIFY"]
    PHASE_ENERGY = {
        "OBSERVE": (0.3, 0.9),
        "PLAN": (0.5, 0.5),
        "EXECUTE": (0.9, 0.2),
        "VERIFY": (0.2, 0.1),
    }

    def __init__(self):
        self.phase = "OBSERVE"
        self.step_count = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.start_time = time.time()
        self.history = []
        self._record()

    def _record(self):
        t, v = self.PHASE_ENERGY[self.phase]
        self.history.append({"phase": self.phase, "T": t, "V": v, "ts": time.time()})

    def transition(self, p):
        if p in self.PHASES and p != self.phase:
            old = self.phase
            self.phase = p
            self.step_count += 1
            self._record()
            return old, p
        return None, None

    @property
    def T(self):
        return self.PHASE_ENERGY[self.phase][0]

    @property
    def V(self):
        return self.PHASE_ENERGY[self.phase][1]

    def action_integral(self):
        if len(self.history) < 2:
            return 0.0
        s = 0.0
        for i in range(1, len(self.history)):
            a = self.history[i - 1]
            b = self.history[i]
            s += (a["T"] - a["V"]) * (b["ts"] - a["ts"])
        return s

    def efficiency(self):
        if len(self.history) < 2:
            return 1.0
        dt = self.history[-1]["ts"] - self.history[0]["ts"]
        worst = 1.2 * max(dt, 1e-9)
        return max(0.0, min(1.0, 1.0 - abs(self.action_integral()) / worst))

    def render(self):
        # Phase icons and Japanese descriptions
        ICONS = {"OBSERVE": "🔭", "PLAN": "📐", "EXECUTE": "⚡", "VERIFY": "✅"}
        LABELS_JP = {
            "OBSERVE": "観察中 — コードを読んで状況を把握しています",
            "PLAN":    "計画中 — 最適な実装方法を考えています",
            "EXECUTE": "実行中 — コードを書いて変更を加えています",
            "VERIFY":  "検証中 — 動作確認・テストをしています",
        }
        
        # Phase progress bar
        states = []
        for p in self.PHASES:
            icon = ICONS[p]
            if p == self.phase:
                states.append(f"{C.GREEN}{C.BOLD}{icon}[{p}]{C.RESET}")
            elif self.PHASES.index(p) < self.PHASES.index(self.phase):
                states.append(f"{C.GREEN}{icon} {p}{C.RESET}")
            else:
                states.append(f"{C.DIM}{icon} {p}{C.RESET}")
        
        phase_line = " → ".join(states)
        
        # Energy bar (visual)
        H = self.T + self.V
        bar_len = 20
        filled = int((1.0 - H / 1.2) * bar_len)  # Lower H = more filled (closer to ground)
        bar = "█" * max(0, filled) + "░" * (bar_len - max(0, filled))
        
        # Elapsed time
        elapsed = time.time() - self.start_time
        
        # Efficiency with color
        eta = self.efficiency()
        eta_pct = int(eta * 100)
        if eta_pct >= 80:
            eta_color = C.GREEN
            eta_label = "効率的"
        elif eta_pct >= 50:
            eta_color = C.YELLOW
            eta_label = "普通"
        else:
            eta_color = C.RED
            eta_label = "改善の余地あり"
        
        w = min(60, term_width() - 2)
        border = "─" * w
        
        lines = [
            f"{C.CYAN}{border}{C.RESET}",
            f"  {phase_line}",
            f"  {C.BOLD}{ICONS[self.phase]} {LABELS_JP[self.phase]}{C.RESET}",
            f"",
            f"  完了度  {bar} {C.DIM}(H={H:.2f}, 低いほど完了に近い){C.RESET}",
            f"  効率    {eta_color}{eta_pct}% {eta_label}{C.RESET}  {C.DIM}│{C.RESET}  ステップ {self.step_count}  {C.DIM}│{C.RESET}  ツール {self.tool_calls}回",
            f"  トークン {self.tokens_in}→{self.tokens_out}  {C.DIM}│{C.RESET}  経過 {elapsed:.1f}秒",
            f"{C.CYAN}{border}{C.RESET}",
        ]
        return "\n".join(lines)

    def to_dict(self):
        return {
            "phase": self.phase,
            "step_count": self.step_count,
            "tool_calls": self.tool_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "start_time": self.start_time,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data):
        o = cls()
        o.phase = data.get("phase", "OBSERVE")
        o.step_count = data.get("step_count", 0)
        o.tool_calls = data.get("tool_calls", 0)
        o.tokens_in = data.get("tokens_in", 0)
        o.tokens_out = data.get("tokens_out", 0)
        o.start_time = data.get("start_time", time.time())
        o.history = data.get("history", []) or []
        if not o.history:
            o._record()
        return o


class SessionStore:
    def __init__(self, root=SESSION_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sid):
        return self.root / f"{sid}.json"

    def save(self, sid, payload):
        data = copy.deepcopy(payload)
        data["updated_at"] = now_iso()
        path = self._path(sid)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, sid):
        if sid == "latest":
            files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                return None, None
            path = files[0]
        else:
            path = self._path(sid)
            if not path.exists():
                return None, None
        return path.stem, json.loads(path.read_text(encoding="utf-8"))

    def list_sessions(self, limit=20):
        out = []
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        for p in files:
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                obj = {}
            out.append({
                "id": p.stem,
                "updated_at": obj.get("updated_at", "?"),
                "model": obj.get("model", "?"),
                "turns": len(obj.get("messages", [])),
                "title": obj.get("title", ""),
            })
        return out

class ContextManager:
    def __init__(self, limit=DEFAULT_CONTEXT_LIMIT, summarize_at=0.82, keep_recent=14):
        self.limit = max(2048, int(limit))
        self.summarize_at = summarize_at
        self.keep_recent = keep_recent
        self.summary_count = 0

    def estimate(self, messages):
        n = 0
        for m in messages:
            n += approx_tokens(m.get("content", ""))
            if m.get("tool_calls"):
                n += approx_tokens(json.dumps(m["tool_calls"], ensure_ascii=False))
        return n

    def maybe_summarize(self, messages):
        if self.estimate(messages) < int(self.limit * self.summarize_at):
            return messages, None
        if len(messages) <= self.keep_recent + 2:
            return messages, None

        system = [m for m in messages if m.get("role") == "system"][:1]
        rest = [m for m in messages if m.get("role") != "system"]
        old = rest[:-self.keep_recent]
        recent = rest[-self.keep_recent:]

        lines = []
        for m in old:
            role = m.get("role", "?")
            txt = (m.get("content") or "").replace("\n", " ").strip()
            if len(txt) > 160:
                txt = txt[:160] + "..."
            if txt:
                lines.append(f"- {role}: {txt}")
            if m.get("tool_calls"):
                lines.append(f"- assistant(tool_calls): {len(m['tool_calls'])} calls")

        summary = {"role": "system", "content": "Context summary (auto-compressed):\n" + "\n".join(lines[:120])}
        self.summary_count += 1
        return system + [summary] + recent, f"Context compressed ({len(old)} messages)."


class FileWatcher:
    def __init__(self, root, callback, interval=1.0):
        self.root = Path(root)
        self.callback = callback
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.snapshot = {}
        self.allowed = {
            ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".toml", ".yaml", ".yml",
            ".sh", ".ps1", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".css", ".html",
        }

    def start(self):
        self.snapshot = self._scan()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=0.5)

    def _ok(self, rel):
        if any(part.startswith(".") for part in rel.parts):
            return False
        if any(part in {"node_modules", "dist", "build", "__pycache__", ".git"} for part in rel.parts):
            return False
        return rel.suffix.lower() in self.allowed

    def _scan(self):
        snap = {}
        for p in self.root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                rel = p.relative_to(self.root)
                if not self._ok(rel):
                    continue
                st = p.stat()
                snap[str(p)] = (st.st_mtime_ns, st.st_size)
            except Exception:
                continue
        return snap

    def _run(self):
        while not self.stop_event.is_set():
            time.sleep(self.interval)
            new = self._scan()
            oldk, newk = set(self.snapshot), set(new)
            for path in sorted(newk - oldk):
                self.callback(path, "created")
            for path in sorted(oldk - newk):
                self.callback(path, "deleted")
            for path in sorted(newk & oldk):
                if new[path] != self.snapshot[path]:
                    self.callback(path, "modified")
            self.snapshot = new


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, description, parameters, fn):
        self.tools[name] = {"name": name, "description": description, "parameters": parameters, "fn": fn}

    def as_ollama(self):
        return [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
            for t in self.tools.values()
        ]

    def execute(self, name, args):
        if name not in self.tools:
            return f"Error: unknown tool '{name}'"
        try:
            return self.tools[name]["fn"](**args)
        except Exception as exc:
            return f"Error executing {name}: {exc}\n{traceback.format_exc()}"


class SWMLMetrics:
    def __init__(self):
        self.energy_history = []
        self.efficiency_history = []
        self.tool_usage = Counter()
        self.phase_counts = Counter()
        self.inference_speeds = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.context_summaries = 0
        self.sub_agents = 0

    def sample(self, omega):
        self.energy_history.append((time.time(), omega.phase, omega.T, omega.V, omega.T + omega.V))
        self.efficiency_history.append((time.time(), omega.efficiency()))
        self.phase_counts[omega.phase] += 1

    def to_dict(self):
        return {
            "energy_history": self.energy_history,
            "efficiency_history": self.efficiency_history,
            "tool_usage": dict(self.tool_usage),
            "phase_counts": dict(self.phase_counts),
            "inference_speeds": self.inference_speeds,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "context_summaries": self.context_summaries,
            "sub_agents": self.sub_agents,
        }

    @classmethod
    def from_dict(cls, data):
        m = cls()
        m.energy_history = data.get("energy_history", [])
        m.efficiency_history = data.get("efficiency_history", [])
        m.tool_usage = Counter(data.get("tool_usage", {}))
        m.phase_counts = Counter(data.get("phase_counts", {}))
        m.inference_speeds = data.get("inference_speeds", [])
        m.tokens_in = data.get("tokens_in", 0)
        m.tokens_out = data.get("tokens_out", 0)
        m.tests_run = data.get("tests_run", 0)
        m.tests_passed = data.get("tests_passed", 0)
        m.tests_failed = data.get("tests_failed", 0)
        m.context_summaries = data.get("context_summaries", 0)
        m.sub_agents = data.get("sub_agents", 0)
        return m


def ollama_http(path, body=None, timeout=120):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def ollama_list():
    try:
        with ollama_http("/api/tags", timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return [m["name"] for m in payload.get("models", [])]
    except Exception:
        return []


def ollama_model_info(model):
    try:
        with ollama_http("/api/show", body={"name": model}, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def supports_vision(model_name, info):
    m = model_name.lower()
    if any(k in m for k in ["llava", "vision", "vl", "moondream", "bakllava"]):
        return True
    t = json.dumps(info).lower()
    return any(k in t for k in ["vision", "image", "multimodal"])


def extract_context_limit(info):
    text = json.dumps(info)
    m = re.search(r'"context_length"\s*:\s*(\d+)', text) or re.search(r'"num_ctx"\s*:\s*(\d+)', text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return DEFAULT_CONTEXT_LIMIT


def ollama_chat(model, messages, tools=None, stream=True, on_chunk=None):
    body = {"model": model, "messages": messages, "stream": bool(stream)}
    if tools:
        body["tools"] = tools

    try:
        resp = ollama_http("/api/chat", body=body, timeout=300)
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {OLLAMA_URL}: {exc}")

    if not stream:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        msg = data.get("message", {})
        return {
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls", []) or [],
            "tokens_in": data.get("prompt_eval_count", 0),
            "tokens_out": data.get("eval_count", 0),
        }

    full, calls = [], []
    tin, tout = 0, 0
    for line in resp:
        if not line.strip():
            continue
        try:
            ch = json.loads(line.decode("utf-8"))
        except Exception:
            continue
        msg = ch.get("message", {})
        txt = msg.get("content", "")
        if txt:
            full.append(txt)
            sys.stdout.write(txt)
            sys.stdout.flush()
        c = msg.get("tool_calls") or []
        if c:
            calls.extend(c)
        if ch.get("prompt_eval_count") is not None:
            tin = ch.get("prompt_eval_count") or tin
        if ch.get("eval_count") is not None:
            tout = ch.get("eval_count") or tout
        if on_chunk:
            on_chunk(ch)
        if ch.get("done"):
            break
    if full:
        print()
    return {"content": "".join(full), "tool_calls": calls, "tokens_in": tin, "tokens_out": tout}


def system_prompt(sidecar=False, vision=False):
    extra = ""
    if sidecar:
        extra += "\n- Sidecar model available for lightweight checks."
    if vision:
        extra += "\n- Vision available; use view_image for diagrams/screenshots."
    return (
        "You are SWML-Agent operating in Omega-space with phases OBSERVE, PLAN, EXECUTE, VERIFY.\n"
        "Always keep edits minimal and verify with tests.\n"
        "Use tools deterministically. If tests fail, fix and rerun.\n"
        "Tooling: read/write/edit/patch/run/list/search/think/checkpoint/undo/spawn_agent/view_image."
        + extra
    )

class SWMLTools:
    def __init__(self, agent):
        self.agent = agent

    def read_file(self, path, offset=0, limit=0):
        p = (Path(path) if Path(path).is_absolute() else Path.cwd() / path).resolve()
        if not p.exists():
            return f"Error: not found: {path}"
        if p.stat().st_size > 1_500_000:
            return "Error: file too large (>1.5MB)"
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if offset or limit:
            start = max(0, int(offset) - 1)
            end = start + int(limit) if limit else len(lines)
            chunk = lines[start:end]
            return f"[lines {start+1}-{start+len(chunk)} / {len(lines)}]\n" + "\n".join(chunk)
        return text

    def write_file(self, path, content):
        p = (Path(path) if Path(path).is_absolute() else Path.cwd() / path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        self.agent.modified_files.add(str(p))
        return f"Wrote {len(content)} bytes to {p}"

    def edit_file(self, path, old_text, new_text):
        p = (Path(path) if Path(path).is_absolute() else Path.cwd() / path).resolve()
        if not p.exists():
            return f"Error: not found: {path}"
        src = p.read_text(encoding="utf-8")
        if old_text not in src:
            return "Error: old_text not found"
        if src.count(old_text) > 1:
            return "Error: old_text appears multiple times"
        p.write_text(src.replace(old_text, new_text, 1), encoding="utf-8")
        self.agent.modified_files.add(str(p))
        return f"Edited {p}"

    def patch_file(self, path, patches):
        p = (Path(path) if Path(path).is_absolute() else Path.cwd() / path).resolve()
        if not p.exists():
            return f"Error: not found: {path}"
        src = p.read_text(encoding="utf-8")
        blocks = re.findall(r"<<<OLD\n(.*?)\n===\n(.*?)\n>>>", patches, flags=re.DOTALL)
        if not blocks:
            return "Error: invalid patch format"
        applied = 0
        for old, new in blocks:
            if old in src:
                src = src.replace(old, new, 1)
                applied += 1
        if not applied:
            return "Error: no patch blocks matched"
        p.write_text(src, encoding="utf-8")
        self.agent.modified_files.add(str(p))
        return f"Applied {applied}/{len(blocks)} patch blocks to {p}"

    def run_command(self, command, timeout=90):
        timeout = max(1, min(int(timeout), 300))
        try:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=os.getcwd())
            out = proc.stdout or ""
            err = proc.stderr or ""
            txt = out + (f"\n[stderr]\n{err}" if err else "") + f"\n[exit code: {proc.returncode}]"
            return txt[:20000]
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s"
        except Exception as exc:
            return f"Error running command: {exc}"

    def list_files(self, directory=".", pattern="**/*", max_depth=4):
        base = (Path(directory) if Path(directory).is_absolute() else Path.cwd() / directory).resolve()
        if not base.is_dir():
            return f"Error: not a directory: {directory}"
        max_depth = max(1, min(int(max_depth), 8))
        rows = []
        for p in sorted(base.glob(pattern)):
            try:
                rel = p.relative_to(base)
            except Exception:
                continue
            if len(rel.parts) > max_depth or any(part.startswith(".") for part in rel.parts):
                continue
            rows.append(("D" if p.is_dir() else "F") + f" {rel}" + ("" if p.is_dir() else f" ({p.stat().st_size}b)"))
            if len(rows) >= 200:
                rows.append("... truncated")
                break
        return "\n".join(rows) if rows else "(empty)"

    def search_files(self, query, directory=".", extensions=""):
        base = (Path(directory) if Path(directory).is_absolute() else Path.cwd() / directory).resolve()
        if not base.is_dir():
            return f"Error: not a directory: {directory}"
        ext = {"." + e.strip().lstrip(".") for e in extensions.split(",") if e.strip()} if extensions else set()
        needle, rows = query.lower(), []
        for p in base.rglob("*"):
            if not p.is_file() or p.stat().st_size > 300_000:
                continue
            rel = p.relative_to(base)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if ext and p.suffix not in ext:
                continue
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if needle in line.lower():
                        rows.append(f"{rel}:{i}: {line[:180]}")
                        if len(rows) >= 80:
                            return "\n".join(rows) + "\n... truncated"
            except Exception:
                pass
        return "\n".join(rows) if rows else f"No matches for '{query}'"

    def think(self, thought):
        return f"Thought captured ({len(thought)} chars)."

    def checkpoint(self, message=""):
        if not self.agent.is_git_repo:
            return "No git repo detected."
        msg = message or f"swml checkpoint {now_iso()}"
        try:
            subprocess.run(["git", "add", "-A"], capture_output=True, timeout=10)
            proc = subprocess.run(["git", "commit", "-m", msg, "--allow-empty"], capture_output=True, text=True, timeout=10)
            if proc.returncode != 0:
                return "Checkpoint skipped."
            rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
            return f"Checkpoint created: {rev.stdout.strip()}"
        except Exception as exc:
            return f"Checkpoint failed: {exc}"

    def undo(self):
        if not self.agent.is_git_repo:
            return "No git repo detected."
        try:
            proc = subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True, timeout=10)
            return "Rolled back one commit." if proc.returncode == 0 else proc.stderr
        except Exception as exc:
            return f"Undo failed: {exc}"

    def spawn_agent(self, task, max_turns=8):
        if self.agent.depth >= self.agent.max_subagent_depth:
            return "Error: max sub-agent depth reached"
        self.agent.metrics.sub_agents += 1
        child = SWMLAgent(
            model=self.agent.model,
            sidecar_model=self.agent.sidecar_model,
            auto_approve=True,
            verbose=False,
            session_store=self.agent.session_store,
            session_id=f"{self.agent.session_id}-child-{uuid.uuid4().hex[:6]}",
            depth=self.agent.depth + 1,
            max_subagent_depth=self.agent.max_subagent_depth,
            watch=False,
        )
        child.max_turns = max(1, min(int(max_turns), 20))
        summary = child.run_task(task, one_shot=True)
        child.close()
        return "Sub-agent complete:\n" + summary[:8000]

    def view_image(self, path, prompt="Describe this image for coding context"):
        if not self.agent.vision_enabled:
            return "Error: model does not appear to support vision"
        p = (Path(path) if Path(path).is_absolute() else Path.cwd() / path).resolve()
        if not p.exists() or not p.is_file():
            return f"Error: image not found: {path}"
        if p.stat().st_size > 4_000_000:
            return "Error: image too large (>4MB)"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        self.agent.inject_multimodal_message(prompt, b64)
        return f"Attached image {p.name} for next model turn"


class SWMLAgent:
    def __init__(self, model, sidecar_model=None, auto_approve=False, verbose=False, session_store=None, session_id=None, depth=0, max_subagent_depth=2, watch=True):
        self.model = model
        self.sidecar_model = sidecar_model
        self.auto_approve = auto_approve
        self.verbose = verbose
        self.depth = depth
        self.max_subagent_depth = max_subagent_depth
        self.session_store = session_store or SessionStore()
        self.session_id = session_id or datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

        self.omega = OmegaState()
        self.metrics = SWMLMetrics()
        self.max_turns = 48
        self.task_desc = ""

        self.model_info = ollama_model_info(self.model)
        self.vision_enabled = supports_vision(self.model, self.model_info)
        self.context = ContextManager(limit=extract_context_limit(self.model_info))
        self.messages = [{"role": "system", "content": system_prompt(bool(sidecar_model), self.vision_enabled)}]

        self.pending_multimodal = deque()
        self.pending_watcher = deque(maxlen=200)
        self.modified_files = set()
        self.pending_repair_note = None

        self.tools = ToolRegistry()
        self._register_tools()

        self.watcher = None
        if watch and depth == 0:
            self.watcher = FileWatcher(Path.cwd(), self._on_watch)
            self.watcher.start()

        self.is_git_repo = self._detect_git_repo()

    def close(self):
        if self.watcher:
            self.watcher.stop()

    def _detect_git_repo(self):
        try:
            proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, timeout=4)
            return proc.returncode == 0
        except Exception:
            return False

    def _register_tools(self):
        t = SWMLTools(self)
        specs = [
            ("read_file", "Read file contents", {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["path"]}, t.read_file),
            ("write_file", "Write file contents", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}, t.write_file),
            ("edit_file", "Exact text replacement in a file", {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}, t.edit_file),
            ("patch_file", "Apply patch blocks <<<OLD/===/>>>", {"type": "object", "properties": {"path": {"type": "string"}, "patches": {"type": "string"}}, "required": ["path", "patches"]}, t.patch_file),
            ("run_command", "Run shell command", {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}, t.run_command),
            ("list_files", "List files recursively", {"type": "object", "properties": {"directory": {"type": "string"}, "pattern": {"type": "string"}, "max_depth": {"type": "integer"}}, "required": []}, t.list_files),
            ("search_files", "Search text in files", {"type": "object", "properties": {"query": {"type": "string"}, "directory": {"type": "string"}, "extensions": {"type": "string"}}, "required": ["query"]}, t.search_files),
            ("think", "Record reasoning", {"type": "object", "properties": {"thought": {"type": "string"}}, "required": ["thought"]}, t.think),
            ("checkpoint", "Create git checkpoint", {"type": "object", "properties": {"message": {"type": "string"}}, "required": []}, t.checkpoint),
            ("undo", "Undo previous checkpoint", {"type": "object", "properties": {}, "required": []}, t.undo),
            ("spawn_agent", "Spawn child SWML agent", {"type": "object", "properties": {"task": {"type": "string"}, "max_turns": {"type": "integer"}}, "required": ["task"]}, t.spawn_agent),
            ("view_image", "Attach image for vision models", {"type": "object", "properties": {"path": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["path"]}, t.view_image),
        ]
        for name, desc, params, fn in specs:
            self.tools.register(name, desc, params, fn)

    def _on_watch(self, path, evt):
        self.pending_watcher.append((evt, path))

    def inject_multimodal_message(self, prompt, b64):
        self.pending_multimodal.append({"role": "user", "content": prompt, "images": [b64]})

    def _watch_note(self):
        if not self.pending_watcher:
            return None
        rows = []
        while self.pending_watcher:
            evt, path = self.pending_watcher.popleft()
            rows.append(f"- {evt}: {os.path.relpath(path, os.getcwd())}")
        if not rows:
            return None
        return "File watcher update (auto):\n" + "\n".join(rows[:30])

    def _approve(self, name, args):
        if self.auto_approve or name == "think":
            return True
        print(f"\n{C.YELLOW}Tool request: {name}{C.RESET}")
        for k, v in args.items():
            s = str(v)
            if len(s) > 240:
                s = s[:240] + "..."
            print(f"  {k}: {s}")
        try:
            ans = input("Allow? [Y/n] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False
        return ans in {"", "y", "yes"}

    def _detect_phase(self, content, has_tools=False):
        if has_tools:
            return "EXECUTE"
        c = (content or "").lower()
        if any(k in c for k in ["inspect", "read", "understand", "check file"]):
            return "OBSERVE"
        if any(k in c for k in ["plan", "approach", "strategy", "steps"]):
            return "PLAN"
        if any(k in c for k in ["test", "verify", "passed", "confirm"]):
            return "VERIFY"
        if any(k in c for k in ["edit", "write", "implement", "fix", "change"]):
            return "EXECUTE"
        return None

    def _call_messages(self):
        msgs = list(self.messages)
        note = self._watch_note()
        if note:
            msgs.append({"role": "system", "content": note})
        while self.pending_multimodal:
            msgs.append(self.pending_multimodal.popleft())
        msgs, c_note = self.context.maybe_summarize(msgs)
        if c_note:
            self.metrics.context_summaries += 1
            if self.verbose:
                print(f"{C.DIM}{c_note}{C.RESET}")
        return msgs

    def _save(self, title=""):
        self.session_store.save(self.session_id, {
            "id": self.session_id,
            "title": title or self.task_desc,
            "model": self.model,
            "sidecar_model": self.sidecar_model,
            "messages": self.messages,
            "omega": self.omega.to_dict(),
            "metrics": self.metrics.to_dict(),
            "context_limit": self.context.limit,
            "depth": self.depth,
            "updated_at": now_iso(),
        })

    @classmethod
    def from_session(cls, data, auto_approve=False, verbose=False, watch=True):
        a = cls(data.get("model"), data.get("sidecar_model"), auto_approve, verbose, SessionStore(), data.get("id"), data.get("depth", 0), watch=watch)
        a.messages = data.get("messages") or a.messages
        a.omega = OmegaState.from_dict(data.get("omega", {}))
        a.metrics = SWMLMetrics.from_dict(data.get("metrics", {}))
        if data.get("context_limit"):
            a.context.limit = max(2048, int(data.get("context_limit")))
        return a

    def _run_llm(self):
        print(f"\n{self.omega.render()}")
        msgs = self._call_messages()
        spin = Spinner()

        def on_chunk(ch):
            spin.set_tokens(ch.get("eval_count", 0) or 0)

        print(f"{C.CYAN}{'-' * min(term_width() - 2, 72)}{C.RESET}")
        spin.start()
        t0 = time.time()
        try:
            res = ollama_chat(self.model, msgs, tools=self.tools.as_ollama(), stream=True, on_chunk=on_chunk)
        finally:
            spin.stop()
        dt = max(0.001, time.time() - t0)
        spd = (res.get("tokens_out", 0) or 0) / dt
        self.metrics.inference_speeds.append((time.time(), spd))
        self.omega.tokens_in += res.get("tokens_in", 0)
        self.omega.tokens_out += res.get("tokens_out", 0)
        self.metrics.tokens_in += res.get("tokens_in", 0)
        self.metrics.tokens_out += res.get("tokens_out", 0)
        print(f"{C.DIM}Inference: in={res.get('tokens_in',0)} out={res.get('tokens_out',0)} {spd:.1f} tok/s{C.RESET}")
        return res

    def _tool_exec(self, calls):
        did = False
        for tc in calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not self._approve(name, args):
                self.messages.append({"role": "tool", "content": "Denied by user."})
                continue
            self.omega.tool_calls += 1
            self.metrics.tool_usage[name] += 1
            t0 = time.time()
            out = self.tools.execute(name, args)
            dt = time.time() - t0
            did = True
            print(f"{C.GREEN}tool:{name}{C.RESET} {C.DIM}{dt:.2f}s {len(out)} chars{C.RESET}")
            prev = out[:700] + ("\n..." if len(out) > 700 else "")
            print(f"{C.DIM}{prev}{C.RESET}")
            self.messages.append({"role": "tool", "content": out[:12000]})
        return did

    def _detect_tests(self):
        cwd = Path.cwd()
        if (cwd / "pytest.ini").exists() or (cwd / "pyproject.toml").exists() or any(cwd.rglob("test_*.py")):
            return "python -m pytest -q"
        if (cwd / "package.json").exists():
            return "npm test -- --watch=false"
        if (cwd / "go.mod").exists():
            return "go test ./..."
        if (cwd / "Cargo.toml").exists():
            return "cargo test"
        return None

    def _auto_test(self):
        if not self.modified_files:
            return None
        cmd = self._detect_tests()
        if not cmd:
            self.modified_files.clear()
            return "No tests detected for auto-test loop."
        self.omega.transition("VERIFY")
        self.metrics.tests_run += 1
        out = SWMLTools(self).run_command(cmd, timeout=180)
        if "[exit code: 0]" in out:
            self.metrics.tests_passed += 1
            self.modified_files.clear()
            note = f"Auto-test passed with `{cmd}`."
            self.messages.append({"role": "system", "content": note})
            return note
        self.metrics.tests_failed += 1
        self.pending_repair_note = "AUTO-TEST FAILURE. Fix and rerun.\n" + out[:4000]
        return "Auto-test failed; repair loop queued."

    def run_turn(self, user_input=None):
        if user_input:
            self.messages.append({"role": "user", "content": user_input})
        if self.pending_repair_note:
            self.messages.append({"role": "user", "content": self.pending_repair_note})
            self.pending_repair_note = None
            self.omega.transition("EXECUTE")

        try:
            res = self._run_llm()
        except ConnectionError as exc:
            print(f"{C.RED}{exc}{C.RESET}")
            return False
        except Exception as exc:
            print(f"{C.RED}LLM error: {exc}{C.RESET}")
            traceback.print_exc()
            return False

        content, calls = res.get("content", ""), res.get("tool_calls", [])
        msg = {"role": "assistant"}
        if content:
            msg["content"] = content
        if calls:
            msg["tool_calls"] = calls
        self.messages.append(msg)

        ph = self._detect_phase(content, bool(calls))
        if ph:
            self.omega.transition(ph)

        did_tools = self._tool_exec(calls) if calls else False
        note = self._auto_test()
        if note and self.verbose:
            print(f"{C.BLUE}{note}{C.RESET}")

        self.metrics.sample(self.omega)
        self._save()
        return did_tools or bool(self.pending_repair_note)

    def run_task(self, task, one_shot=False):
        self.task_desc = (task or "")[:80]
        turn = 0
        cont = self.run_turn(task)
        while cont and turn < self.max_turns:
            turn += 1
            cont = self.run_turn()
        self.omega.transition("VERIFY")
        self.metrics.sample(self.omega)
        self._save(self.task_desc)
        summary = f"Complete. S={self.omega.action_integral():+.3f} eta={self.omega.efficiency()*100:.0f}% tools={self.omega.tool_calls} tokens={self.omega.tokens_in}->{self.omega.tokens_out} session={self.session_id}"
        if not one_shot:
            print(f"\n{C.GREEN}{summary}{C.RESET}")
        return summary

    def dashboard(self):
        w = min(term_width(), 120)
        sep = "=" * (w - 2)
        total = max(1, sum(self.metrics.phase_counts.values()))
        lines = [
            f"{C.CYAN}{sep}{C.RESET}",
            f"{C.BOLD}SWML Dashboard{C.RESET} session={self.session_id}",
            f"model={self.model}" + (f" sidecar={self.sidecar_model}" if self.sidecar_model else ""),
            f"tokens in/out: {self.metrics.tokens_in}/{self.metrics.tokens_out}",
            f"tests run/pass/fail: {self.metrics.tests_run}/{self.metrics.tests_passed}/{self.metrics.tests_failed}",
            f"context summaries: {self.metrics.context_summaries} sub-agents: {self.metrics.sub_agents}",
            "",
            f"{C.BOLD}Energy History{C.RESET}",
        ]
        for _, ph, t, v, h in self.metrics.energy_history[-20:]:
            lines.append(f"{ph:<7} H={h:.2f} T={t:.2f} V={v:.2f} {'#' * int(h * 10)}")
        if not self.metrics.energy_history:
            lines.append("(no samples yet)")

        lines += ["", f"{C.BOLD}Tool Usage{C.RESET}"]
        if self.metrics.tool_usage:
            for n, c in self.metrics.tool_usage.most_common(12):
                lines.append(f"{n:<14} {c:>4}")
        else:
            lines.append("(no tool calls)")

        lines += ["", f"{C.BOLD}Phase Distribution (ASCII Pie){C.RESET}"]
        order, sym = ["OBSERVE", "PLAN", "EXECUTE", "VERIFY"], {"OBSERVE": "O", "PLAN": "P", "EXECUTE": "E", "VERIFY": "V"}
        acc, cur = [], 0.0
        for p in order:
            cur += self.metrics.phase_counts.get(p, 0) / total
            acc.append((p, cur))
        slices, pie = 30, []
        for i in range(slices):
            x = (i + 0.5) / slices
            pick = "VERIFY"
            for p, edge in acc:
                if x <= edge:
                    pick = p
                    break
            pie.append(sym[pick])
        lines.append("(" + "".join(pie) + ")")
        for p in order:
            lines.append(f"{sym[p]} {p:<7} {(self.metrics.phase_counts.get(p,0)/total)*100:5.1f}%")

        lines += ["", f"{C.BOLD}Efficiency Over Time{C.RESET}"]
        if self.metrics.efficiency_history:
            vals = [e for _, e in self.metrics.efficiency_history[-30:]]
            lines.append("".join(" .:-=+*#%@"[min(9, max(0, int(v * 10) - 1))] for v in vals))
            lines.append(f"latest eta={vals[-1]*100:.1f}%")
        else:
            lines.append("(no efficiency data)")
        lines.append(f"{C.CYAN}{sep}{C.RESET}")
        return "\n".join(lines)


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
    preferred = ["qwen3-coder", "qwen2.5-coder", "codellama", "deepseek-coder", "qwen3"]
    for pref in preferred:
        for m in models:
            if pref in m:
                return m
    return models[0]


def run_repl(agent, model):
    print(f"{C.DIM}Commands: /help /status /dashboard /sessions /model X /quit{C.RESET}\n")

    while True:
        try:
            user = input(f"{C.GREEN}Ω ❯ {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
            break

        if not user:
            continue

        cmd = user.lower()
        if cmd in {"/quit", "/exit", "/q"}:
            print("bye")
            break
        if cmd == "/help":
            print(f"""
  {C.BOLD}Commands:{C.RESET}
    /status      Show current Ω-state
    /dashboard   Show SWML metrics dashboard
    /sessions    List saved sessions
    /model NAME  Switch main model
    /undo        Rollback last git checkpoint
    /help        This help
    /quit        Exit

  {C.BOLD}Ω-space:{C.RESET}
    H = T + V    (Hamiltonian = kinetic + potential)
    S = ∫(T−V)dt (action integral, minimized)
    η = efficiency (higher = better path)
""")
            continue
        if cmd == "/status":
            print(agent.omega.render())
            continue
        if cmd == "/dashboard":
            print(agent.dashboard())
            continue
        if cmd == "/sessions":
            rows = agent.session_store.list_sessions()
            for r in rows:
                print(f"  {r['id']}  {r['updated_at']}  {r['title']}")
            continue
        if cmd == "/undo":
            t = SWMLTools(agent)
            print(t.undo())
            continue
        if cmd.startswith("/model "):
            new_model = user[7:].strip()
            if new_model:
                agent.model = new_model
                agent.model_info = ollama_model_info(new_model)
                agent.vision_enabled = supports_vision(new_model, agent.model_info)
                print(f"  Switched to {C.BOLD}{new_model}{C.RESET}")
            continue

        agent.run_task(user)
        print()


def parse_args():
    parser = argparse.ArgumentParser(description="SWML-Agent: physics-based coding agent")
    parser.add_argument("-p", "--prompt", help="One-shot prompt")
    parser.add_argument("--model", help="Main model")
    parser.add_argument("--sidecar", help="Sidecar model for lightweight tasks")
    parser.add_argument("--resume", help="Resume session id or 'latest'")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve tools")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-watch", action="store_true", help="Disable file watcher")
    return parser.parse_args()


def main():
    args = parse_args()

    model = args.model or detect_model()
    if not model:
        print(f"{C.RED}No Ollama model found. Try: ollama pull qwen3-coder{C.RESET}")
        sys.exit(1)

    store = SessionStore()
    agent = None

    if args.resume:
        sid, data = store.load(args.resume)
        if not data:
            print(f"{C.RED}Session '{args.resume}' not found.{C.RESET}")
            sys.exit(1)
        agent = SWMLAgent.from_session(data, auto_approve=args.yes, verbose=args.verbose, watch=not args.no_watch)
        if args.model:
            agent.model = args.model
        model = agent.model
        print(f"Resumed session: {sid}")
    else:
        agent = SWMLAgent(
            model=model,
            sidecar_model=args.sidecar,
            auto_approve=args.yes,
            verbose=args.verbose,
            session_store=store,
            watch=not args.no_watch,
        )

    info = ollama_model_info(model)
    details = info.get("details", {}) if isinstance(info, dict) else {}

    print(BANNER)
    print(f"  {C.DIM}model   :{C.RESET} {model}")
    if details:
        ps = details.get("parameter_size", "?")
        q = details.get("quantization_level", "?")
        print(f"  {C.DIM}params  :{C.RESET} {ps}, {q}")
    print(f"  {C.DIM}sidecar :{C.RESET} {agent.sidecar_model or '-'}")
    print(f"  {C.DIM}vision  :{C.RESET} {'yes' if agent.vision_enabled else 'no'}")
    print(f"  {C.DIM}context :{C.RESET} {agent.context.limit}")
    print(f"  {C.DIM}session :{C.RESET} {agent.session_id}")
    print(f"  {C.DIM}tools   :{C.RESET} {len(agent.tools.tools)}")
    print(f"  {C.DIM}git     :{C.RESET} {'yes' if agent.is_git_repo else 'no'}")
    print()

    if args.prompt:
        try:
            agent.run_task(args.prompt)
        finally:
            agent.close()
        return

    try:
        run_repl(agent, model)
    finally:
        agent.close()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    main()
