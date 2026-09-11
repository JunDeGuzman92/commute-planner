"""Budget tracking and AI surplus advisor.

Commuters set a transport budget; we track what they'd spend per mode,
compare against the budget, and generate actionable advice when there's
a surplus (or deficit).

The advisor is rule-based but presents like a conversation: it considers
food security, savings rate, PRESTO reload strategy, and pass economics
before suggesting where leftover money should go.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from modes import DRT_FARE_PRESTO, DRT_MONTHLY_PASS

# 2026 Ontario living-cost anchors (StatsCan / local averages)
MEAL_COST = 16.0              # average prepared meal in Durham
GROCERY_DAY = 12.0            # daily groceries, budget-conscious
EMERGENCY_FUND_TARGET_WEEKS = 4


@dataclass
class BudgetState:
    """Monthly transport budget and how the user's choices consume it."""
    monthly_budget: float
    trips_per_week: int
    chosen_mode: str
    cost_per_trip: float

    @property
    def trips_per_month(self) -> float:
        return self.trips_per_week * 4.33

    @property
    def monthly_spend(self) -> float:
        # Transit riders may benefit from a pass — model the cheaper option
        if self.chosen_mode == "transit":
            payg = self.trips_per_month * self.cost_per_trip
            return min(payg, DRT_MONTHLY_PASS)
        return self.trips_per_month * self.cost_per_trip

    @property
    def surplus(self) -> float:
        return self.monthly_budget - self.monthly_spend


@dataclass
class Advice:
    headline: str
    actions: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    suggested_allocation: dict = field(default_factory=dict)


def advise_surplus(state: BudgetState, savings_balance: float = 0.0,
                   food_insecure: bool = False) -> Advice:
    """Where should leftover transport budget go?

    Priority order (evidence-based):
      1. Food security if flagged
      2. Emergency fund if savings < 4 weeks of budget
      3. PRESTO reload buffer (avoids overdraft lockouts — see March 2026 rule)
      4. Monthly pass upgrade if it saves money
      5. Discretionary (occasional Uber for late nights, etc.)
    """
    surplus = state.surplus
    if surplus <= 0:
        return advise_deficit(state)

    advice = Advice(
        headline=f"You have ${surplus:.2f}/month left in your transport budget"
    )
    remaining = surplus
    alloc: dict[str, float] = {}

    # 1. Food first — transport savings mean nothing if meals are skipped
    if food_insecure:
        food = min(remaining, MEAL_COST * 8)  # ~8 meals
        alloc["food"] = round(food, 2)
        remaining -= food
        advice.actions.append(f"Put ${food:.0f} toward groceries or meals")
        advice.reasoning.append(
            "Food security comes first — transport savings shouldn't "
            "come at the cost of skipped meals")

    # 2. Emergency buffer
    emergency_target = state.monthly_budget * EMERGENCY_FUND_TARGET_WEEKS / 4.33
    if savings_balance < emergency_target and remaining > 0:
        save = min(remaining, (emergency_target - savings_balance) * 0.3)
        if save >= 10:
            alloc["emergency_savings"] = round(save, 2)
            remaining -= save
            advice.actions.append(f"Move ${save:.0f} to emergency savings")
            advice.reasoning.append(
                f"Build towards a ${emergency_target:.0f} buffer "
                f"(~4 weeks of transport budget)")

    # 3. PRESTO buffer — avoid the negative-balance lockout
    if state.chosen_mode == "transit" and remaining >= 20:
        presto = min(remaining * 0.4, 40.0)
        alloc["presto_buffer"] = round(presto, 2)
        remaining -= presto
        advice.actions.append(f"Keep ${presto:.0f} as a PRESTO balance buffer")
        advice.reasoning.append(
            "Since March 2026, insufficient PRESTO balance locks you out of "
            "all transit until reloaded — a buffer prevents that")

    # 4. Pass upgrade check
    if state.chosen_mode == "transit":
        payg = state.trips_per_month * DRT_FARE_PRESTO
        if payg > DRT_MONTHLY_PASS and state.cost_per_trip > 0:
            advice.actions.append(
                f"Switch to a monthly pass: saves ${payg - DRT_MONTHLY_PASS:.2f}/month")
            advice.reasoning.append(
                f"At {state.trips_per_week} trips/week you're paying "
                f"${payg:.2f} per-ride when a pass costs ${DRT_MONTHLY_PASS:.2f}")

    # 5. Discretionary remainder
    if remaining > 5:
        alloc["discretionary"] = round(remaining, 2)
        advice.actions.append(
            f"${remaining:.0f} left for flexibility — an occasional Uber "
            f"home after a late shift, or extra savings")
        advice.reasoning.append(
            "Keeping some transport surplus unassigned preserves options "
            "for bad-weather days or schedule emergencies")

    advice.suggested_allocation = alloc
    return advice


def advise_deficit(state: BudgetState) -> Advice:
    """The chosen mode blows the budget — find cheaper alternatives."""
    deficit = -state.surplus
    advice = Advice(
        headline=f"This mode exceeds your budget by ${deficit:.2f}/month"
    )
    per_trip_target = state.monthly_budget / state.trips_per_month

    advice.reasoning.append(
        f"Your budget allows ${per_trip_target:.2f}/trip "
        f"({state.trips_per_week} trips/week), but "
        f"{state.chosen_mode} costs ${state.cost_per_trip:.2f}/trip")

    # Suggest concrete swaps
    if state.chosen_mode in ("uber", "taxi"):
        saving = state.cost_per_trip - DRT_FARE_PRESTO
        advice.actions.append(
            f"Switch to DRT transit: saves ${saving * state.trips_per_month:.0f}/month")
        advice.actions.append(
            "For trips where transit doesn't work, try Poparide — "
            "typically half the Uber fare")
    elif state.chosen_mode == "drive":
        advice.actions.append(
            f"Parking + fuel add up. Transit saves ~${deficit:.0f}/month "
            "if your trip is served")
        advice.actions.append(
            "Carpool via Poparide to split costs on days you drive")
    elif state.chosen_mode == "transit" and state.trips_per_month * DRT_FARE_PRESTO > state.monthly_budget:
        advice.actions.append(
            f"A monthly pass (${DRT_MONTHLY_PASS:.2f}) caps your spend")
        advice.actions.append(
            "Check the Transit Assistance Program (TAP) if you receive "
            "ODSP/OW — first 14 trips then free")
    else:
        advice.actions.append("Consider cycling or walking for short trips")
        advice.actions.append("Combine errands into fewer trips")

    advice.suggested_allocation = {}
    return advice


def compare_all_vs_budget(state: BudgetState, all_modes: list[dict]) -> dict:
    """Rank every mode against the budget — the filtering/sorting backend."""
    rows = []
    for m in all_modes:
        monthly = m["cost"] * state.trips_per_month
        rows.append({
            **m,
            "monthly_cost": round(monthly, 2),
            "within_budget": monthly <= state.monthly_budget,
            "budget_delta": round(state.monthly_budget - monthly, 2),
        })
    rows.sort(key=lambda r: r["monthly_cost"])
    return {
        "monthly_budget": state.monthly_budget,
        "trips_per_month": round(state.trips_per_month),
        "modes": rows,
        "cheapest_within_budget": next(
            (r["mode"] for r in rows if r["within_budget"]), None),
    }
