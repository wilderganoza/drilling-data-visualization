# Documentamos el paquete de calculadoras de ingeniería pre-spud (casing_design, torque_drag,
# hydraulics, well_control, cementing, directional, bha, bit, afe); cada módulo expone una
# función de cálculo pura sobre (params, WellContext). Los params vienen del store
# ops_engineering_designs; el WellContext se carga desde los grids del programa de Planning
# del evento (ver context.py)
"""Pre-spud engineering calculators. Each module (casing_design, torque_drag,
hydraulics, well_control, cementing, directional, bha, bit, afe) is a pure
calc function over (params, WellContext). Params come from the
ops_engineering_designs store; WellContext is loaded from the event's Planning
program grids (see context.py)."""
