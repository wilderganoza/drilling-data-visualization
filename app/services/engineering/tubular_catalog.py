"""Real API 5CT tubular geometry + grade + connection catalog.

A representative (not exhaustive) subset of standard oilfield casing sizes with
their *published* dimensions — nominal weight, wall, drift — and the mechanical
properties casing design needs: grade minimum yield, and connection ratings
(joint/tension efficiency, compression rating, internal-pressure leak resistance
and whether the connection is a metal-to-metal gas-tight seal).

Honest scope: these are typical published values (API 5CT / common premium
connection datasheets). A real project design pulls the exact numbers from the
manufacturer's tally; this catalog is enough to run the design against realistic
pipe-body and connection limits rather than a wall computed from weight alone."""
# Importamos dataclass para modelar Tubular y Connection como registros simples
from dataclasses import dataclass
# Importamos Optional para tipar parámetros/retornos que pueden venir vacíos
from typing import Optional


# Definimos la geometría de un tubular (casing) del catálogo
@dataclass
class Tubular:
    od: float          # in
    weight: float      # nominal ppf
    wall: float        # in
    id_in: float       # in
    drift: float       # in


# --- API 5CT casing dimensions (od -> list of weights) -------------------------
# (od, weight, wall, id, drift)
# Guardamos la tabla de dimensiones de casing publicadas por API 5CT
_CASING = [
    (30.0, 157.0, 0.625, 28.750, 28.500),
    (20.0, 94.0, 0.438, 19.124, 18.936),
    (20.0, 106.5, 0.500, 19.000, 18.812),
    (20.0, 133.0, 0.635, 18.730, 18.542),
    (18.625, 87.5, 0.435, 17.755, 17.567),
    (16.0, 84.0, 0.495, 15.010, 14.822),
    (16.0, 97.0, 0.575, 14.850, 14.662),
    (13.375, 54.5, 0.380, 12.615, 12.459),
    (13.375, 61.0, 0.430, 12.515, 12.359),
    (13.375, 68.0, 0.480, 12.415, 12.259),
    (13.375, 72.0, 0.514, 12.347, 12.191),
    (10.75, 45.5, 0.400, 9.950, 9.794),
    (10.75, 51.0, 0.450, 9.850, 9.694),
    (10.75, 55.5, 0.495, 9.760, 9.604),
    (9.625, 40.0, 0.395, 8.835, 8.679),
    (9.625, 43.5, 0.435, 8.755, 8.599),
    (9.625, 47.0, 0.472, 8.681, 8.525),
    (9.625, 53.5, 0.545, 8.535, 8.379),
    (8.625, 36.0, 0.400, 7.825, 7.700),
    (8.625, 44.0, 0.500, 7.625, 7.500),
    (7.625, 39.0, 0.500, 6.625, 6.500),
    (7.0, 23.0, 0.317, 6.366, 6.241),
    (7.0, 26.0, 0.362, 6.276, 6.151),
    (7.0, 29.0, 0.408, 6.184, 6.059),
    (7.0, 32.0, 0.453, 6.094, 5.969),
    (7.0, 35.0, 0.498, 6.004, 5.879),
    (7.0, 38.0, 0.540, 5.920, 5.795),
    (5.5, 17.0, 0.304, 4.892, 4.767),
    (5.5, 20.0, 0.361, 4.778, 4.653),
    (5.5, 23.0, 0.415, 4.670, 4.545),
    (5.0, 18.0, 0.362, 4.276, 4.151),
    (4.5, 13.5, 0.290, 3.920, 3.795),
    (4.5, 15.1, 0.337, 3.826, 3.701),
]

# --- Grade minimum yield strength (psi) & ultimate (psi) ------------------------
# Guardamos, por grado de acero, el par (fluencia mínima, resistencia última) en psi
GRADES = {
    "H-40": (40000, 60000), "J-55": (55000, 75000), "K-55": (55000, 95000),
    "M-65": (65000, 85000), "N-80": (80000, 100000), "L-80": (80000, 95000),
    "C-90": (90000, 100000), "C-95": (95000, 105000), "T-95": (95000, 105000),
    "P-110": (110000, 125000), "Q-125": (125000, 135000),
    "X-52": (52000, 66000), "X-56": (56000, 71000), "X-60": (60000, 75000),
}

# --- Connection ratings --------------------------------------------------------
# eff_tension : joint tensile efficiency as a fraction of pipe-body yield tension
# eff_compress: compression rating as a fraction of pipe-body yield (API threaded
#               connections carry little compression; premium carry ~60-100%)
# eff_internal: internal-pressure (leak) resistance as a fraction of pipe-body burst
# gas_tight   : metal-to-metal seal rated for gas (True) vs thread-and-coupling (False)
# Definimos las propiedades de una conexión (rendimiento relativo al cuerpo del tubo)
@dataclass
class Connection:
    name: str
    eff_tension: float
    eff_compress: float
    eff_internal: float
    gas_tight: bool


# Guardamos el catálogo de conexiones conocidas, indexado por su código corto
CONNECTIONS = {
    "STC": Connection("STC (API short round)", 0.62, 0.25, 0.80, False),
    "LTC": Connection("LTC (API long round)", 0.80, 0.30, 0.90, False),
    "BTC": Connection("BTC (API buttress)", 0.95, 0.55, 1.00, False),
    "Premium": Connection("Premium (metal seal)", 1.00, 0.60, 1.00, True),
    "TSH": Connection("TenarisHydril (premium)", 1.00, 0.80, 1.00, True),
    "VAM": Connection("VAM (premium)", 1.00, 0.80, 1.00, True),
    "Semi-premium": Connection("Semi-premium", 0.90, 0.50, 1.00, True),
}
# Definimos la conexión genérica que usamos cuando no reconocemos el nombre dado
_DEFAULT_CONN = Connection("Generic (assumed API BTC)", 0.90, 0.50, 0.95, False)


def lookup(od: float, weight: Optional[float] = None) -> Optional[Tubular]:
    """Nearest catalog tubular for an OD (and weight if given)."""
    # Buscamos candidatos con OD muy cercano (tolerancia de 0.30 in)
    cands = [t for t in _CASING if abs(t[0] - od) < 0.30]
    if not cands:
        # Si no hay match cercano, tomamos los 6 tubulares con OD más próximo de todo el catálogo
        cands = _CASING
        cands = sorted(cands, key=lambda t: abs(t[0] - od))[:6]
    if weight is not None:
        # Si nos dieron peso nominal, desempatamos por OD y luego por peso
        best = min(cands, key=lambda t: (abs(t[0] - od), abs(t[1] - weight)))
    else:
        # Sin peso, elegimos solo por OD más cercano
        best = min(cands, key=lambda t: abs(t[0] - od))
    # Devolvemos el tubular encontrado como dataclass tipado
    return Tubular(*best)


def grade_yield(grade: Optional[str]) -> float:
    # Buscamos el grado normalizando mayúsculas/espacios; usamos N-80 (80000 psi) como default razonable
    g = GRADES.get((grade or "").strip().upper())
    return float(g[0]) if g else 80000.0


def grade_ultimate(grade: Optional[str]) -> float:
    # Igual que grade_yield pero devolviendo la resistencia última
    g = GRADES.get((grade or "").strip().upper())
    return float(g[1]) if g else 100000.0


def connection(name: Optional[str]) -> Connection:
    """Resolve a connection string (fuzzy) to its ratings."""
    key = (name or "").strip()
    if not key:
        # Sin nombre, devolvemos la conexión genérica por defecto
        return _DEFAULT_CONN
    if key in CONNECTIONS:
        # Coincidencia exacta con el código del catálogo
        return CONNECTIONS[key]
    up = key.upper()
    # Probamos coincidencia parcial en cualquier dirección (código dentro del texto o viceversa)
    for k, c in CONNECTIONS.items():
        if k.upper() in up or up in k.upper():
            return c
    # Reconocemos marcas/palabras típicas de conexiones premium aunque no estén en el catálogo exacto
    if any(t in up for t in ("VAM", "TSH", "HYDRIL", "PREMIUM", "TENARIS", "JFE", "SEAL")):
        return CONNECTIONS["Premium"]
    if "BTC" in up or "BUTTRESS" in up:
        return CONNECTIONS["BTC"]
    if "LTC" in up or "LONG" in up:
        return CONNECTIONS["LTC"]
    if "STC" in up or "SHORT" in up:
        return CONNECTIONS["STC"]
    # Si nada coincide, caemos de nuevo en la conexión genérica
    return _DEFAULT_CONN
