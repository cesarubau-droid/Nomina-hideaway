# ============================================================
# CALCULADOR RECEPCIÓN — v4.1
# Turnos:
#   06:00-15:00 → 8h ordinarias + 1h xd fija
#   08:00-16:00 → 8h ordinarias
#   09:00-17:00 → 8h ordinarias
#   15:00-22:00 → 7h ordinarias
#   22:00-06:00 → 6h ordinarias + 2h extra noc fija
# Regla 20/45 para extras adicionales
# Llegada anticipada: 25min → 0.5h extra diurna
# Tolerancia: 10min | Siguiente turno si supera tolerancia
# Quebrado excepcional: detectado por Break Out/Break In antes del turno nocturno
#   → bloque extra calculado aparte + sumado al turno principal
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
    6:  (15 * 60, 8, 1.0, 0.0, 0.0),
    8:  (16 * 60, 8, 0.0, 0.0, 0.0),
    9:  (17 * 60, 8, 0.0, 0.0, 0.0),
    15: (22 * 60, 7, 0.0, 0.0, 0.0),
}

NOCTURNO_START = 22 * 60
NOCTURNO_ORD_H = 6
NOCTURNO_XN    = 2.0
NOCTURNO_END   = 30 * 60   # 06:00 siguiente día

STARTS_SORTED = sorted(TURNOS.keys())
CONFIANZA_IDS = {25}


def detect_turno(entry_m: int) -> tuple:
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

    is_fer, fer_name = es_feriado(fecha)
    nota_fer = f'★ Feriado: {fer_name}' if is_fer else ''

    if not punches_raw:
        return empty('Libre', nota_fer if is_fer else 'Día libre')

    # ── NOCTURNO DESDE PROCESADOR ────────────────────────────
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

    # ── DETECCIÓN NOCTURNO INTERNO ───────────────────────────
    raw_mins = [t2m(p) for p in punches_raw if p]
    has_noc_entry  = any(m >= NOCTURNO_START - TOLERANCE_MIN for m in raw_mins)
    has_early_exit = any(m <= 6 * 60 + 30 for m in raw_mins)

    if has_noc_entry and has_early_exit:
        entry_noc = max(m for m in raw_mins if m >= NOCTURNO_START - TOLERANCE_MIN)
        exit_noc  = min(m for m in raw_mins if m <= 6 * 60 + 30)

        # ── QUEBRADO EXCEPCIONAL ─────────────────────────────
        # Hay Break Out/Break In → hay bloque extra antes del turno nocturno
        break_outs = [t2m(p) for p in punches_raw
                      if p in punches_raw]  # se pasan todos desde procesador
        # Detectar si hay marcas ANTES del nocturno (fuera del rango 21:50-06:30)
        pre_noc = [m for m in raw_mins
                   if m < NOCTURNO_START - TOLERANCE_MIN and m > 6 * 60 + 30]

        bloque_extra = None
        if len(pre_noc) >= 2:
            # Hay al menos entrada y salida antes del turno nocturno
            entry_pre = min(pre_noc)
            exit_pre  = max(pre_noc)
            bloque_extra = (entry_pre, exit_pre)

        res = _calcular_nocturno(fecha, entry_noc, exit_noc + 24 * 60,
                                 m2t(entry_noc), nota_fer, es_confianza)

        # Sumar bloque extra si existe
        if bloque_extra and not es_confianza:
            entry_pre_m, exit_pre_m = bloque_extra

            # Redondear entrada con regla 20/45 hacia adelante
            entry_rem = entry_pre_m % 60
            if entry_rem < 20:
                entry_pre_r = (entry_pre_m // 60) * 60
            elif entry_rem < 45:
                entry_pre_r = (entry_pre_m // 60) * 60 + 30
            else:
                entry_pre_r = (entry_pre_m // 60 + 1) * 60

            # Redondear salida con regla 20/45 hacia atrás
            exit_rem = exit_pre_m % 60
            if exit_rem < 20:
                exit_pre_r = (exit_pre_m // 60) * 60
            elif exit_rem < 45:
                exit_pre_r = (exit_pre_m // 60) * 60 + 30
            else:
                exit_pre_r = (exit_pre_m // 60 + 1) * 60

            # Horas exactas entre entrada y salida redondeadas
            duracion = exit_pre_r - entry_pre_r
            if duracion > 0:
                xd2, xm2, xn2 = split_hours(entry_pre_r,
                                             entry_pre_r + duracion)
                res['xd'] = r2(res['xd'] + xd2)
                res['xm'] = r2(res['xm'] + xm2)
                res['xn'] = r2(res['xn'] + xn2)
                res['nota'] = (res['nota'] or '') + (
                    f' | Bloque extra: {m2t(entry_pre_r)}-{m2t(exit_pre_r)} '
                    f'= {round(duracion/60, 2)}h'
                )

        return aplicar_feriado(res, fecha)

    # ── TURNO NORMAL ─────────────────────────────────────────
    entry_str_val = punches[0]
    entry_m       = t2m(entry_str_val)

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta',
                     f'Entrada: {entry_str_val}',
                     entry_red=entry_str_val, exit_red='?')

    exit_m = t2m(punches[-1])
    turno_h, early_min, late_min = detect_turno(entry_m)
    sched_end, ord_h, xd_fija, xm_fija, xn_fija = TURNOS.get(
        turno_h, (22 * 60, 7, 0.0, 0.0, 0.0)
    )

    is_late     = late_min > TOLERANCE_MIN
    entry_count = turno_h * 60 + LATE_PENALTY if is_late else turno_h * 60

    if exit_m <= entry_count:
        exit_m += 24 * 60

    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count:
        exit_rounded += 24 * 60

    d_o, mx_o, n_o = split_hours(entry_count, entry_count + ord_h * 60)
    over_min = max(0, exit_rounded - sched_end)

    xd = xd_fija
    xm = xm_fija
    xn = xn_fija

    if not es_confianza:
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

    has_extra  = xd + xm + xn > 0
    late_label = 'Tardío' if is_late else 'OK'
    status     = late_label + (' +Extra' if has_extra else '')

    if nota_fer:
        nota = nota_fer
    elif is_late:
        nota = f'Tardío: llegó {entry_str_val}, cuenta desde {m2t(entry_count)}'
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
