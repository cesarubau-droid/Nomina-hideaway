# ============================================================
# CALCULADOR DE HORAS — v2.1
# Hotel Rio Celeste Hideaway
# ============================================================

from config import *


def t2m(t: str) -> int:
    """'HH:MM' → minutos desde medianoche."""
    if t is None: return 0
    h, m = map(int, str(t).split(':'))
    return h * 60 + m


def m2t(m: int) -> str:
    """Minutos desde medianoche → 'HH:MM'."""
    m = int(m) % (24 * 60)
    return f"{m//60:02d}:{m%60:02d}"


def r2(x) -> float:
    return round(float(x), 2)


def split_hours(start_m: int, end_m: int) -> tuple:
    """
    Divide un bloque de tiempo en horas diurnas, mixtas y nocturnas.
    Diurna: 05:00-19:30 | Mixta: 19:30-22:30 | Nocturna: 22:30-05:00
    """
    if end_m <= start_m:
        end_m += 24 * 60
    while start_m >= 1440:
        start_m -= 1440
        end_m   -= 1440
    segs = [
        (0,    300,  'noc'), (300,  1170, 'diu'),
        (1170, 1350, 'mix'), (1350, 1440, 'noc'),
        (1440, 1740, 'noc'), (1740, 2610, 'diu'),
        (2610, 2790, 'mix'), (2790, 2880, 'noc'),
    ]
    diu = mix = noc = 0
    for ss, se, t in segs:
        os = max(start_m, ss); oe = min(end_m, se)
        if oe > os:
            mins = oe - os
            if t == 'diu':   diu += mins
            elif t == 'mix': mix += mins
            else:            noc += mins
    return r2(diu/60), r2(mix/60), r2(noc/60)


def round_exit(exit_m: int, sched_end: int) -> int:
    """Redondea la salida real con regla 20/45 relativa al fin del turno."""
    if exit_m <= sched_end:
        return sched_end
    over = exit_m - sched_end
    if over > 12 * 60: over = 0
    full = over // 60; rem = over % 60
    if rem < EXTRA_HALF_MIN:   return sched_end + full * 60
    elif rem < EXTRA_FULL_MIN: return sched_end + full * 60 + 30
    else:                      return sched_end + (full + 1) * 60


def calc_extra(over_min: int) -> float:
    """Horas extra según regla 20/45."""
    if over_min < EXTRA_HALF_MIN: return 0
    elif over_min < EXTRA_FULL_MIN: return 0.5
    else:
        full = over_min // 60; rem = over_min % 60
        if rem < EXTRA_HALF_MIN:   er = 0
        elif rem < EXTRA_FULL_MIN: er = 0.5
        else:                      er = 1.0
        return full + er


def nearest_shift(entry_m: int, starts: list) -> tuple:
    """
    Turno más cercano a la entrada real.
    En empate → turno anterior (menor hora).
    Retorna (turno_minutos, diferencia_minutos).
    """
    diffs = [(abs(entry_m - h*60), h) for h in starts]
    diffs.sort()
    min_diff = diffs[0][0]
    candidates = [h for d, h in diffs if d == min_diff]
    best = min(candidates)
    return best * 60, entry_m - best * 60


def clean_punches(punches: list) -> list:
    """Elimina marcaciones con menos de DUPLICATE_MIN entre sí."""
    if not punches: return []
    cleaned = [punches[0]]
    for p in punches[1:]:
        if t2m(p) - t2m(cleaned[-1]) >= DUPLICATE_MIN:
            cleaned.append(p)
    return cleaned


def detect_split(punch_mins: list) -> tuple:
    """
    Detecta turno quebrado.
    Con 4 marcaciones: split siempre entre índice 1 y 2 (salida B1 → entrada B2).
    Con 3 marcaciones: busca el primer gap >= SPLIT_GAP_MIN.
    """
    if len(punch_mins) < 3:
        return False, None
    if len(punch_mins) == 4:
        gap = punch_mins[2] - punch_mins[1]
        if gap >= SPLIT_GAP_MIN:
            return True, 1
    for i in range(len(punch_mins) - 1):
        if punch_mins[i+1] - punch_mins[i] >= SPLIT_GAP_MIN:
            return True, i
    return False, None


def empty(status, nota='', entry_red='', exit_red=''):
    return {
        'diu_o': 0, 'mix_o': 0, 'noc_o': 0,
        'xd': 0, 'xm': 0, 'xn': 0,
        'status': status, 'nota': nota,
        'entry_red': entry_red, 'exit_red': exit_red,
    }


def calcular_dia(fecha: str, punches_raw: list, dept: str,
                 tipo: str = 'Fijo') -> dict:
    """
    Calcula horas para un empleado en un día.

    Args:
        fecha:       'YYYY-MM-DD'
        punches_raw: lista de strings 'HH:MM' (ya limpias de duplicados)
        dept:        departamento interno (clave en DEPT_STARTS)
        tipo:        'Fijo' | 'Por Horas' | 'Confianza' | 'Compensado'

    Returns:
        dict con diu_o, mix_o, noc_o, xd, xm, xn, status, nota,
              entry_red, exit_red
    """
    is_fer   = fecha in FERIADOS
    fer_name = FERIADOS.get(fecha, '')
    is_conf  = tipo == 'Confianza'
    is_comp  = tipo == 'Compensado' or dept in COMPENSADO_DEPTS
    ord_h    = ORD_HOURS_COMPENSADO if is_comp else ORD_HOURS_DEFAULT

    # Sin marcaciones → día libre
    if not punches_raw:
        return empty('Libre', f'★ Feriado: {fer_name}' if is_fer else 'Día libre')

    punches = clean_punches(sorted(
        [p for p in punches_raw if p is not None],
        key=lambda x: t2m(x)
    ))

    if len(punches) < 2:
        return empty('Sin salida — Andry ajusta', f'Entrada: {punches[0]}',
                     entry_red=punches[0], exit_red='?')

    starts  = DEPT_STARTS.get(dept, [8])
    entry_m = t2m(punches[0])
    exit_m  = t2m(punches[-1])

    # ── SEGURIDAD ────────────────────────────────────────────
    if dept == 'SEGURIDAD':
        re_m, diff = nearest_shift(entry_m, starts)
        turno_h    = re_m // 60
        is_late    = diff > TOLERANCE_MIN
        entry_count = re_m + LATE_PENALTY if is_late else re_m

        if turno_h in SEG_ACUERDO_STARTS:
            # Con acuerdo: 6h ord + 1h extra noc fija
            ord_end = re_m + 6 * 60
            d_o, mx_o, n_o = split_hours(re_m, ord_end)
            nota = f'★ Feriado: {fer_name}' if is_fer else \
                   'Acuerdo Seg: 6h ord + 1h extra noc'
            return {
                'diu_o': d_o, 'mix_o': mx_o, 'noc_o': n_o,
                'xd': 0, 'xm': 0, 'xn': 1.0,
                'status': 'Con Acuerdo', 'nota': nota,
                'entry_red': m2t(re_m),
                'exit_red':  m2t((re_m + 7*60) % 1440),
            }
        else:
            # Sin acuerdo: 8h ord + regla 20/45
            sched_end = entry_count + ord_h * 60
            if exit_m <= entry_count: exit_m += 24 * 60
            exit_rounded = round_exit(exit_m, sched_end)
            total_min  = exit_rounded - entry_count
            over_min   = total_min - ord_h * 60
            actual_ord = min(total_min, ord_h * 60)
            d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)
            xd = xm = xn = 0
            if over_min >= EXTRA_HALF_MIN:
                xh = calc_extra(over_min)
                if xh > 0:
                    xs = entry_count + ord_h * 60
                    xd, xm, xn = split_hours(xs, xs + int(xh * 60))
            status = ('Tardío' if is_late else 'OK') + \
                     (' +Extra' if xd + xm + xn > 0 else '')
            nota   = f'★ Feriado: {fer_name}' if is_fer else \
                     (f'Tardío: llegó {punches[0]}, cuenta desde {m2t(entry_count)}'
                      if is_late else '')
            return {
                'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
                'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
                'status': status, 'nota': nota,
                'entry_red': m2t(entry_count),
                'exit_red':  m2t(exit_rounded % 1440),
            }

    # ── RECEPCIÓN NOCTURNO ───────────────────────────────────
    if dept == 'RECEPCION' and entry_m >= REC_NOCTURNO_START * 60:
        re_m    = REC_NOCTURNO_START * 60
        ord_end = re_m + 6 * 60
        d_o, mx_o, n_o = split_hours(re_m, ord_end)
        nota = f'★ Feriado: {fer_name}' if is_fer else \
               '6h ord + 2h extra noc (Recepción nocturno)'
        return {
            'diu_o': d_o, 'mix_o': mx_o, 'noc_o': n_o,
            'xd': 0, 'xm': 0, 'xn': 2.0,
            'status': 'Nocturno Recepción', 'nota': nota,
            'entry_red': '22:00', 'exit_red': '06:00',
        }

    # ── TURNO QUEBRADO ───────────────────────────────────────
    if dept in SPLIT_DEPTS:
        punch_mins = [t2m(p) for p in punches]
        is_split, si = detect_split(punch_mins)
        if is_split:
            b1 = punch_mins[:si + 1]
            b2 = punch_mins[si + 1:]
            re1, _ = nearest_shift(b1[0], starts)
            re2, _ = nearest_shift(b2[0], starts)
            # B1 termina a las re1+6h (bloque de 6h), B2 termina a las 22:00
            sched1 = re1 + 6 * 60
            sched2 = 22 * 60
            exit1  = round_exit(b1[-1], sched1)
            exit2  = round_exit(b2[-1], sched2)
            h1     = (exit1 - re1) / 60
            h2     = (exit2 - re2) / 60
            if h2 < 0: h2 += 24
            total    = h1 + h2
            over_min = round((total - ord_h) * 60)
            ord_b1   = min(h1, ord_h)
            ord_b2   = min(h2, ord_h - ord_b1)
            d1, mx1, n1 = split_hours(re1, re1 + int(ord_b1 * 60))
            d2, mx2, n2 = split_hours(re2, re2 + int(ord_b2 * 60))
            diu_o = r2(d1 + d2); mix_o = r2(mx1 + mx2); noc_o = r2(n1 + n2)
            xd = xm = xn = 0
            if not is_conf and over_min >= EXTRA_HALF_MIN:
                xh = calc_extra(over_min)
                if xh > 0:
                    xs = re2 + int(ord_b2 * 60)
                    xd, xm, xn = split_hours(xs, xs + int(xh * 60))
            nota = f'★ Feriado: {fer_name}' if is_fer else \
                   f'Quebrado B1:{m2t(re1)}-{m2t(exit1)} + B2:{m2t(re2)}-{m2t(exit2)} = {r2(total)}h'
            return {
                'diu_o': diu_o, 'mix_o': mix_o, 'noc_o': noc_o,
                'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
                'status': 'Quebrado', 'nota': nota,
                'entry_red': f'{m2t(re1)}/{m2t(re2)}',
                'exit_red':  f'{m2t(exit1)}/{m2t(exit2)}',
            }

    # ── TURNO NORMAL ─────────────────────────────────────────
    re_m, diff  = nearest_shift(entry_m, starts)
    is_late     = diff > TOLERANCE_MIN
    entry_count = re_m + LATE_PENALTY if is_late else re_m
    sched_end   = entry_count + ord_h * 60
    if exit_m <= entry_count: exit_m += 24 * 60
    exit_rounded = round_exit(exit_m, sched_end)
    if exit_rounded <= entry_count: exit_rounded += 24 * 60
    total_min  = exit_rounded - entry_count
    over_min   = total_min - ord_h * 60
    actual_ord = min(total_min, ord_h * 60)
    d_o, mx_o, n_o = split_hours(entry_count, entry_count + actual_ord)
    xd = xm = xn = 0
    if not is_conf and over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = entry_count + ord_h * 60
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))
    status = ('Tardío' if is_late else 'OK') + \
             (' +Extra' if xd + xm + xn > 0 else '')
    nota   = f'★ Feriado: {fer_name}' if is_fer else \
             (f'Tardío: llegó {punches[0]}, cuenta desde {m2t(entry_count)}'
              if is_late else '')
    return {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': status, 'nota': nota,
        'entry_red': m2t(entry_count),
        'exit_red':  m2t(exit_rounded % 1440),
    }
