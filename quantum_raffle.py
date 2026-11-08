# =============================================================================
# Quantum Dice You Can Audit — CHSH Raffle
# Florida Qiskit Fallfest Hackathon 2026
#
# This script uses the CHSH inequality to verify that raffle randomness
# is genuinely quantum. Cheaters who skip entanglement are automatically
# detected by the laws of physics.
#
# How to run:
#   1. pip install qiskit qiskit-ibm-runtime numpy matplotlib pylatexenc
#   2. Set USE_HARDWARE = False for simulator, True for real IBM hardware
#   3. If USE_HARDWARE = True, fill in your API key and CRN below
#   4. Run the script: python quantum_raffle.py
# =============================================================================

# --- CELL 1: Imports ---

import numpy as np
import hashlib
import matplotlib.pyplot as plt

from qiskit import QuantumCircuit, transpile
from qiskit.primitives import StatevectorSampler


# --- CELL 2: Configuration ---

USE_HARDWARE = False   # Set to True to run on real IBM quantum hardware

SHOTS = 1024           # Number of times each circuit is run

# IBM Quantum credentials (only needed if USE_HARDWARE = True)
IBM_API_KEY = "YOUR_44_CHARACTER_API_KEY_HERE"
IBM_CRN     = "YOUR_CRN_HERE"

# Optimal measurement angles for CHSH (in radians)
# These angles maximize S toward the Tsirelson bound of 2*sqrt(2) ≈ 2.828
ANGLES = {
    'A0':  np.pi / 2,   # Alice setting 0
    'A1':  0.0,          # Alice setting 1
    'B0':  np.pi / 4,   # Bob setting 0
    'B1': -np.pi / 4,   # Bob setting 1
}

# S = E(A0,B0) - E(A0,B1) + E(A1,B0) + E(A1,B1)
SIGNS = {
    ('A0', 'B0'): +1,
    ('A0', 'B1'): -1,
    ('A1', 'B0'): +1,
    ('A1', 'B1'): +1,
}

# Players: (name, is_cheater)
# Add or remove players here. Keep to 2-3 for hardware runs.
PLAYER_CONFIGS = [
    ("Alice",   False),   # honest
    ("Bob",     False),   # honest
    ("Mallory", True),    # cheater
]

# Raffle entrant list — everyone who bought a ticket
ENTRANTS = ["Alice", "Bob", "Mallory", "Carol", "Dave"]

# How many standard deviations above 2 a player must be to pass
SIGMA_THRESHOLD = 5.0


# --- CELL 3: Build the Bell Circuit ---
#
# HOW THIS WORKS:
#   Step 1: H gate puts qubit 0 into superposition (50% |0>, 50% |1>)
#   Step 2: CNOT (CX) gate entangles qubit 1 with qubit 0
#   Result: Bell state (|00> + |11>) / sqrt(2) — classically impossible correlations
#   Step 3: RY rotations let us measure in different bases (the 4 CHSH settings)

def build_circuit(alice_angle, bob_angle):
    """Build an honest entangled CHSH circuit."""
    qc = QuantumCircuit(2)
    qc.h(0)                    # Hadamard: superposition
    qc.cx(0, 1)                # CNOT: entangle
    qc.ry(-alice_angle, 0)     # Alice's measurement rotation
    qc.ry(-bob_angle,   1)     # Bob's measurement rotation
    qc.measure_all()
    return qc


def build_rigged_circuit(alice_angle, bob_angle):
    """Build a cheater's circuit — no entanglement, classical correlations only."""
    qc = QuantumCircuit(2)
    # NO qc.h(0)    ← Hadamard removed
    # NO qc.cx(0,1) ← CNOT removed — no entanglement
    qc.ry(-alice_angle, 0)
    qc.ry(-bob_angle,   1)
    qc.measure_all()
    return qc


# --- CELL 4: Compute Expectation Values and S ---
#
# HOW THIS WORKS:
#   counts like {'00': 510, '11': 490, '01': 12, '10': 12}
#   '00' and '11' = Alice and Bob AGREED    → contribute +1
#   '01' and '10' = Alice and Bob DISAGREED → contribute -1
#   E = (agreements - disagreements) / total
#
#   S = E(A0,B0) - E(A0,B1) + E(A1,B0) + E(A1,B1)
#   Classical bound: |S| <= 2
#   Tsirelson bound: |S| <= 2*sqrt(2) ≈ 2.828

def expectation_value(counts):
    """Compute expectation value E from a counts dictionary."""
    total      = sum(counts.values())
    n_agree    = counts.get('00', 0) + counts.get('11', 0)
    n_disagree = counts.get('01', 0) + counts.get('10', 0)
    return (n_agree - n_disagree) / total


def compute_S_and_error(circuits_and_settings, backend=None):
    """
    Run all 4 measurement settings and compute S with statistical error.
    Automatically uses hardware or simulator based on USE_HARDWARE flag.
    """
    E_values   = {}
    E_errors   = {}
    all_counts = {}

    for qc, alice_key, bob_key in circuits_and_settings:
        label = f"{alice_key}{bob_key}"

        if USE_HARDWARE:
            from qiskit_ibm_runtime import SamplerV2 as Sampler
            qc_t    = transpile(qc, backend=backend, optimization_level=1)
            sampler = Sampler(backend)
            result  = sampler.run([qc_t], shots=SHOTS).result()
            counts  = result[0].data.meas.get_counts()
        else:
            result = StatevectorSampler().run([qc], shots=SHOTS).result()
            counts = result[0].data.meas.get_counts()

        all_counts[label] = counts
        E = expectation_value(counts)
        E_values[label]   = E
        E_errors[label]   = np.sqrt((1 - E**2) / SHOTS)

        print(f"  E({alice_key},{bob_key}) = {E:+.4f}  ±{E_errors[label]:.4f}  counts: {counts}")

    S       = sum(sign * E_values[f"{a}{b}"] for (a, b), sign in SIGNS.items())
    sigma_S = np.sqrt(sum(e**2 for e in E_errors.values()))

    return S, sigma_S, E_values, all_counts


# --- CELL 5: Honest Player ---

def hash_bits(bitstring):
    """Create a SHA-256 commitment hash of a bitstring."""
    return hashlib.sha256(bitstring.encode()).hexdigest()


def extract_winner_bits(all_counts):
    """Extract 8 bits from the 4 measurement settings for winner selection."""
    bits = ""
    for label in ['A0B0', 'A0B1', 'A1B0', 'A1B1']:
        most_common = max(all_counts[label], key=all_counts[label].get)
        bits += most_common   # 2 bits per setting → 8 bits total
    return bits


def run_honest_player(name, backend=None):
    """Run the CHSH experiment for an honest player using a real Bell state."""
    print(f"\n{'='*50}")
    print(f"  HONEST PLAYER: {name}")
    print(f"{'='*50}")

    circuits_and_settings = [
        (build_circuit(ANGLES[a], ANGLES[b]), a, b)
        for (a, b) in SIGNS.keys()
    ]

    S, sigma_S, E_values, all_counts = compute_S_and_error(
        circuits_and_settings, backend=backend
    )

    winner_bits = extract_winner_bits(all_counts)
    commitment  = hash_bits(winner_bits)

    print(f"\n  S = {S:.4f}  ±{sigma_S:.4f}")
    print(f"  Classical bound = 2.000  |  Tsirelson bound = {2*np.sqrt(2):.4f}")
    print(f"  Winner bits: {winner_bits}")
    print(f"  Commitment:  {commitment[:16]}...")

    return {
        'name': name, 'is_cheater': False,
        'S': S, 'sigma_S': sigma_S,
        'E_values': E_values,
        'winner_bits': winner_bits,
        'commitment': commitment,
        'all_counts': all_counts,
    }


# --- CELL 6: Cheater ---

def run_cheater(name, backend=None):
    """Run a rigged experiment for a cheating player (no entanglement)."""
    print(f"\n{'='*50}")
    print(f"  CHEATER: {name}  (skipping entanglement secretly)")
    print(f"{'='*50}")

    circuits_and_settings = [
        (build_rigged_circuit(ANGLES[a], ANGLES[b]), a, b)
        for (a, b) in SIGNS.keys()
    ]

    S, sigma_S, E_values, all_counts = compute_S_and_error(
        circuits_and_settings, backend=backend
    )

    winner_bits = extract_winner_bits(all_counts)
    commitment  = hash_bits(winner_bits)

    print(f"\n  S = {S:.4f}  ±{sigma_S:.4f}  (should be <= 2.000 — caught!)")
    print(f"  Winner bits: {winner_bits}")
    print(f"  Commitment:  {commitment[:16]}...")

    return {
        'name': name, 'is_cheater': True,
        'S': S, 'sigma_S': sigma_S,
        'E_values': E_values,
        'winner_bits': winner_bits,
        'commitment': commitment,
        'all_counts': all_counts,
    }


# --- CELL 7: Run All Players ---

def setup_backend():
    """Connect to IBM hardware or return None for simulator."""
    if USE_HARDWARE:
        from qiskit_ibm_runtime import QiskitRuntimeService
        print("Connecting to IBM Quantum...")
        QiskitRuntimeService.save_account(
            token=IBM_API_KEY,
            instance=IBM_CRN,
            region="us-east",
            set_as_default=True,
            overwrite=True,
        )
        service = QiskitRuntimeService()
        backend = service.least_busy(operational=True, simulator=False)
        print(f"Using backend: {backend.name}")
        return backend
    else:
        print("Using local simulator (StatevectorSampler)")
        return None


backend = setup_backend()

players = []
for name, is_cheater in PLAYER_CONFIGS:
    if is_cheater:
        players.append(run_cheater(name, backend))
    else:
        players.append(run_honest_player(name, backend))

print(f"\n\nAll {len(players)} players finished!")
print(f"Honest:   {sum(1 for p in players if not p['is_cheater'])}")
print(f"Cheaters: {sum(1 for p in players if p['is_cheater'])}")


# --- CELL 8: Verifier ---
#
# HOW THIS WORKS:
#   Flag anyone whose S does NOT beat 2 by at least 5 standard deviations.
#   5 sigma = less than 1-in-3.5-million chance of a false accusation.
#   Also verify the commitment hash to confirm bits weren't changed after the fact.

def verify_player(player):
    """Check whether a player's results are consistent with a genuine Bell test."""
    S, sigma_S   = player['S'], player['sigma_S']
    sigmas_above = (S - 2.0) / sigma_S
    passes_bell  = sigmas_above >= SIGMA_THRESHOLD
    hash_matches = hash_bits(player['winner_bits']) == player['commitment']
    passes       = passes_bell and hash_matches

    print(f"\n  Player: {player['name']}")
    print(f"    S = {S:.4f},  {sigmas_above:.1f}σ above classical bound  (need >= {SIGMA_THRESHOLD}σ)")
    print(f"    Bell test:  {'PASS ✓' if passes_bell  else 'FAIL ✗'}")
    print(f"    Hash check: {'PASS ✓' if hash_matches else 'FAIL ✗'}")
    print(f"    --> {'VERIFIED HONEST ✓' if passes else 'FLAGGED AS CHEATER ✗'}")

    return passes


print("\n" + "="*50)
print("  VERIFICATION RESULTS")
print("="*50)

verified_players = [p for p in players if verify_player(p)]

print(f"\n  Honest:  {[p['name'] for p in verified_players]}")
print(f"  Flagged: {[p['name'] for p in players if p not in verified_players]}")


# --- CELL 9: Pick the Winner ---
#
# HOW THIS WORKS:
#   XOR all honest players' bitstrings together.
#   No single player can control the XOR — they'd all need to collude.
#   Convert to a number, take mod number-of-entrants → winner index.

def pick_winner(verified_players, entrants):
    """Combine verified players' bits via XOR and pick a winner."""
    if not verified_players:
        print("No verified players — cannot pick a winner.")
        return None

    print(f"\n{'='*50}")
    print("  PICKING THE WINNER")
    print(f"{'='*50}")

    combined = verified_players[0]['winner_bits']
    print(f"  {verified_players[0]['name']}'s bits: {combined}")

    for p in verified_players[1:]:
        print(f"  {p['name']}'s bits:  {p['winner_bits']}")
        combined = ''.join(
            str(int(a) ^ int(b)) for a, b in zip(combined, p['winner_bits'])
        )

    print(f"  XOR result: {combined}")
    idx    = int(combined, 2) % len(entrants)
    winner = entrants[idx]
    print(f"  Index {idx} of {len(entrants)} → 🎉 WINNER: {winner} 🎉")
    return winner


winner = pick_winner(verified_players, ENTRANTS)


# --- CELL 10: Results Plot ---

def plot_results(players):
    """Bar chart of S values for all players with classical and Tsirelson bounds."""
    names  = [p['name']    for p in players]
    S_vals = [p['S']       for p in players]
    S_errs = [p['sigma_S'] for p in players]
    colors = ['steelblue' if not p['is_cheater'] else 'tomato' for p in players]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(names, S_vals, color=colors, yerr=S_errs,
                  capsize=8, edgecolor='black', linewidth=1.2)

    ax.axhline(2.0,          color='red',   linestyle='--', linewidth=2,
               label='Classical bound (S = 2)')
    ax.axhline(2*np.sqrt(2), color='green', linestyle='--', linewidth=2,
               label=f'Tsirelson bound (S = 2√2 ≈ {2*np.sqrt(2):.3f})')

    for bar, S, err in zip(bars, S_vals, S_errs):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + err + 0.05,
                f'S={S:.3f}', ha='center', fontsize=11, fontweight='bold')

    ax.set_ylabel('CHSH Parameter S', fontsize=13)
    ax.set_title('Quantum Dice You Can Audit — CHSH Results', fontsize=14)
    ax.set_ylim(0, 3.2)
    ax.legend(fontsize=11)
    plt.tight_layout()
    plt.savefig('chsh_results.png', dpi=150)
    plt.show()
    print("Plot saved as chsh_results.png")


plot_results(players)
