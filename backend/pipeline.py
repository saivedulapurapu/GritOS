"""The GritOS analysis pipeline: one business state in, one analysis dict out (no I/O)."""
import capital_lock
import dependency_index
import financial_engine
import fragility_model
import grit
import runway_decay
import shock_engine
from schemas import CURRENCY_SYMBOLS, FullBusinessState


def process_business_state(state: FullBusinessState):
    # 1. Baseline calc
    baseline = financial_engine.calculate_operational_metrics(
        state.revenue, state.ad_spend, state.cogs, state.shipping_cost, state.rto_cost
    )
    bottom_line = financial_engine.calculate_net_metrics(baseline['contribution_margin'], state.fixed_costs, state.cash_in_bank)

    # 2. Shock Simulation
    shock_results = shock_engine.apply_shocks(
        state.model_dump(), state.cac_shock, state.rev_shock, state.cogs_shock, state.ad_spend_behaviour
    )

    # 3. Capital Lock
    lock_data = capital_lock.calculate_capital_lock(
        state.stock_units, state.cost_per_unit, state.daily_velocity, CURRENCY_SYMBOLS[state.currency]
    )

    # 4. Concentration (HHI) — structural, so the same value applies to baseline and stressed state
    dependency = dependency_index.get_dependency_score(
        state.top_platform_rev, state.revenue, state.top_supplier_spend, state.total_purchases,
        state.platform_shares, state.supplier_shares,
    )
    concentration_hhi = dependency['max_hhi']

    # 5. Fragility tier (baseline structure) & shock sensitivity
    ad_spend_ratio = state.ad_spend / state.revenue if state.revenue > 0 else 0
    total_shock_pct = state.cac_shock + state.rev_shock + state.cogs_shock

    fragility = fragility_model.classify_fragility(
        baseline['margin_percent'], bottom_line['runway_months'], ad_spend_ratio, concentration_hhi
    )
    sensitivity = fragility_model.get_shock_sensitivity(bottom_line['runway_months'], shock_results['runway'], total_shock_pct)
    fragility['sensitivity'] = sensitivity
    shock_results['runway_lost_months'] = fragility_model.runway_lost_within_horizon(
        bottom_line['runway_months'], shock_results['runway']
    )

    # Same rules on the shocked figures: how the business looks under this scenario.
    stressed = fragility_model.classify_fragility(
        shock_results['margin_percent'], shock_results['runway'], shock_results['ad_spend_ratio'], concentration_hhi
    )
    fragility['stressed_class'] = stressed['class']
    fragility['stressed_reasons'] = stressed['reasons']

    # 6. Runway-decay estimate: λ = runway x BASELINE tier factor (<= runway).
    # Sensitivity is reported, not used here. The scenario estimate uses the SHOCKED
    # runway; the baseline estimate (no shock) feeds the Grit Score.
    runway_decay_estimate = runway_decay.calculate_runway_decay_estimate(shock_results['runway'], fragility['class'])
    trajectory = runway_decay.calculate_runway_decay_trajectory(shock_results['runway'], fragility['class'])
    baseline_runway_decay_estimate = runway_decay.calculate_runway_decay_estimate(bottom_line['runway_months'], fragility['class'])

    days_to_liquidate = lock_data['days_to_liquidate']  # None = no sales velocity

    # 7. Grit Score: the same function on the baseline and on the stressed state.
    # Weights, multipliers and the short-runway cap are justified in grit.py.
    baseline_grit = grit.compute_grit(
        fragility['score'], baseline_runway_decay_estimate, concentration_hhi, days_to_liquidate, bottom_line['runway_months']
    )
    scenario_grit = grit.compute_grit(
        stressed['score'], runway_decay_estimate, concentration_hhi, days_to_liquidate, shock_results['runway']
    )

    return {
        "currency": state.currency,
        "baseline": {**baseline, **bottom_line},
        "simulation": shock_results,
        "inventory": lock_data,
        "fragility": fragility,
        "dependency": dependency,
        "runway_decay_estimate": runway_decay_estimate,
        "baseline_runway_decay_estimate": baseline_runway_decay_estimate,
        "trajectory": trajectory,
        "grit_score": scenario_grit['score'],
        "baseline_grit": baseline_grit['score'],
        "grit_breakdown": scenario_grit,
        "ad_spend_ratio": ad_spend_ratio
    }
