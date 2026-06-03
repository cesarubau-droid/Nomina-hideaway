# ============================================================
# CALCULADOR COMPENSADO — v4.1
# Aplica a: Contabilidad, Sostenibilidad
# Turno base: 08:00-17:00 → 9h ordinarias
# Turno flexible: si entrada >= 60min después de las 08:00
#   → cuenta desde entrada redondeada, horas exactas trabajadas
# Regla 20/45 para extras por salida tardía
# Tolerancia: 10min
# Feriados: todas las horas se duplican
# ============================================================
from calculador_base import (
    t2m, m2t, r2, split_hours,
    round_exit, calc_extra, calc_early, clean_punches,
    empty, es_feriado, aplicar_feriado
)
from config import TOLERANCE_MIN, LATE_PENALTY, EXTRA_HALF_MIN, ORD_HOURS_COMPENSADO

TURNO_START = 8 * 60    # 08:00
TURNO_END   = 17 * 60   # 17:00
ORD_H       = ORD_HOURS_COMPENSADO  # 9h


def _redondear_entrada(entry_m: int) -> int:
    """Redondea entrada con regla 20/45 hacia adelante."""
    rem = entry_m % 60
    if rem < 20:   return (entry_m // 60) * 60
    elif rem < 45: return (entry_m // 60) * 60 + 30
    else:          return (entry_m // 60 + 1) * 60


def calcular(fecha: str, punches_raw: list, dept: str = '') -> dict:
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

    # Detección de turno
    diff      = entry_m - TURNO_START
    is_late   = diff > TOLERANCE_MIN
    early_min = max(0, -diff) if not is_late else 0
    late_min  = max(0, diff)  if is_late else 0

    # ── TURNO FLEXIBLE ───────────────────────────────────────
    # Si llegó 60min o más tarde → cuenta desde entrada redondeada
    if late_min >= 60:
        entry_count = _redondear_entrada(entry_m)
        sched_end   = entry_count + ORD_H * 60

        if exit_m <= entry_count:
            exit_m += 24 * 60

        exit_rounded = round_exit(exit_m, sched_end)
        if exit_rounded <= entry_count:
            exit_rounded += 24 * 60

        total_min  = exit_rounded - entry_count
        actual_ord = min(total_min, ORD_H * 60)
        d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)
        over_min = max(0, exit_rounded - sched_end)

        xd = xm = xn = 0.0
        if over_min >= EXTRA_HALF_MIN:
            xh = calc_extra(over_min)
            if xh > 0:
                xd2, xm2, xn2 = split_hours(sched_end, sched_end + int(xh * 60))
                xd = r2(xd + xd2)
                xm = r2(xm + xm2)
                xn = r2(xn + xn2)

        nota = nota_fer if nota_fer else f'Turno flexible desde {m2t(entry_count)}'
        res = {
            'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
            'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
            'status': 'Flexible' + (' +Extra' if xd+xm+xn > 0 else ''),
            'nota': nota,
            'entry_red': m2t(entry_count),
            'exit_red':  m2t(exit_rounded % 1440),
        }
        return aplicar_feriado(res, fecha)

    # ── TURNO NORMAL ─────────────────────────────────────────
    entry_count = TURNO_START + LATE_PENALTY if is_late else TURNO_START

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
