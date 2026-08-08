"""Pre-spud engineering calculators. Each module (casing_design, torque_drag,
hydraulics, well_control, cementing, directional, bha, bit, afe) is a pure
calc function over (params, WellContext). Params come from the
ops_engineering_designs store; WellContext is loaded from the event's Planning
program grids (see context.py)."""
