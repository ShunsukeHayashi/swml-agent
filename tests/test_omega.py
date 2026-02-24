#!/usr/bin/env python3
"""Unit tests for SWML-Agent Omega state system."""

import sys
import os
import time
import math

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We need to import the classes from swml-agent.py
# Since it has a hyphen, we use importlib
import importlib.util
spec = importlib.util.spec_from_file_location("swml_agent", 
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "swml-agent.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OmegaState = mod.OmegaState
VariationalPlanner = mod.VariationalPlanner


def test_initial_state():
    """Agent starts in OBSERVE phase."""
    omega = OmegaState()
    assert omega.phase == "OBSERVE"
    assert omega.phase_index == 0
    assert omega.step_count == 0
    assert omega.tool_calls == 0
    print("✓ test_initial_state")


def test_hamiltonian():
    """H = T + V for each phase."""
    omega = OmegaState()
    
    # OBSERVE: T=0.3, V=0.9, H=1.2
    assert abs(omega.T - 0.3) < 0.01
    assert abs(omega.V - 0.9) < 0.01
    assert abs(omega.H - 1.2) < 0.01
    
    # Transition to EXECUTE: T=0.9, V=0.2, H=1.1
    omega.transition("EXECUTE")
    assert abs(omega.T - 0.9) < 0.01
    assert abs(omega.V - 0.2) < 0.01
    assert abs(omega.H - 1.1) < 0.01
    
    # VERIFY: ground state H=0.3
    omega.transition("VERIFY")
    assert abs(omega.H - 0.3) < 0.01
    print("✓ test_hamiltonian")


def test_lagrangian():
    """L = T - V."""
    omega = OmegaState()
    
    # OBSERVE: L = 0.3 - 0.9 = -0.6
    assert abs(omega.L - (-0.6)) < 0.01
    
    # EXECUTE: L = 0.9 - 0.2 = 0.7
    omega.transition("EXECUTE")
    assert abs(omega.L - 0.7) < 0.01
    print("✓ test_lagrangian")


def test_phase_transitions():
    """Transitions update state correctly."""
    omega = OmegaState()
    
    old, new = omega.transition("PLAN")
    assert old == "OBSERVE"
    assert new == "PLAN"
    assert omega.step_count == 1
    
    old, new = omega.transition("EXECUTE")
    assert old == "PLAN"
    assert new == "EXECUTE"
    assert omega.step_count == 2
    
    # Same phase → no transition
    old, new = omega.transition("EXECUTE")
    assert old is None
    assert new is None
    assert omega.step_count == 2
    print("✓ test_phase_transitions")


def test_action_integral():
    """S = ∫L dt should accumulate over time."""
    omega = OmegaState()
    
    # Initial: no action yet
    assert omega.action_integral() == 0.0
    
    # Wait a tiny bit and transition
    time.sleep(0.05)
    omega.transition("PLAN")
    
    S = omega.action_integral()
    # S should be negative (OBSERVE has L = -0.6, so S ≈ -0.6 * dt < 0)
    assert S < 0, f"Expected S < 0, got {S}"
    print("✓ test_action_integral")


def test_entropy():
    """Entropy increases with more diverse phase visits."""
    omega = OmegaState()
    
    # Only OBSERVE visited → low entropy
    e1 = omega.entropy()
    
    # Visit more phases → higher entropy
    omega.transition("PLAN")
    omega.transition("EXECUTE")
    omega.transition("VERIFY")
    e2 = omega.entropy()
    
    assert e2 > e1, f"Expected entropy to increase: {e1} → {e2}"
    print("✓ test_entropy")


def test_efficiency():
    """Efficiency should be between 0 and 1."""
    omega = OmegaState()
    eta = omega.efficiency()
    assert 0.0 <= eta <= 1.0, f"Expected 0 ≤ η ≤ 1, got {eta}"
    print("✓ test_efficiency")


def test_render():
    """Render should produce non-empty string."""
    omega = OmegaState()
    output = omega.render("test task")
    assert len(output) > 0
    assert "OBSERVE" in output
    print("✓ test_render")


def test_trajectory():
    """Trajectory plot needs at least 2 history points."""
    omega = OmegaState()
    
    # Single point → empty
    assert omega.render_trajectory() == ""
    
    # Multiple points → has content
    omega.transition("PLAN")
    omega.transition("EXECUTE")
    traj = omega.render_trajectory()
    assert len(traj) > 0
    print("✓ test_trajectory")


def test_variational_planner():
    """Planner should score and rank plans."""
    plans = [
        "1. Read the file\n2. Edit one line\n3. Run tests",
        "1. Read all files\n2. Analyze dependencies\n3. Create new module\n4. Write tests\n5. Edit config\n6. Run full suite\n7. Deploy",
    ]
    ranked = VariationalPlanner.compare_plans(plans)
    assert len(ranked) == 2
    # Simpler plan should have lower action
    assert ranked[0]["steps"] <= ranked[1]["steps"]
    print("✓ test_variational_planner")


def test_ground_state_is_minimum():
    """VERIFY should have the lowest Hamiltonian."""
    omega = OmegaState()
    energies = {}
    for phase in OmegaState.PHASES:
        T, V = OmegaState.PHASE_ENERGY[phase]
        energies[phase] = T + V
    
    assert energies["VERIFY"] == min(energies.values()), \
        f"VERIFY should be ground state, got {energies}"
    print("✓ test_ground_state_is_minimum")


if __name__ == "__main__":
    tests = [
        test_initial_state,
        test_hamiltonian,
        test_lagrangian,
        test_phase_transitions,
        test_action_integral,
        test_entropy,
        test_efficiency,
        test_render,
        test_trajectory,
        test_variational_planner,
        test_ground_state_is_minimum,
    ]
    
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
    
    print(f"\n{'═' * 40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("All tests passed! ✓")
    sys.exit(failed)
