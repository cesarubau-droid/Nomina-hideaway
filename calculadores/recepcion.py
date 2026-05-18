# ============================================================
# CALCULADOR RECEPCIÓN — v4.0
# Turnos:
#   06:00-15:00 → 8h ordinarias
#   08:00-16:00 → 8h ordinarias
#   09:00-17:00 → 8h ordinarias
#   15:00-22:00 → 7h ordinarias
#   22:00-06:00 → 6h ordinarias + 2h extra noc fija
# Regla 20/45 para extras adicionales
# Llegada anticipada: 25min → 0.5h extra diurna
# Tolerancia: 10min | Siguiente turno si supera tolerancia
# Sin quebrados
# Confianza: Tania Rodriguez (ID 25) — nunca extras
# Feriados: todas las horas se duplican
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours,
    round_exit, calc_extra, calc_early, clean_punches,
    empty, es_feriado, aplicar_feriado
)
from config import TOLERANCE_MIN, LATE_PENALTY, EXTRA_HALF_MIN

# Turnos: inicio → (fin, ord_h, xd_fija, xm_fija, xn_fija)
TURNOS = {
    6:  (15 * 60, 8, 1.0, 0.0, 0.0),   # 06:00 → 15:00 (8h ord + 1h xd fija)
    8:  (16 * 60, 8, 0.0, 0.0, 0.0),   # 08:00 → 16:00 (8h ord)
    9:  (17 * 60, 8, 0.0, 0.0, 0.0),   # 09:00 → 17:00 (8h ord)
    15: (22 * 60, 7, 0.0, 0.0, 0.0),   # 15:00 → 22:00 (7h ord)
}

# Turno nocturno
NOCTURNO_START = 22 * 60   # 22:00
NOCTURNO_ORD_H = 6
NOCTURNO_XN    = 2.0
NOCTURNO_END   = 30 * 60   # 06:00 siguiente día

STARTS_SORTED = sorted(TURNOS.keys())

# Empleados de confianza (sin extras)
CONFIANZA_IDS = {25}  # Tania Rodriguez


def detect_turno(entry_m: int) -> tuple:
    """
    Detecta el turno:
    1. Dentro de tolerancia (+-10min) → ese turno
    2. Antes del primer turno → anticipada al primero
    3. Superó tolerancia → primer turno >= entrada (siguiente turno)
    Retorna (turno_h, early_min, late_min).
    """
    for h in STARTS_SORTED:
        turno_m = h * 60
        diff    = entry_m - turno_m
        if -TOLERANCE_MIN <= diff <= TOLERANCE_MIN:
            if diff <= 0:
                return h, 0, 0
            else:
                return h, 0, diff

    if entry_m < STARTS_SORTED[0] * 60:
        early_min = STARTS_SORTED[0] * 60 - entry_m
        return STARTS_SORTED[0], early_min, 0

    for h in STARTS_SORTED:
        if h * 60 >= entry_m:
            return h, 0, 0

    last_h = STARTS_SORTED[-1]
    return last_h, 0, entry_m - last_h * 60


def calcular(fecha: str, punches_raw: list,
             es_nocturno: bool = False, exit_str: str = None,
             es_confianza: bool = False) -> dict:
    """
    Calcula horas para un empleado de Recepción.
    """
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    # Nocturno desde procesador
    if es_nocturno and exit_str:
        entry_m = t2m(punches_raw[0]) if punches_raw else NOCTURNO_START
        exit_m  = t2m(exit_str) + 24 * 60
        res = _calcular_nocturno(fecha, entry_m, exit_m,
                                 punches_raw[0] if punches_raw else m2t(NOCTURNO_START),
                                 nota_fer, es_confianza)
        return aplicar_feriado(res, fecha)

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    # Detección nocturno interno
    raw_mins = [t2m(p) for p in punches_raw if p]
    has_noc_entry = any(m >= NOCTURNO_START - TOLERANCE_MIN for m in raw_mins)
    has_early_exit = any(m <= 6 * 60 + 30 for m in raw_mins)

    if has_noc_entry and has_early_exit:
        entry_noc = max(m for m in raw_mins if m >= NOCTURNO_START - TOLERANCE_MIN)
        exit_noc  = min(m for m in raw_mins if m <= 6 * 60 + 30)
        res = _calcular_nocturno(fecha, entry_noc, exit_noc + 24 * 60,
                                 m2t(entry_noc), nota_fer, es_confianza)
        return aplicar_feriado(res, fecha)

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    exit_m = t2m(punches[-1])
    turno_h, early_min, late_min = detect_turno(entry_m)
    sched_end, ord_h, xd_fija, xm_fija, xn_fija = TURNOS.get(turno_h, (22 * 60, 7, 0.0, 0.0, 0.0))

    is_late     = late_min > TOLERANCE_MIN
    entry_count = turno_h * 60 + LATE_PENALTY if is_late else turno_h * 60

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    d_o, mx_o, n_o = split_hours(entry_count, entry_count + ord_h * 60)

    over_min = max(0, exit_rounded - sched_end)

    # Extras fijas del turno
    xd = xd_fija
    xm = xm_fija
    xn = xn_fija

    if not es_confianza:
        # Extra por llegada anticipada (diurna)
        if early_min > 0 and not is_late:
            xd = r2(xd + calc_early(early_min))

        # Extra adicional por salida más allá del turno completo
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
                       entry_str: str, nota_fer: str,
                       es_confianza: bool) -> dict:
    """Turno nocturno 22:00-06:00: 6h ord + 2h extra noc fija."""
    re_m    = NOCTURNO_START
    ord_end = re_m + NOCTURNO_ORD_H * 60

    d_o, mx_o, n_o = split_hours(re_m, ord_end)

    xd = 0.0
    xm = 0.0
    xn = NOCTURNO_XN if not es_confianza else 0.0

    over_min = max(0, exit_m - NOCTURNO_END)
    if not es_confianza and over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = NOCTURNO_END
            xd2, xm2, xn2 = split_hours(xs, xs + int(xh * 60))
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
        'exit_red':  m2t(NOCTURNO_END % 1440),
    }
