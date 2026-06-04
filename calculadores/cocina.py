# ============================================================
# CALCULADOR ALIMENTOS COCINA — v1.1
# Turnos y reglas fijas (validadas con Andry):
#   T1: 06:00-15:00 → 8h ord + 1h xd fija
#   T2: 06:00-12:00 / 17:00-22:00 (quebrado) → 7h ord + 4h xm fija
#   T3: 12:00-22:00 → 7h ord + 3h xm fija
#   T4: 14:00-22:00 → 7h ord + 1h xm fija
#   T5: 15:00-22:00 → 7h ord
# Extras fijas siempre clasificadas como Andry indica:
#   T1 → xd | T2,T3,T4 → xm
# Salida tardía adicional → split_hours desde fin del turno
# Llegada anticipada → xd (regla 25min)
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
    6:  (15 * 60, 8, 1.0, 0.0, 0.0),   # T1: 06-15 → 8h ord + 1xd
    7:  (15 * 60, 8, 0.0, 0.0, 0.0),   # T6: 07-15 → 8h ord
    8:  (16 * 60, 8, 0.0, 0.0, 0.0),   # T8: 08-16 → 8h ord
    11: (22 * 60, 8, 0.0, 0.0, 0.0),   # T7: 11-22 → 8h ord
    12: (22 * 60, 7, 0.0, 3.0, 0.0),   # T3: 12-22 → 7h ord + 3xm
    14: (22 * 60, 7, 0.0, 1.0, 0.0),   # T4: 14-22 → 7h ord + 1xm
    15: (22 * 60, 7, 0.0, 0.0, 0.0),   # T5: 15-22 → 7h ord
}

# Turno quebrado T2
T2_ENTRY1  = 6  * 60   # 06:00
T2_EXIT1   = 12 * 60   # 12:00
T2_ENTRY2  = 17 * 60   # 17:00
T2_EXIT2   = 22 * 60   # 22:00
T2_ORD_H   = 7
T2_XM_FIJA = 4.0       # 4h extra mixtas fijas

# Gap mínimo para detectar turno quebrado: 3h
QUEBRADO_GAP = 180

STARTS_SORTED = sorted(TURNOS.keys())


def detect_turno(entry_m: int) -> tuple:
    """
    Detecta el turno al que corresponde una entrada.
    Retorna (turno_h, early_min, late_min).
    """
    # 1. Dentro de tolerancia (+-10min) → ese turno
    for h in STARTS_SORTED:
        turno_m = h * 60
        diff    = entry_m - turno_m
        if -TOLERANCE_MIN <= diff <= TOLERANCE_MIN:
            return h, 0, max(0, diff)

    # 2. Antes del primer turno → anticipada
    if entry_m < STARTS_SORTED[0] * 60:
        early_min = STARTS_SORTED[0] * 60 - entry_m
        return STARTS_SORTED[0], early_min, 0

    # 3. Fuera de tolerancia → turno más cercano
    best_h    = STARTS_SORTED[0]
    best_diff = 999999
    for h in STARTS_SORTED:
        diff = abs(entry_m - h * 60)
        if diff < best_diff:
            best_diff = diff
            best_h    = h
    late = entry_m - best_h * 60
    return best_h, 0, max(0, late)


def calcular(fecha: str, punches_raw: list,
             es_nocturno: bool = False, exit_str: str = None,
             es_confianza: bool = False) -> dict:

    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 1:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    entry_str = punches[0]
    entry_m   = t2m(entry_str)

    # ── NOCTURNO CRUZADO ─────────────────────────────────────
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

    turno_data = TURNOS.get(turno_h, (22 * 60, 7, 0.0, 0.0, 0.0))
    sched_end, ord_h, xd_fija, xm_fija, xn_fija = turno_data

    is_late     = late_min > TOLERANCE_MIN
    entry_count = (turno_h * 60) + LATE_PENALTY if is_late else turno_h * 60

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    # Ordinarias
    ord_end = entry_count + ord_h * 60
    d_o, mx_o, n_o = split_hours(entry_count, ord_end)

    # Over = minutos más allá del fin del turno completo (ord + extras fijas)
    turno_total_end = sched_end  # el turno termina en sched_end
    over_min = max(0, exit_rounded - turno_total_end)

    # Extras fijas hardcodeadas
    xd = xd_fija
    xm = xm_fija
    xn = xn_fija

    # Extra por llegada anticipada → siempre diurna
    if early_min > 0 and not is_late and not es_confianza:
        xd = r2(xd + calc_early(early_min))

    # Extra adicional por salida tardía → split_hours desde sched_end
    if not es_confianza and over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xd2, xm2, xn2 = split_hours(sched_end, sched_end + int(xh * 60))
            xd = r2(xd + xd2)
            xm = r2(xm + xm2)
            xn = r2(xn + xn2)

    has_extra  = xd + xm + xn > 0
    status     = ('Tardío' if is_late else 'OK') + (' +Extra' if has_extra else '')

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
    """
    Turno quebrado dinámico — no depende de horario fijo.
    B1: entrada redondeada → Break Out redondeado
    B2: Break In → salida redondeada
    Ordinarias: 7h distribuidas entre B1 y B2
    Extras: calculadas con split_hours según donde caigan
    """
    b1_mins = punch_mins[:split_idx + 1]
    b2_mins = punch_mins[split_idx + 1:]

    entry1_m = b1_mins[0]
    exit1_m  = b1_mins[-1]
    entry2_m = b2_mins[0]
    exit2_m  = b2_mins[-1]

    # ── B1: redondear entrada y salida con regla 20/45 ───────
    rem1 = entry1_m % 60
    if rem1 < 20:   entry1_c = (entry1_m // 60) * 60
    elif rem1 < 45: entry1_c = (entry1_m // 60) * 60 + 30
    else:           entry1_c = (entry1_m // 60 + 1) * 60

    exit1_rem = exit1_m % 60
    if exit1_rem >= 45:
        exit1_r = (exit1_m // 60 + 1) * 60
    elif exit1_rem >= 20:
        exit1_r = (exit1_m // 60) * 60 + 30
    else:
        exit1_r = (exit1_m // 60) * 60

    # ── B2: redondear entrada y salida con regla 20/45 ───────
    rem2 = entry2_m % 60
    if rem2 < 20:   entry2_c = (entry2_m // 60) * 60
    elif rem2 < 45: entry2_c = (entry2_m // 60) * 60 + 30
    else:           entry2_c = (entry2_m // 60 + 1) * 60

    exit2_rem = exit2_m % 60
    if exit2_rem >= 45:
        exit2_r = (exit2_m // 60 + 1) * 60
    elif exit2_rem >= 20:
        exit2_r = (exit2_m // 60) * 60 + 30
    else:
        exit2_r = (exit2_m // 60) * 60

    if exit2_r <= entry2_c:
        exit2_r += 24 * 60

    # ── Horas totales ────────────────────────────────────────
    h1 = (exit1_r - entry1_c) / 60
    h2 = (exit2_r - entry2_c) / 60
    if h1 < 0: h1 += 24
    if h2 < 0: h2 += 24
    total    = h1 + h2
    ord_h    = 7

    # Ordinarias distribuidas entre B1 y B2
    ord_b1 = min(h1, ord_h)
    ord_b2 = min(h2, max(0.0, ord_h - ord_b1))

    d1, mx1, n1 = split_hours(entry1_c, entry1_c + int(ord_b1 * 60))
    d2, mx2, n2 = split_hours(entry2_c, entry2_c + int(ord_b2 * 60))

    diu_o = r2(d1 + d2)
    mix_o = r2(mx1 + mx2)
    noc_o = r2(n1 + n2)

    # Extras: lo que sobre de 7h → split_hours dinámico
    xd = xm = xn = 0.0
    if not es_confianza:
        over_total = round((total - ord_h) * 60)
        if over_total > 0:
            # Extras del B2 (después de las ordinarias de B2)
            xs = entry2_c + int(ord_b2 * 60)
            xd2, xm2, xn2 = split_hours(xs, xs + over_total)
            xd = r2(xd + xd2)
            xm = r2(xm + xm2)
            xn = r2(xn + xn2)

    is_fer, fer_name = es_feriado(fecha)
    nota = f'★ Feriado: {fer_name}' if is_fer else (
        f'Quebrado B1:{m2t(entry1_c)}-{m2t(exit1_r % 1440)} '
        f'+ B2:{m2t(entry2_c)}-{m2t(exit2_r % 1440)} = {r2(total)}h'
    )

    return {
        'diu_o': diu_o, 'mix_o': mix_o, 'noc_o': noc_o,
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': 'Quebrado' + (' +Extra' if xd + xm + xn > 0 else ''),
        'nota': nota,
        'entry_red': f'{m2t(entry1_c)}/{m2t(entry2_c)}',
        'exit_red':  f'{m2t(exit1_r % 1440)}/{m2t(exit2_r % 1440)}',
    }
