# ============================================================
# CALCULADOR SEGURIDAD — v4.2
# Reglas:
#   Con Acuerdo (16, 22, 23h): 6h ord noc + 1h extra noc fija
#   Sin Acuerdo (6, 8, 15h): 8h ord + regla 20/45
#   Lizanias (ID 48): jornada flexible Art. 135-138
#     - Sale antes 19:00  → diurna  → límite 8h
#     - Sale 19:00-22:30  → mixta   → límite 7h
#     - Sale después 22:30 → nocturna → límite 6h
#   Confianza: nunca extras
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours, nearest_shift,
    round_exit, calc_extra, calc_early, clean_punches, empty, es_feriado
)
from config import (
    DEPT_STARTS, SEG_ACUERDO_STARTS, SEG_SIN_ACUERDO,
    TOLERANCE_MIN, LATE_PENALTY, ORD_HOURS_DEFAULT, EXTRA_HALF_MIN
)

DEPT   = 'SEGURIDAD'
STARTS = DEPT_STARTS[DEPT]

EID_LIZANIAS = 48

# Ordinarias hardcodeadas por turno con acuerdo (todo nocturno)
# turno_h → (diu_o, mix_o, noc_o)
ACUERDO_ORD = {
    16: (0.0, 0.0, 6.0),   # 16→22: 6h noc
    22: (0.0, 0.0, 6.0),   # 22→05: 6h noc
    23: (0.0, 0.0, 6.0),   # 23→06: 6h noc
}


def calcular(fecha: str, punches_raw: list, es_nocturno: bool = False,
             exit_str: str = None, es_confianza: bool = False,
             eid: int = None) -> dict:
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

    # ── LIZANIAS (ID 48) — jornada flexible especial ─────────
    if eid == EID_LIZANIAS:
        if es_nocturno and exit_str:
            exit_m = t2m(exit_str)
        elif len(punches) >= 2:
            exit_m = t2m(punches[-1])
        else:
            return empty('Sin salida — Andry ajusta',
                         f'Entrada: {entry_str}',
                         entry_red=entry_str, exit_red='?')
        return _lizanias(entry_m, exit_m, nota_fer)

    # ── TURNO NOCTURNO CRUZADO ───────────────────────────────
    if es_nocturno and exit_str:
        exit_m = t2m(exit_str)
        if exit_m <= entry_m:
            exit_m += 24 * 60
        re_m, _ = nearest_shift(entry_m, STARTS)
        turno_h  = re_m // 60

        if turno_h in SEG_ACUERDO_STARTS:
            return _con_acuerdo(re_m, nota_fer, turno_h)
        else:
            return _sin_acuerdo(re_m, exit_m, turno_h, nota_fer, es_confianza, entry_m_real=entry_m)

    # ── TURNO NORMAL ─────────────────────────────────────────
    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    exit_str_real = punches[-1]
    exit_m        = t2m(exit_str_real)
    re_m, diff    = nearest_shift(entry_m, STARTS)
    turno_h       = re_m // 60
    is_late       = diff > TOLERANCE_MIN

    if turno_h in SEG_ACUERDO_STARTS:
        nota = nota_fer if nota_fer else 'Acuerdo Seg: 6h ord noc + 1h extra noc'
        if is_late:
            nota = f'Tardío + {nota}'
        return _con_acuerdo(re_m, nota, turno_h)
    else:
        entry_count = re_m + LATE_PENALTY if is_late else re_m
        if exit_m <= entry_count:
            exit_m += 24 * 60
        return _sin_acuerdo(entry_count, exit_m, turno_h, nota_fer,
                             es_confianza, is_late, re_m, entry_str, entry_m)


def _lizanias(entry_m: int, exit_m: int, nota_fer: str) -> dict:
    """
    Lizanias (ID 48) — jornada flexible Art. 135-138.
    Redondeo entrada/salida con regla 20/45.
    Ordinarias = min(real, límite de jornada).
    Extras = lo que sobra, clasificadas con split_hours.
    Si trabajó menos del límite, paga lo real.
    """
    # Ajuste overnight
    if exit_m <= entry_m:
        exit_m += 24 * 60

    # ── REDONDEO ENTRADA con regla 20/45 ─────────────────────
    rem = entry_m % 60
    if rem < 20:   entry_r = (entry_m // 60) * 60
    elif rem < 45: entry_r = (entry_m // 60) * 60 + 30
    else:          entry_r = (entry_m // 60 + 1) * 60

    # ── REDONDEO SALIDA con round_exit ───────────────────────
    sched_ref = entry_r + 8 * 60  # referencia para round_exit
    if exit_m <= entry_r:
        exit_m += 24 * 60
    exit_r = round_exit(exit_m, sched_ref)
    if exit_r <= entry_r:
        exit_r += 24 * 60

    total_min = exit_r - entry_r

    # Salida normalizada para clasificar jornada
    exit_norm = exit_r % 1440

    LIMITE_MIXTA = 19 * 60       # 19:00
    LIMITE_NOC   = 22 * 60 + 30  # 22:30

    # exit_norm == 0 significa medianoche exacta → nocturna
    if exit_norm == 0 or exit_norm > LIMITE_NOC:
        jornada    = 'Nocturna'
        limite_min = 6 * 60
    elif exit_norm > LIMITE_MIXTA:
        jornada    = 'Mixta'
        limite_min = 7 * 60
    else:
        jornada    = 'Diurna'
        limite_min = 8 * 60

    ord_min  = min(total_min, limite_min)
    over_min = total_min - ord_min

    d_o, mx_o, n_o = split_hours(entry_r, entry_r + ord_min)

    xd = xm = xn = 0.0
    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = entry_r + ord_min
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))

    nota = nota_fer if nota_fer else f'Lizanias flexible — {jornada}'

    return {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': f'Lizanias {jornada}',
        'nota': nota,
        'entry_red': m2t(entry_r),
        'exit_red':  m2t(exit_r % 1440),
    }


def _con_acuerdo(re_m: int, nota: str, turno_h: int) -> dict:
    """6h ordinarias nocturnas + 1h extra nocturna fija."""
    d_o, mx_o, n_o = ACUERDO_ORD.get(turno_h, (0.0, 0.0, 6.0))

    if not nota:
        nota = 'Acuerdo Seg: 6h ord noc + 1h extra noc'

    return {
        'diu_o': d_o, 'mix_o': mx_o, 'noc_o': n_o,
        'xd': 0.0, 'xm': 0.0, 'xn': 1.0,
        'status': 'Con Acuerdo', 'nota': nota,
        'entry_red': m2t(re_m),
        'exit_red':  m2t((re_m + 7 * 60) % 1440),
    }


def _sin_acuerdo(entry_count: int, exit_m: int, turno_h: int,
                 nota_fer: str, es_confianza: bool,
                 is_late: bool = False, re_m: int = None,
                 entry_str: str = '', entry_m_real: int = None) -> dict:
    """8h ordinarias + regla 20/45."""
    ord_h     = ORD_HOURS_DEFAULT
    sched_end = entry_count + ord_h * 60
    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    total_min    = exit_rounded - entry_count
    over_min     = total_min - ord_h * 60
    actual_ord   = min(total_min, ord_h * 60)

    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)

    xd = xm = xn = 0.0

    if not es_confianza:
        early_min = max(0, re_m - entry_m_real) if re_m is not None and entry_m_real is not None and not is_late else 0
        if early_min >= 25:
            xd = r2(xd + calc_early(early_min))

        if over_min >= EXTRA_HALF_MIN:
            xh = calc_extra(over_min)
            if xh > 0:
                xs = sched_end
                xd2, xm2, xn2 = split_hours(xs, xs + int(xh * 60))
                xd = r2(xd + xd2)
                xm = r2(xm + xm2)
                xn = r2(xn + xn2)

    has_extra  = xd + xm + xn > 0
    late_label = 'Tardío' if is_late else 'OK'
    status     = late_label + (' +Extra' if has_extra else '')

    if nota_fer:
        nota = nota_fer
    elif is_late and re_m is not None:
        nota = f'Tardío: llegó {entry_str}, cuenta desde {m2t(entry_count)}'
    else:
        nota = ''

    return {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': status, 'nota': nota,
        'entry_red': m2t(entry_count),
        'exit_red':  m2t(exit_rounded % 1440),
    }
