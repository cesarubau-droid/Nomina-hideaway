# ============================================================
# CALCULADOR BASE — Funciones compartidas
# Hotel Rio Celeste Hideaway — Nómina v4.0
# ============================================================

from config import (
    EXTRA_HALF_MIN, EXTRA_FULL_MIN, TOLERANCE_MIN, LATE_PENALTY,
    DUPLICATE_MIN, ORD_HOURS_DEFAULT, ORD_HOURS_COMPENSADO, FERIADOS
)


def t2m(t: str) -> int:
    """'HH:MM' → minutos desde medianoche."""
    if t is None: return 0
    h, m = map(int, str(t)[:5].split(':'))
    return h * 60 + m


def m2t(m: int) -> str:
    """Minutos desde medianoche → 'HH:MM'."""
    m = int(m) % (24 * 60)
    return f"{m//60:02d}:{m%60:02d}"


def r2(x) -> float:
    return round(float(x), 2)


def split_hours(start_m: int, end_m: int) -> tuple:
    """
    Divide un bloque de tiempo en horas diurnas, mixtas y nocturnas.
    Diurna: 05:00-19:30 | Mixta: 19:30-22:30 | Nocturna: 22:30-05:00
    """
    if end_m == start_m:
        return 0.0, 0.0, 0.0
    if end_m < start_m:
        end_m += 24 * 60
    while start_m >= 1440:
        start_m -= 1440
        end_m   -= 1440
    segs = [
        (0,    300,  'noc'), (300,  1170, 'diu'),
        (1170, 1350, 'mix'), (1350, 1440, 'noc'),
        (1440, 1740, 'noc'), (1740, 2610, 'diu'),
        (2610, 2790, 'mix'), (2790, 2880, 'noc'),
    ]
    diu = mix = noc = 0
    for ss, se, tp in segs:
        os_ = max(start_m, ss)
        oe_ = min(end_m, se)
        if oe_ > os_:
            mins = oe_ - os_
            if tp == 'diu':   diu += mins
            elif tp == 'mix': mix += mins
            else:             noc += mins
    return r2(diu / 60), r2(mix / 60), r2(noc / 60)


def nearest_shift(entry_m: int, starts: list) -> tuple:
    """
    Turno más cercano a la entrada real.
    En empate → turno anterior (menor hora).
    Retorna (turno_minutos, diferencia_minutos).
    """
    diffs = [(abs(entry_m - h * 60), h) for h in starts]
    diffs.sort()
    min_diff = diffs[0][0]
    candidates = [h for d, h in diffs if d == min_diff]
    best = min(candidates)
    return best * 60, entry_m - best * 60


def round_exit(exit_m: int, sched_end: int) -> int:
    """
    Redondea la salida real con regla 20/45 relativa al fin del turno.
    - Salida tardía: regla 20/45 hacia adelante
    - Salida anticipada: regla 20/45 hacia atrás (descuenta)
    - Menos de 20min de diferencia en cualquier dirección → fin programado
    """
    diff = exit_m - sched_end

    # Salida tardía
    if diff > 0:
        if diff > 12 * 60:
            diff = 0
        full = diff // 60
        rem  = diff % 60
        if rem < EXTRA_HALF_MIN:
            return sched_end + full * 60
        elif rem < EXTRA_FULL_MIN:
            return sched_end + full * 60 + 30
        else:
            return sched_end + (full + 1) * 60

    # Salida anticipada
    early = sched_end - exit_m  # minutos antes del fin
    if early < 15:
        return sched_end          # menos de 15min → fin programado
    elif early < EXTRA_FULL_MIN:
        return sched_end - 30     # entre 15 y 44min → descuenta 30min
    else:
        full  = early // 60
        rem   = early % 60
        if rem < 15:
            return sched_end - full * 60
        elif rem < EXTRA_FULL_MIN:
            return sched_end - full * 60 - 30
        else:
            return sched_end - (full + 1) * 60


def calc_extra(over_min: int) -> float:
    """Horas extra según regla 20/45."""
    if over_min < EXTRA_HALF_MIN:
        return 0
    elif over_min < EXTRA_FULL_MIN:
        return 0.5
    else:
        full = over_min // 60
        rem  = over_min % 60
        if rem < EXTRA_HALF_MIN:   er = 0
        elif rem < EXTRA_FULL_MIN: er = 0.5
        else:                      er = 1.0
        return full + er


def clean_punches(punches: list) -> list:
    """Elimina marcaciones con menos de DUPLICATE_MIN entre sí."""
    if not punches: return []
    cleaned = [punches[0]]
    for p in punches[1:]:
        if t2m(p) - t2m(cleaned[-1]) >= DUPLICATE_MIN:
            cleaned.append(p)
    return cleaned


def empty(status, nota='', entry_red='', exit_red=''):
    return {
        'diu_o': 0, 'mix_o': 0, 'noc_o': 0,
        'xd': 0, 'xm': 0, 'xn': 0,
        'status': status, 'nota': nota,
        'entry_red': entry_red, 'exit_red': exit_red,
    }


def es_feriado(fecha: str) -> tuple:
    return fecha in FERIADOS, FERIADOS.get(fecha, '')


def calc_early(early_min: int) -> float:
    """
    Calcula horas extra por llegada anticipada.
    Umbral: 25min antes del turno.
    - Menos de 25min → 0h extra
    - Entre 25 y 44min → 0.5h extra
    - 45min o más → escala igual que regla 20/45
    Siempre son horas diurnas.
    """
    if early_min < 25:
        return 0.0
    elif early_min < 45:
        return 0.5
    else:
        full = early_min // 60
        rem  = early_min % 60
        if rem < 25:   er = 0.0
        elif rem < 45: er = 0.5
        else:          er = 1.0
        return float(full) + er


def aplicar_feriado(resultado: dict, fecha: str) -> dict:
    """
    Si el día es feriado, duplica todas las horas (ordinarias y extras).
    Se aplica al resultado final de cualquier calculador.
    """
    is_fer, fer_name = es_feriado(fecha)
    if not is_fer:
        return resultado

    r = resultado.copy()
    r['diu_o'] = r2(r['diu_o'] * 2)
    r['mix_o'] = r2(r['mix_o'] * 2)
    r['noc_o'] = r2(r['noc_o'] * 2)
    r['xd']    = r2(r['xd']    * 2)
    r['xm']    = r2(r['xm']    * 2)
    r['xn']    = r2(r['xn']    * 2)
    r['nota']  = f'★ Feriado: {fer_name} — horas duplicadas'
    return r
