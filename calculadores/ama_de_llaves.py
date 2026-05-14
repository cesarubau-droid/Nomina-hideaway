# ============================================================
# CALCULADOR AMA DE LLAVES — v4.0
# Turnos: 6, 7, 8h → 8h ordinarias
#         12, 14h  → 7h ordinarias
# Regla 20/45 para extras
# Tolerancia: 10min | Penalización tardío: 30min
# Turno quebrado: cuando hay Break Out/Break In con gap >= 3h30min
# Sin empleados de confianza
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours, nearest_shift,
    round_exit, calc_extra, calc_early, clean_punches, empty, es_feriado
)
from config import (
    DEPT_STARTS, TOLERANCE_MIN, LATE_PENALTY, EXTRA_HALF_MIN, SPLIT_GAP_MIN
)

DEPT   = 'AMA DE LLAVES'
STARTS = DEPT_STARTS[DEPT]  # [6, 7, 8, 12, 14]

# Horas ordinarias según turno de inicio
ORD_HORAS = {
    6:  8,
    7:  8,
    8:  8,
    12: 7,
    14: 7,
}

# Gap mínimo para considerar turno quebrado (3h30min)
QUEBRADO_GAP = 210

# Fin programado por turno (inicio + horas ordinarias)
TURNO_FIN = {
    6:  14 * 60,   # 06:00 → 14:00
    7:  15 * 60,   # 07:00 → 15:00
    8:  16 * 60,   # 08:00 → 16:00
    12: 19 * 60,   # 12:00 → 19:00
    14: 21 * 60,   # 14:00 → 21:00
}


def detect_turno(entry_m: int, exit_m: int) -> tuple:
    """
    Detecta el turno correcto usando la hora de salida como referencia.
    Compara exit_m con el fin programado de cada turno.
    Retorna (turno_inicio_minutos, early_min, late_min).
    - early_min > 0: llegó anticipado
    - late_min > 0:  llegó tarde
    """
    if exit_m <= entry_m:
        exit_m += 24 * 60

    best_turno = None
    best_diff  = 999999

    for h, fin_m in TURNO_FIN.items():
        # Ajustar si la salida cruza medianoche
        fin_adj = fin_m if fin_m >= entry_m else fin_m + 24 * 60
        diff = abs(exit_m - fin_adj)
        if diff < best_diff:
            best_diff  = diff
            best_turno = h

    re_m      = best_turno * 60
    early_min = max(0, re_m - entry_m)   # llegó antes del turno
    late_min  = max(0, entry_m - re_m)   # llegó después del turno
    return re_m, early_min, late_min


def calcular(fecha: str, punches_raw: list,
             es_nocturno: bool = False, exit_str: str = None) -> dict:
    """
    Calcula horas para un empleado de Ama de Llaves.

    Args:
        fecha:       'YYYY-MM-DD'
        punches_raw: lista ['HH:MM', ...] — todas las marcas del día
        es_nocturno: True si el turno cruzó medianoche
        exit_str:    hora de salida del día siguiente (solo si es_nocturno)
    """
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
        exit_m  = t2m(exit_str)
        if exit_m <= entry_m:
            exit_m += 24 * 60
        re_m, _, _ = detect_turno(entry_m, exit_m)
        turno_h    = re_m // 60
        ord_h      = ORD_HORAS.get(turno_h, 8)
        return _calcular_turno(
            re_m, re_m, exit_m, ord_h, nota_fer,
            is_late=False, entry_str=entry_str,
            early_min=0
        )

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    # ── DETECCIÓN DE TURNO QUEBRADO ──────────────────────────
    punch_mins = [t2m(p) for p in punches]
    is_split, split_idx = _detect_split(punch_mins)

    if is_split:
        return _calcular_quebrado(punches, punch_mins, split_idx, nota_fer)

    # ── TURNO NORMAL ─────────────────────────────────────────
    exit_m              = t2m(punches[-1])
    re_m, early_min, late_min = detect_turno(entry_m, exit_m)
    turno_h             = re_m // 60
    ord_h               = ORD_HORAS.get(turno_h, 8)
    is_late             = late_min > TOLERANCE_MIN
    entry_count         = re_m + LATE_PENALTY if is_late else re_m

    if exit_m <= entry_count:
        exit_m += 24 * 60

    return _calcular_turno(
        re_m, entry_count, exit_m, ord_h, nota_fer,
        is_late, entry_str,
        early_min=early_min
    )


def _detect_split(punch_mins: list) -> tuple:
    """
    Detecta turno quebrado:
    4 punches → quebrado si gap entre idx 1 y 2 >= 3h30min
    3 punches → quebrado si gap más grande >= 3h30min
    2 punches → turno normal
    """
    n = len(punch_mins)
    if n == 4:
        gap = punch_mins[2] - punch_mins[1]
        if gap >= QUEBRADO_GAP:
            return True, 1
    elif n == 3:
        gaps = [punch_mins[i+1] - punch_mins[i] for i in range(n-1)]
        max_idx = gaps.index(max(gaps))
        if gaps[max_idx] >= QUEBRADO_GAP:
            return True, max_idx
    return False, None


def _calcular_quebrado(punches, punch_mins, split_idx, nota_fer) -> dict:
    """Calcula turno quebrado B1 + B2."""

    b1_mins = punch_mins[:split_idx + 1]
    b2_mins = punch_mins[split_idx + 1:]

    entry1_m = b1_mins[0]
    exit1_m  = b1_mins[-1]
    entry2_m = b2_mins[0]
    exit2_m  = b2_mins[-1]

    re1, diff1 = nearest_shift(entry1_m, STARTS)
    re2, _     = nearest_shift(entry2_m, STARTS)

    turno_h1 = re1 // 60
    ord_h    = ORD_HORAS.get(turno_h1, 8)

    is_late      = diff1 > TOLERANCE_MIN
    entry1_count = re1 + LATE_PENALTY if is_late else re1

    if exit1_m <= entry1_count:
        exit1_m += 24 * 60
    if exit2_m <= re2:
        exit2_m += 24 * 60

    # Salida de B1 — redondeo simple
    exit1_rem = exit1_m % 60
    if exit1_rem >= 45:
        exit1_r = (exit1_m // 60 + 1) * 60
    elif exit1_rem >= 20:
        exit1_r = (exit1_m // 60) * 60 + 30
    else:
        exit1_r = (exit1_m // 60) * 60

    # Salida de B2 — contra las 22:00 o 23:00
    sched2  = 22 * 60
    exit2_r = round_exit(exit2_m, sched2)

    h1 = (exit1_r - entry1_count) / 60
    h2 = (exit2_r - re2) / 60
    if h1 < 0: h1 += 24
    if h2 < 0: h2 += 24

    total    = h1 + h2
    over_min = round((total - ord_h) * 60)

    ord_b1 = min(h1, ord_h)
    ord_b2 = min(h2, max(0.0, ord_h - ord_b1))

    d1, mx1, n1 = split_hours(entry1_count, entry1_count + int(ord_b1 * 60))
    d2, mx2, n2 = split_hours(re2,          re2          + int(ord_b2 * 60))

    diu_o = r2(d1 + d2)
    mix_o = r2(mx1 + mx2)
    noc_o = r2(n1 + n2)

    xd = xm = xn = 0.0
    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = re2 + int(ord_b2 * 60)
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))

    nota = nota_fer if nota_fer else (
        f'Quebrado B1:{m2t(entry1_count)}-{m2t(exit1_r % 1440)} '
        f'+ B2:{m2t(re2)}-{m2t(exit2_r % 1440)} = {r2(total)}h'
    )
    if is_late and not nota_fer:
        nota = 'Tardío B1. ' + nota

    return {
        'diu_o': diu_o, 'mix_o': mix_o, 'noc_o': noc_o,
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': 'Quebrado' + (' +Extra' if xd + xm + xn > 0 else ''),
        'nota': nota,
        'entry_red': f'{m2t(entry1_count)}/{m2t(re2)}',
        'exit_red':  f'{m2t(exit1_r % 1440)}/{m2t(exit2_r % 1440)}',
    }


def _calcular_turno(re_m: int, entry_count: int, exit_m: int,
                    ord_h: int, nota_fer: str,
                    is_late: bool, entry_str: str,
                    early_min: int = 0) -> dict:
    """Calcula turno normal con llegada anticipada."""

    sched_end    = entry_count + ord_h * 60
    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    total_min  = exit_rounded - entry_count
    over_min   = total_min - ord_h * 60
    actual_ord = min(total_min, ord_h * 60)

    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)

    xd = xm = xn = 0.0

    # Extras por llegada anticipada (siempre diurnas)
    if early_min > 0 and not is_late:
        xe = calc_early(early_min)
        xd = r2(xd + xe)

    # Extras por salida tardía (regla 20/45)
    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = entry_count + ord_h * 60
            xd2, xm2, xn2 = split_hours(xs, xs + int(xh * 60))
            xd = r2(xd + xd2)
            xm = r2(xm + xm2)
            xn = r2(xn + xn2)

    has_extra  = xd + xm + xn > 0
    late_label = 'Tardío' if is_late else 'OK'
    status     = late_label + (' +Extra' if has_extra else '')

    if nota_fer:
        nota = nota_fer
    elif is_late:
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
