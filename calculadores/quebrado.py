# ============================================================
# CALCULADOR QUEBRADO — v4.0
# Aplica a: Restaurante Salón, Alimentos Cocina
# Regla: detecta gap >= 4h entre bloques → B1 + B2
#        8h ordinarias totales + regla 20/45
#        Confianza: nunca extras
# ============================================================

from calculador_base import (
    t2m, m2t, r2, split_hours, nearest_shift,
    round_exit, calc_extra, clean_punches, empty, es_feriado
)
from config import (
    DEPT_STARTS, TOLERANCE_MIN, LATE_PENALTY,
    ORD_HOURS_DEFAULT, EXTRA_HALF_MIN, SPLIT_GAP_MIN
)


def calcular(fecha: str, punches_raw: list, dept: str,
             es_confianza: bool = False) -> dict:
    """
    Calcula horas para departamentos con turno quebrado.

    Args:
        fecha:        'YYYY-MM-DD'
        punches_raw:  lista ['HH:MM', ...] — TODAS las marcas del día
                      ordenadas por hora
        dept:         'RESTAURANTE SALON' o 'ALIMENTOS COCINA'
        es_confianza: si es True, nunca se calculan extras
    """
    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''
    starts   = DEPT_STARTS.get(dept, [6])
    ord_h    = ORD_HOURS_DEFAULT

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    punches = clean_punches(sorted(punches_raw, key=lambda x: t2m(x)))

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {punches[0]}',
                     entry_red=punches[0], exit_red='?')

    punch_mins = [t2m(p) for p in punches]
    is_split, split_idx = _detect_split(punch_mins)

    if is_split:
        return _calcular_quebrado(
            punches, punch_mins, split_idx,
            starts, ord_h, nota_fer, es_confianza
        )
    else:
        return _calcular_normal(
            punches, starts, ord_h, nota_fer, es_confianza
        )


def _detect_split(punch_mins: list) -> tuple:
    """
    Detecta turno quebrado segun cantidad de punches:
    4 punches: siempre quebrado, split entre indice 1 y 2
    3 punches: split en el gap mas grande si >= SPLIT_GAP_MIN
    2 punches: siempre turno normal
    """
    n = len(punch_mins)
    if n == 4:
        return True, 1
    if n == 3:
        gaps = [punch_mins[i+1] - punch_mins[i] for i in range(n-1)]
        max_idx = gaps.index(max(gaps))
        if gaps[max_idx] >= SPLIT_GAP_MIN:
            return True, max_idx
    return False, None


def _calcular_quebrado(punches, punch_mins, split_idx,
                       starts, ord_h, nota_fer, es_confianza) -> dict:
    """
    Calcula turno quebrado B1 + B2.

    B1: primera parte del turno (ej 06:00-14:00)
    B2: segunda parte del turno (ej 17:00-22:00)

    El split_idx indica el último punch de B1.
    """
    # ── Separar bloques ──────────────────────────────────────
    b1_mins = punch_mins[:split_idx + 1]   # ej [360, 847]
    b2_mins = punch_mins[split_idx + 1:]   # ej [1079, 1332]

    entry1_m = b1_mins[0]   # entrada real B1
    exit1_m  = b1_mins[-1]  # salida real B1
    entry2_m = b2_mins[0]   # entrada real B2
    exit2_m  = b2_mins[-1]  # salida real B2

    # ── Redondear entradas al turno más cercano ──────────────
    re1, diff1 = nearest_shift(entry1_m, starts)
    re2, _     = nearest_shift(entry2_m, starts)

    # Tardío solo aplica en B1
    is_late      = diff1 > TOLERANCE_MIN
    entry1_count = re1 + LATE_PENALTY if is_late else re1

    # ── Calcular duración real de cada bloque ────────────────
    # B1: de entry1_count a exit1_m
    # Si exit1_m <= entry1_count (no debería pasar en B1 diurno), ajustar
    if exit1_m <= entry1_count:
        exit1_m += 24 * 60

    # B2: de re2 a exit2_m, siempre contra las 22:00 como fin programado
    # (todos los turnos quebrados de restaurante/cocina terminan a las 22:00)
    sched2 = 22 * 60
    if exit2_m <= re2:
        exit2_m += 24 * 60

    # ── Redondear salidas con regla 20/45 ────────────────────
    # B1: fin programado = entry1_count + horas hasta el break
    # Como no hay turno fijo de fin de B1, usamos la salida real misma
    # como referencia — la regla 20/45 se aplica desde exit1_m
    # Simplificado: B1 no tiene extra, su salida es la real redondeada al 0
    # (el break siempre termina el bloque limpio)
    exit1_r = (exit1_m // 60) * 60   # redondear a la hora entera más cercana hacia abajo
    # Aplicar regla: si los minutos de salida >= 45 → hora completa, si >=20 → media hora
    exit1_rem = exit1_m % 60
    if exit1_rem >= 45:
        exit1_r = (exit1_m // 60 + 1) * 60
    elif exit1_rem >= 20:
        exit1_r = (exit1_m // 60) * 60 + 30
    else:
        exit1_r = (exit1_m // 60) * 60

    exit2_r = round_exit(exit2_m, sched2)

    # ── Horas de cada bloque ─────────────────────────────────
    h1 = (exit1_r - entry1_count) / 60
    h2 = (exit2_r - re2) / 60
    if h1 < 0: h1 += 24
    if h2 < 0: h2 += 24

    total    = h1 + h2
    over_min = round((total - ord_h) * 60)

    # ── Ordinarias ───────────────────────────────────────────
    ord_b1 = min(h1, ord_h)
    ord_b2 = min(h2, max(0.0, ord_h - ord_b1))

    d1, mx1, n1 = split_hours(entry1_count, entry1_count + int(ord_b1 * 60))
    d2, mx2, n2 = split_hours(re2,          re2          + int(ord_b2 * 60))

    diu_o = r2(d1 + d2)
    mix_o = r2(mx1 + mx2)
    noc_o = r2(n1 + n2)

    # ── Extras (solo si no es confianza) ─────────────────────
    xd = xm = xn = 0.0
    if not es_confianza and over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = re2 + int(ord_b2 * 60)
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))

    # ── Construir resultado ──────────────────────────────────
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


def _calcular_normal(punches, starts, ord_h, nota_fer, es_confianza) -> dict:
    """Turno normal (sin gap suficiente para quebrado)."""
    entry_m      = t2m(punches[0])
    exit_m       = t2m(punches[-1])
    re_m, diff   = nearest_shift(entry_m, starts)
    is_late      = diff > TOLERANCE_MIN
    entry_count  = re_m + LATE_PENALTY if is_late else re_m
    sched_end    = entry_count + ord_h * 60

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    total_min    = exit_rounded - entry_count
    over_min     = total_min - ord_h * 60
    actual_ord   = min(total_min, ord_h * 60)

    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)

    xd = xm = xn = 0.0
    if not es_confianza and over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = entry_count + ord_h * 60
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))

    has_extra  = xd + xm + xn > 0
    late_label = 'Tardío' if is_late else 'OK'
    status     = late_label + (' +Extra' if has_extra else '')

    nota = nota_fer if nota_fer else (
        f'Tardío: llegó {punches[0]}, cuenta desde {m2t(entry_count)}'
        if is_late else ''
    )

    return {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': status, 'nota': nota,
        'entry_red': m2t(entry_count),
        'exit_red':  m2t(exit_rounded % 1440),
    }
