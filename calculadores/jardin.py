# ============================================================
# CALCULADOR JARDÍN — v4.0
# Turnos: 6AM-2PM, 7AM-3PM, 8AM-4PM
# 8h ordinarias + regla 20/45
# Llegada anticipada: 25min → 0.5h extra diurna
# Tolerancia: 10min | Penalización tardío: 30min
# Sin quebrados ni nocturnos
# Sin empleados de confianza
# Feriados: todas las horas se duplican
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours,
    round_exit, calc_extra, calc_early, clean_punches,
    empty, es_feriado, aplicar_feriado
)
from config import DEPT_STARTS, TOLERANCE_MIN, LATE_PENALTY, EXTRA_HALF_MIN

DEPT      = 'JARDIN'
STARTS    = DEPT_STARTS[DEPT]   # [6, 7, 8]
ORD_H     = 8

# Fin programado por turno
TURNO_FIN = {
    6:  14 * 60,   # 06:00 → 14:00
    7:  15 * 60,   # 07:00 → 15:00
    8:  16 * 60,   # 08:00 → 16:00
    15: 22 * 60,   # 15:00 → 22:00 (7h, turno especial)
    22: 30 * 60,   # 22:00 → 06:00 (siguiente día)
}

# Horas ordinarias por turno
TURNO_ORD = {
    6:  8,
    7:  8,
    8:  8,
    15: 7,
    22: 6,  # nocturno
}

# Turno nocturno: 22:00-06:00
NOCTURNO_START = 22 * 60   # 22:00
NOCTURNO_ORD_H = 6         # 6h ordinarias
NOCTURNO_XN    = 2.0       # 2h extra nocturna fija

STARTS_SORTED = sorted(h for h in TURNO_FIN.keys() if h != 22)  # excluye nocturno


def detect_turno(entry_m: int, exit_m: int) -> tuple:
    """
    Detecta el turno usando entrada y salida:
    1. Dentro de tolerancia antes o después → ese turno
    2. Antes del primer turno → anticipada al primero
    3. Superó tolerancia → turno cuyo fin programado
       esté más cerca de la salida real
    Retorna (turno_h, early_min, late_min).
    """
    # 1. Dentro de tolerancia
    for h in STARTS_SORTED:
        turno_m = h * 60
        diff    = entry_m - turno_m
        if -TOLERANCE_MIN <= diff <= TOLERANCE_MIN:
            if diff <= 0:
                return h, 0, 0
            else:
                return h, 0, diff

    # 2. Antes del primer turno → anticipada
    if entry_m < STARTS_SORTED[0] * 60:
        early_min = STARTS_SORTED[0] * 60 - entry_m
        return STARTS_SORTED[0], early_min, 0

    # 3. Usar salida para desempatar — turno con fin más cercano a exit_m
    if exit_m <= entry_m:
        exit_m += 24 * 60

    best_h    = STARTS_SORTED[0]
    best_diff = 999999
    for h in STARTS_SORTED:
        fin_m = TURNO_FIN[h]
        fin_adj = fin_m if fin_m >= entry_m else fin_m + 24 * 60
        diff = abs(exit_m - fin_adj)
        if diff < best_diff:
            best_diff = diff
            best_h    = h

    re_m     = best_h * 60
    early_min = max(0, re_m - entry_m)
    late_min  = max(0, entry_m - re_m)
    return best_h, early_min, late_min


def calcular(fecha: str, punches_raw: list) -> dict:
    """
    Calcula horas para un empleado de Jardín.

    Args:
        fecha:       'YYYY-MM-DD'
        punches_raw: lista ['HH:MM', ...] — Check In / Check Out
    """
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    # ── TURNO NOCTURNO 22:00-06:00 ───────────────────────────
    # Detectar ANTES del sort: si algún punch es >= 21:50
    raw_mins = [t2m(p) for p in punches_raw if p]
    has_nocturno_entry = any(m >= NOCTURNO_START - TOLERANCE_MIN for m in raw_mins)
    has_early_exit     = any(m <= 6 * 60 + 30 for m in raw_mins)

    if has_nocturno_entry and has_early_exit:
        # Es turno nocturno — tomar el punch >= 21:50 como entrada
        # y el punch <= 06:30 como salida
        entry_noc = max(m for m in raw_mins if m >= NOCTURNO_START - TOLERANCE_MIN)
        exit_noc  = min(m for m in raw_mins if m <= 6 * 60 + 30)
        from calculador_base import m2t as _m2t
        entry_str_noc = _m2t(entry_noc)
        res = _calcular_nocturno(fecha, entry_noc, exit_noc + 24*60,
                                 entry_str_noc, nota_fer)
        return aplicar_feriado(res, fecha)

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    exit_m = t2m(punches[-1])

    turno_h, early_min, late_min = detect_turno(entry_m, exit_m)
    sched_end = TURNO_FIN.get(turno_h, 16 * 60)
    ord_h     = TURNO_ORD.get(turno_h, ORD_H)

    is_late     = late_min > TOLERANCE_MIN
    entry_count = turno_h * 60 + LATE_PENALTY if is_late else turno_h * 60

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    actual_ord = ord_h * 60
    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)

    over_min = max(0, exit_rounded - sched_end)


    xd = xm = xn = 0.0

    # Extra por llegada anticipada (diurna)
    if early_min > 0 and not is_late:
        xd = r2(xd + calc_early(early_min))

    # Extra por salida tardía (regla 20/45)
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
    elif is_late:
        nota = f'Tardío: llegó {entry_str}, cuenta desde {m2t(entry_count)}'
    else:
        nota = ''

    res = {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': status, 'nota': nota,
        'entry_red': m2t(entry_count),
        'exit_red':  m2t(exit_rounded % 1440),
    }
    return aplicar_feriado(res, fecha)


def _calcular_nocturno(fecha: str, entry_m: int, exit_m: int,
                       entry_str: str, nota_fer: str) -> dict:
    """
    Turno nocturno 22:00-06:00:
    6h ordinarias (0.5h mixta + 5.5h nocturna) + 2h extra nocturna fija.
    """
    re_m   = NOCTURNO_START        # 22:00 = 1320
    ord_end = re_m + NOCTURNO_ORD_H * 60  # 22:00 + 6h = 28:00 (1680)
    sched_end = 30 * 60            # 06:00 siguiente día = 1800

    if exit_m <= entry_m:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)

    d_o, mx_o, n_o = split_hours(re_m, ord_end)

    # Extra nocturna fija: 2h
    # El turno 22:00-06:00 tiene 6h ord + 2h extra
    # Las 2h extra son siempre nocturnas (caen dentro de 22:30-05:00)
    xd = 0.0
    xm = 0.0
    xn = NOCTURNO_XN

    # Extra adicional por salida tardía
    over_min = max(0, exit_rounded - sched_end)

    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs2 = sched_end
            xd2, xm2, xn2 = split_hours(xs2, xs2 + int(xh * 60))
            xd = r2(xd + xd2)
            xm = r2(xm + xm2)
            xn = r2(xn + xn2)

    nota = nota_fer if nota_fer else 'Nocturno: 6h ord + 2h extra noc'
    has_extra = xd + xm + xn > 0

    return {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': 'Nocturno' + (' +Extra' if has_extra else ''),
        'nota': nota,
        'entry_red': m2t(re_m),
        'exit_red':  m2t(sched_end % 1440),
    }
