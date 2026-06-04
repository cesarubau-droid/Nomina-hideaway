# ============================================================
# CALCULADOR SEGURIDAD — v4.1
# Reglas:
#   Con Acuerdo (16, 22, 23h): 6h ord noc + 1h extra noc fija
#   Sin Acuerdo (6, 8, 15h): 8h ord + regla 20/45
#   Turno 6h sin acuerdo: 8h ord + 1h extra noc fija
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

# Ordinarias hardcodeadas por turno con acuerdo (todo nocturno)
# turno_h → (diu_o, mix_o, noc_o)
ACUERDO_ORD = {
    16: (0.0, 0.0, 6.0),   # 16→22: 6h noc
    22: (0.0, 0.0, 6.0),   # 22→05: 6h noc
    23: (0.0, 0.0, 6.0),   # 23→06: 6h noc
}


def calcular(fecha: str, punches_raw: list, es_nocturno: bool = False,
             exit_str: str = None, es_confianza: bool = False) -> dict:
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

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


def _con_acuerdo(re_m: int, nota: str, turno_h: int) -> dict:
    """6h ordinarias nocturnas + 1h extra nocturna fija."""
    # Ordinarias hardcodeadas como nocturnas
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
        # Llegada anticipada → extra diurna
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
