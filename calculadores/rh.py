# ============================================================
# CALCULADOR RH — v4.1
# Turnos:
#   06:00-14:00 → 8h ordinarias
#   07:00-15:00 → 8h ordinarias
#   08:00-16:00 → 8h ordinarias
# Regla 20/45 para extras
# Llegada anticipada: 25min → 0.5h extra diurna
# Tolerancia: 10min | Tardío suma 30min al entry_count
# Sin quebrados ni nocturnos
# Feriados: todas las horas se duplican
# Fix v4.1: entry_count ahora suma LATE_PENALTY cuando es tardío
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours,
    round_exit, calc_extra, calc_early, clean_punches,
    empty, es_feriado, aplicar_feriado
)
from config import TOLERANCE_MIN, LATE_PENALTY, EXTRA_HALF_MIN

TURNOS = {
    6:  (14 * 60, 8),   # 06:00 → 14:00
    7:  (15 * 60, 8),   # 07:00 → 15:00
    8:  (16 * 60, 8),   # 08:00 → 16:00
}

STARTS_SORTED = sorted(TURNOS.keys())


def detect_turno(entry_m: int) -> tuple:
    for h in STARTS_SORTED:
        turno_m = h * 60
        diff    = entry_m - turno_m
        if -TOLERANCE_MIN <= diff <= TOLERANCE_MIN:
            return h, 0, 0 if diff <= 0 else diff

    if entry_m < STARTS_SORTED[0] * 60:
        return STARTS_SORTED[0], STARTS_SORTED[0] * 60 - entry_m, 0

    for h in STARTS_SORTED:
        if h * 60 >= entry_m:
            return h, 0, 0

    last_h = STARTS_SORTED[-1]
    return last_h, 0, entry_m - last_h * 60


def calcular(fecha: str, punches_raw: list) -> dict:
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    exit_m = t2m(punches[-1])
    turno_h, early_min, late_min = detect_turno(entry_m)
    sched_end, ord_h = TURNOS.get(turno_h, (16 * 60, 8))

    is_late     = late_min > TOLERANCE_MIN
    entry_count = turno_h * 60 + LATE_PENALTY if is_late else turno_h * 60  # ← fix

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    total_min  = exit_rounded - entry_count
    actual_ord = min(total_min, ord_h * 60)
    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)
    over_min = max(0, exit_rounded - sched_end)

    xd = xm = xn = 0.0

    if early_min > 0 and not is_late:
        xd = r2(xd + calc_early(early_min))

    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = sched_end
            xd2, xm2, xn2 = split_hours(xs, xs + int(xh * 60))
            xd = r2(xd + xd2)
            xm = r2(xm + xm2)
            xn = r2(xn + xn2)

    has_extra = xd + xm + xn > 0
    status    = ('OK' if not is_late else 'Tardío') + (' +Extra' if has_extra else '')

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
