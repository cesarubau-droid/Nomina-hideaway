# ============================================================
# CALCULADOR RESTAURANTE SALON — v4.0
# Turnos y reglas fijas:
#   T1: 06:00-15:00 → 8h ord + 1h extra diurna
#   T2: 06:00-14:00 / 18:00-22:00 (quebrado) → 8h ord + 4h extra
#   T3: 07:00-15:00 → 8h ord
#   T4: 11:00-22:00 → 8h ord + 0.5h xd + 2.5h xm
#   T5: 12:00-22:00 → 8h ord + 2h xm
#   T6: 14:00-22:00 → 8h ord
#   T7: 15:00-22:00 → 7h ord
# Regla 20/45 para extras adicionales por salida tardía
# Llegada anticipada: 25min → 0.5h extra diurna
# Feriados: todas las horas se duplican
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours, nearest_shift,
    round_exit, calc_extra, calc_early, clean_punches,
    empty, es_feriado, aplicar_feriado
)
from config import TOLERANCE_MIN, LATE_PENALTY, EXTRA_HALF_MIN

# Turnos: inicio → (fin, ord_h, xd_fija, xm_fija, xn_fija)
TURNOS = {
    6:  (15 * 60, 8, 1.0, 0.0, 0.0),   # T1: 06-15
    7:  (15 * 60, 8, 0.0, 0.0, 0.0),   # T3: 07-15
    11: (22 * 60, 8, 0.5, 2.5, 0.0),   # T4: 11-22
    12: (22 * 60, 8, 0.0, 2.0, 0.0),   # T5: 12-22
    14: (22 * 60, 8, 0.0, 0.0, 0.0),   # T6: 14-22
    15: (22 * 60, 7, 0.0, 0.0, 0.0),   # T7: 15-22
}

# Turno quebrado T2
T2_ENTRY1 = 6 * 60   # 06:00
T2_EXIT1  = 14 * 60  # 14:00
T2_ENTRY2 = 18 * 60  # 18:00
T2_EXIT2  = 22 * 60  # 22:00

# Gap mínimo para turno quebrado: 3h30min
QUEBRADO_GAP = 210

# Starts para detect_turno
STARTS_SORTED = sorted(TURNOS.keys())


def detect_turno(entry_m: int) -> tuple:
    """
    Detecta el turno:
    1. Si está dentro de tolerancia ANTES del turno → anticipada
    2. Si está dentro de tolerancia DESPUÉS del turno → tardío normal
    3. Si llegó antes del primer turno → anticipada al primero
    4. Si superó la tolerancia → turno anterior como tardío
    Retorna (turno_h, early_min, late_min).
    """
    # 1 y 2. Dentro de tolerancia de algún turno (antes o después)
    for h in STARTS_SORTED:
        turno_m = h * 60
        diff    = entry_m - turno_m  # positivo=tarde, negativo=anticipado
        if -TOLERANCE_MIN <= diff <= TOLERANCE_MIN:
            if diff <= 0:
                # Llegó anticipado dentro de tolerancia → no cuenta como extra
                return h, 0, 0
            else:
                # Llegó tarde dentro de tolerancia → sin penalización
                return h, 0, diff

    # 3. Antes del primer turno → anticipada
    if entry_m < STARTS_SORTED[0] * 60:
        early_min = STARTS_SORTED[0] * 60 - entry_m
        return STARTS_SORTED[0], early_min, 0

    # 4. Superó la tolerancia → turno anterior más cercano como tardío
    best_h    = STARTS_SORTED[0]
    best_diff = 999999
    for h in STARTS_SORTED:
        turno_m = h * 60
        if turno_m <= entry_m:
            diff = entry_m - turno_m
            if diff < best_diff:
                best_diff = diff
                best_h    = h

    return best_h, 0, best_diff


def calcular(fecha: str, punches_raw: list,
             es_nocturno: bool = False, exit_str: str = None,
             es_confianza: bool = False) -> dict:
    """
    Calcula horas para un empleado de Restaurante Salón.
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
        exit_m = t2m(exit_str)
        if exit_m <= entry_m:
            exit_m += 24 * 60
        turno_h, early_min, late_min = detect_turno(entry_m)
        res = _calcular_turno(
            fecha, turno_h, entry_m, exit_m,
            early_min, late_min, entry_str, es_confianza
        )
        return aplicar_feriado(res, fecha)

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str}',
                     entry_red=entry_str, exit_red='?')

    # ── DETECCIÓN TURNO QUEBRADO ─────────────────────────────
    punch_mins = [t2m(p) for p in punches]
    is_split, split_idx = _detect_split(punch_mins)

    if is_split:
        res = _calcular_quebrado(fecha, punches, punch_mins,
                                 split_idx, es_confianza)
        return aplicar_feriado(res, fecha)

    # ── TURNO NORMAL ─────────────────────────────────────────
    exit_m = t2m(punches[-1])
    turno_h, early_min, late_min = detect_turno(entry_m)
    res = _calcular_turno(
        fecha, turno_h, entry_m, exit_m,
        early_min, late_min, entry_str, es_confianza
    )
    return aplicar_feriado(res, fecha)


def _detect_split(punch_mins: list) -> tuple:
    """
    4 punches → quebrado si gap entre idx 1 y 2 >= 3h30min
    3 punches → quebrado si gap más grande >= 3h30min
    2 punches → normal
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


def _calcular_turno(fecha, turno_h, entry_m, exit_m,
                    early_min, late_min, entry_str,
                    es_confianza) -> dict:
    """
    Calcula turno normal con reglas fijas por turno.
    - Las extras fijas (xd_fija, xm_fija, xn_fija) son parte del turno
    - over_min se calcula desde entry_count + ord_h (fin ordinario)
    - sched_end se usa solo para round_exit
    """
    turno_data = TURNOS.get(turno_h)
    if not turno_data:
        turno_data = (22 * 60, 8, 0.0, 0.0, 0.0)

    sched_end, ord_h, xd_fija, xm_fija, xn_fija = turno_data

    is_late     = late_min > TOLERANCE_MIN
    entry_count = (turno_h * 60) + LATE_PENALTY if is_late else turno_h * 60

    if exit_m <= entry_count:
        exit_m += 24 * 60

    # Redondear salida contra el fin del turno completo (incluyendo extras fijas)
    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    # Ordinarias: desde entry_count hasta entry_count + ord_h
    ord_end    = entry_count + ord_h * 60
    actual_ord = ord_h * 60
    d_o, mx_o, n_o = split_hours(entry_count, ord_end)

    # Over = minutos más allá del fin del turno completo (sched_end)
    # Si exit_rounded > sched_end → salió más tarde que el turno completo
    over_min = max(0, exit_rounded - sched_end)

    # Extras fijas del turno
    xd = xd_fija
    xm = xm_fija
    xn = xn_fija

    # Extra por llegada anticipada (diurna, solo si no tardío ni confianza)
    if early_min > 0 and not is_late and not es_confianza:
        xd = r2(xd + calc_early(early_min))

    # Extra adicional por salida más allá del turno completo
    if not es_confianza and over_min >= EXTRA_HALF_MIN:
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

    is_fer, fer_name = es_feriado(fecha)
    if is_fer:
        nota = f'★ Feriado: {fer_name}'
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


def _calcular_quebrado(fecha, punches, punch_mins,
                       split_idx, es_confianza) -> dict:
    """Calcula turno quebrado T2: 06:00-14:00 / 18:00-22:00."""

    b1_mins = punch_mins[:split_idx + 1]
    b2_mins = punch_mins[split_idx + 1:]

    entry1_m = b1_mins[0]
    exit1_m  = b1_mins[-1]
    entry2_m = b2_mins[0]
    exit2_m  = b2_mins[-1]

    # B1: turno 06:00-14:00
    re1      = T2_ENTRY1
    diff1    = entry1_m - re1
    is_late  = diff1 > TOLERANCE_MIN
    entry1_c = re1 + LATE_PENALTY if is_late else re1
    early1   = max(0, re1 - entry1_m) if not is_late else 0

    if exit1_m <= entry1_c:
        exit1_m += 24 * 60

    exit1_rem = exit1_m % 60
    if exit1_rem >= 45:
        exit1_r = (exit1_m // 60 + 1) * 60
    elif exit1_rem >= 20:
        exit1_r = (exit1_m // 60) * 60 + 30
    else:
        exit1_r = (exit1_m // 60) * 60

    # B2: turno 18:00-22:00
    re2     = T2_ENTRY2
    if exit2_m <= re2:
        exit2_m += 24 * 60
    exit2_r = round_exit(exit2_m, T2_EXIT2)

    # Horas
    h1 = (exit1_r - entry1_c) / 60
    h2 = (exit2_r - re2) / 60
    if h1 < 0: h1 += 24
    if h2 < 0: h2 += 24

    total    = h1 + h2
    ord_h    = 8
    over_min = round((total - ord_h) * 60)

    ord_b1 = min(h1, ord_h)
    ord_b2 = min(h2, max(0.0, ord_h - ord_b1))

    d1, mx1, n1 = split_hours(entry1_c, entry1_c + int(ord_b1 * 60))
    d2, mx2, n2 = split_hours(re2,      re2       + int(ord_b2 * 60))

    diu_o = r2(d1 + d2)
    mix_o = r2(mx1 + mx2)
    noc_o = r2(n1 + n2)

    # Extras fijas T2: 4h (clasificadas por hora)
    xs_start = re2 + int(ord_b2 * 60)
    xd_fija, xm_fija, xn_fija = split_hours(xs_start, xs_start + 4 * 60)

    xd = xd_fija
    xm = xm_fija
    xn = xn_fija

    # Extra por llegada anticipada B1
    if early1 > 0 and not es_confianza:
        xd = r2(xd + calc_early(early1))

    # Extra adicional por salida tardía (regla 20/45)
    if not es_confianza and over_min > 0:
        extra_adicional = over_min - 4 * 60  # ya contamos 4h fijas
        if extra_adicional >= EXTRA_HALF_MIN:
            xh = calc_extra(extra_adicional)
            if xh > 0:
                xs2 = xs_start + 4 * 60
                xd2, xm2, xn2 = split_hours(xs2, xs2 + int(xh * 60))
                xd = r2(xd + xd2)
                xm = r2(xm + xm2)
                xn = r2(xn + xn2)

    is_fer, fer_name = es_feriado(fecha)
    nota = f'★ Feriado: {fer_name}' if is_fer else (
        f'Quebrado B1:{m2t(entry1_c)}-{m2t(exit1_r % 1440)} '
        f'+ B2:{m2t(re2)}-{m2t(exit2_r % 1440)} = {r2(total)}h'
    )
    if is_late and not is_fer:
        nota = 'Tardío B1. ' + nota

    return {
        'diu_o': diu_o, 'mix_o': mix_o, 'noc_o': noc_o,
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': 'Quebrado' + (' +Extra' if xd + xm + xn > 0 else ''),
        'nota': nota,
        'entry_red': f'{m2t(entry1_c)}/{m2t(re2)}',
        'exit_red':  f'{m2t(exit1_r % 1440)}/{m2t(exit2_r % 1440)}',
    }
