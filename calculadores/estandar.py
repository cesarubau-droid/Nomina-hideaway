# ============================================================
# CALCULADOR ESTÁNDAR — v4.0
# Aplica a: Ama de Llaves, Spa, Jardín, Mantenimiento,
#           RH, Proveeduría
# Regla: turno más cercano + 8h ord + regla 20/45
# Confianza: nunca extras
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours, nearest_shift,
    round_exit, calc_extra, clean_punches, empty, es_feriado
)
from config import (
    DEPT_STARTS, TOLERANCE_MIN, LATE_PENALTY,
    ORD_HOURS_DEFAULT, EXTRA_HALF_MIN
)


def calcular(fecha: str, punches_raw: list, dept: str,
             es_nocturno: bool = False, exit_str: str = None,
             es_confianza: bool = False) -> dict:
    """
    Calcula horas para departamentos estándar.

    Args:
        fecha:        'YYYY-MM-DD'
        punches_raw:  lista ['HH:MM', ...] — solo Check In / Check Out
        dept:         departamento interno
        es_nocturno:  True si el turno cruzó medianoche
        exit_str:     hora de salida del día siguiente (solo si es_nocturno)
        es_confianza: si es True, nunca se calculan extras
    """
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''
    starts   = DEPT_STARTS.get(dept, [8])
    ord_h    = ORD_HOURS_DEFAULT

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

    # Turno nocturno cruzado
    if es_nocturno and exit_str:
        exit_m  = t2m(exit_str)
        if exit_m <= entry_m:
            exit_m += 24 * 60
        re_m, _ = nearest_shift(entry_m, starts)
        return _calcular_turno(
            re_m, re_m, exit_m, ord_h, nota_fer,
            es_confianza, is_late=False, entry_str=entry_str
        )

    # Turno normal
    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    exit_m       = t2m(punches[-1])
    re_m, diff   = nearest_shift(entry_m, starts)
    is_late      = diff > TOLERANCE_MIN
    entry_count  = re_m + LATE_PENALTY if is_late else re_m

    if exit_m <= entry_count:
        exit_m += 24 * 60

    return _calcular_turno(
        re_m, entry_count, exit_m, ord_h, nota_fer,
        es_confianza, is_late, entry_str
    )


def _calcular_turno(re_m: int, entry_count: int, exit_m: int,
                    ord_h: int, nota_fer: str, es_confianza: bool,
                    is_late: bool, entry_str: str) -> dict:

    sched_end    = entry_count + ord_h * 60
    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    total_min  = exit_rounded - entry_count
    over_min   = total_min - ord_h * 60

    # Confianza: todas las horas trabajadas son ordinarias, sin extras
    if es_confianza:
        actual_ord = total_min
    else:
        actual_ord = min(total_min, ord_h * 60)

    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)

    xd = xm = xn = 0
    if not es_confianza and over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = entry_count + ord_h * 60
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))

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
