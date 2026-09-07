"""WITS0 (Wellsite Information Transfer Specification, Level 0) framing.

WITS0 is the decades-old, still near-universal ASCII protocol drilling
instrumentation systems use to stream real-time parameters to third-party
software — it's exactly the channel SZJ-II exposes for "third-party data
communication" (see its manual, section 2.2.6.6). This module only implements
the FRAMING, which is a stable, public, vendor-independent standard:

    &&
    0108   4521.30
    0110   18.40
    0113   112
    !!

- A frame starts with a line that is exactly "&&" and ends with a line that
  is exactly "!!".
- Every line in between is one "slot": the first 4 characters are a record
  number (2 digits) + item number (2 digits), e.g. "0108" = record 01, item
  08; everything after that (trimmed) is the value, as plain text.
- There is no checksum and no fixed encoding beyond ASCII/Latin-1 text.

What this module deliberately does NOT hardcode: which record/item number
means "depth" or "hookload" for THIS specific rig. Those are defined by the
vendor's own WITS_Predefined_xx.ini and can vary — see wits0_map.py, which
starts empty on purpose. Guessing item numbers and shipping them as if
confirmed would silently write wrong data into the wrong columns, which is
worse than not mapping them at all."""
# Importamos dataclass para representar una trama decodificada de forma simple
from dataclasses import dataclass, field
# Importamos AsyncIterator/Iterable para tipar los generadores de tramas
from typing import AsyncIterator, Dict, Iterable, List

# Marcamos el inicio y el fin de una trama WITS0, tal como los define el estándar
FRAME_START = "&&"
FRAME_END = "!!"


# Representamos una trama WITS0 ya decodificada: un diccionario {(record, item): valor}
@dataclass
class Wits0Frame:
    # Guardamos los slots de la trama, indexados por (record, item)
    slots: Dict[tuple, str] = field(default_factory=dict)

    # Leemos el valor crudo (string) de un slot, o None si no vino en esta trama
    def raw(self, record: int, item: int) -> str | None:
        return self.slots.get((record, item))

    # Leemos el valor de un slot ya convertido a float, o None si no vino o no es numérico
    def as_float(self, record: int, item: int) -> float | None:
        v = self.raw(record, item)
        if v is None:
            return None
        try:
            # WITS0 a veces separa miles con espacios o trae signos +; probamos la conversión directa primero
            return float(v.strip())
        except ValueError:
            return None


# Decodificamos una sola línea de datos dentro de una trama ("RRII valor") a (record, item, valor)
def _parse_slot_line(line: str) -> tuple | None:
    # Una línea de slot necesita al menos 4 caracteres para el código record+item
    if len(line) < 4:
        return None
    code = line[:4]
    # El código debe ser puramente numérico (2 dígitos de registro + 2 de ítem)
    if not code.isdigit():
        return None
    record = int(code[:2])
    item = int(code[2:4])
    # El resto de la línea (recortado) es el valor; puede venir vacío si el nodo no tiene lectura
    value = line[4:].strip()
    return record, item, value


# Decodificamos un bloque de texto WITS0 (puede traer una o varias tramas) en una lista de Wits0Frame
def parse_wits0_text(text: str) -> List[Wits0Frame]:
    frames: List[Wits0Frame] = []
    current: Dict[tuple, str] | None = None
    # Recorremos línea por línea, sin asumir un separador de línea específico (CRLF o LF)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            # Ignoramos líneas vacías, tanto dentro como fuera de una trama
            continue
        if line == FRAME_START:
            # Iniciamos una trama nueva; si había una a medio construir, la descartamos
            # (una trama incompleta — sin "!!" de cierre — nunca es útil, mejor perderla que corromper la siguiente)
            current = {}
            continue
        if line == FRAME_END:
            # Cerramos la trama actual y la agregamos al resultado, si había una abierta
            if current is not None:
                frames.append(Wits0Frame(slots=current))
            current = None
            continue
        if current is None:
            # Una línea de datos fuera de "&&"..."!!" no es válida — la ignoramos en vez de fallar
            continue
        # Decodificamos la línea de slot y la agregamos a la trama en construcción
        parsed = _parse_slot_line(line)
        if parsed is not None:
            record, item, value = parsed
            current[(record, item)] = value
    return frames


# Decodificamos tramas WITS0 a medida que llegan por un socket asyncio, sin esperar a que se cierre
# la conexión — cede (yield) cada Wits0Frame apenas ve la línea "!!" que la cierra.
async def iter_wits0_frames(reader) -> AsyncIterator[Wits0Frame]:
    """`reader` es un asyncio.StreamReader (o cualquier objeto con `readline()` async
    que devuelva bytes, terminando en b"" al cerrarse la conexión)."""
    current: Dict[tuple, str] | None = None
    while True:
        # Leemos una línea cruda del socket; b"" significa que el otro lado cerró la conexión
        raw = await reader.readline()
        if raw == b"":
            break
        # Decodificamos tolerando bytes que no sean UTF-8 estricto (equipos industriales a veces
        # mandan Latin-1 o basura ocasional en el cable serie-a-TCP)
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        if line == FRAME_START:
            current = {}
            continue
        if line == FRAME_END:
            if current is not None:
                yield Wits0Frame(slots=current)
            current = None
            continue
        if current is None:
            continue
        parsed = _parse_slot_line(line)
        if parsed is not None:
            record, item, value = parsed
            current[(record, item)] = value


# Codificamos una trama (para el simulador de pruebas / para probar contra el equipo real) en el
# formato de texto WITS0, lista para mandar por socket.
def encode_wits0_frame(slots: Dict[tuple, str]) -> str:
    lines = [FRAME_START]
    for (record, item), value in slots.items():
        # Formateamos el código como 2 dígitos de registro + 2 de ítem, seguido de un espacio y el valor
        lines.append(f"{record:02d}{item:02d} {value}")
    lines.append(FRAME_END)
    # Unimos con CRLF, el terminador de línea que usa el estándar WITS0 originalmente sobre serie
    return "\r\n".join(lines) + "\r\n"
