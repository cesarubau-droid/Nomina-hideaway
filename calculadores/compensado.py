# ============================================================
# CALCULADOR COMPENSADO — v4.0
# Aplica a: Contabilidad, Sostenibilidad
# Turno único: 08:00-17:00 → 9h ordinarias
# Regla 20/45 para extras
# Llegada anticipada: 25min → 0.5h extra diurna
# Tolerancia: 10min | Siguiente turno si supera tolerancia
# Sin quebrados ni nocturnos
# Sin empleados de confianza
# Feriados: todas las horas se duplican
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours,
    round_exit, calc_extra, calc_early, clean_punches,
    empty, es_feriado, aplicar_feriado
)
from config import TOLERANCE_MIN, EXTRA_HALF_MIN, ORD_HOURS_COMPENSADO

TURNO_START = 8 * 60    # 08:00
TURNO_END   = 17 * 60   # 17:00
ORD_H       = ORD_HOURS_COMPENSADO  # 9h


def calcular(fecha: str, punches_raw: list, dept: str = '') -> dict:
    """
    Calcula horas para empleados de Contabilidad o Sostenibilidad.
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

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    exit_m = t2m(punches[-1])

    # Detección de turno — solo hay uno (08:00)
    diff = entry_m - TURNO_START
    if -TOLERANCE_MIN <= diff <= TOLERANCE_MIN:
        early_min = max(0, -diff)
        late_min  = max(0, diff)
    elif entry_m < TURNO_START:
        early_min = TURNO_START - entry_m
        late_min  = 0
    else:
        # Llegó tarde — siguiente turno = mismo (único turno)
        early_min = 0
        late_min  = diff

    is_late     = late_min > TOLERANCE_MIN
    entry_count = TURNO_START

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, TURNO_END)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    total_min  = exit_rounded - entry_count
    actual_ord = min(total_min, ORD_H * 60)
    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)
    over_min = max(0, exit_rounded - TURNO_END)

    xd = xm = xn = 0.0

    if early_min > 0 and not is_late:
        xd = r2(xd + calc_early(early_min))

    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = TURNO_END
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
