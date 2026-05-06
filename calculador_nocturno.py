# ============================================================
# CALCULADOR NOCTURNO — Turnos que cruzan medianoche
# Hotel Rio Celeste Hideaway
# ============================================================

from calculador import split_hours, round_exit, calc_extra, nearest_shift, m2t, t2m, r2
from config import FERIADOS, SEG_ACUERDO_STARTS, REC_NOCTURNO_START, DEPT_STARTS, EXTRA_HALF_MIN


def calcular_nocturno(fecha: str, entry_str: str, exit_str: str,
                      dept: str) -> dict:
    """
    Calcula un turno nocturno cruzado (entrada >= 22:00, salida al día siguiente).
    entry_str y exit_str son HH:MM — NO se ordenan, se usan tal cual.

    Args:
        fecha:     fecha de la ENTRADA ('YYYY-MM-DD')
        entry_str: hora de entrada 'HH:MM' (ej: '22:53')
        exit_str:  hora de salida 'HH:MM' del día siguiente (ej: '06:00')
        dept:      departamento interno

    Returns:
        dict con diu_o, mix_o, noc_o, xd, xm, xn, status, nota,
              entry_red, exit_red
    """
    is_fer   = fecha in FERIADOS
    fer_name = FERIADOS.get(fecha, '')

    entry_m = t2m(entry_str)
    exit_m  = t2m(exit_str)

    # El turno cruzó medianoche → exit del día siguiente
    if exit_m <= entry_m:
        exit_m += 24 * 60

    starts  = DEPT_STARTS.get(dept, [22, 23])
    re_m, _ = nearest_shift(entry_m, starts)
    turno_h = re_m // 60

    # ── SEGURIDAD CON ACUERDO ────────────────────────────────
    if dept == 'SEGURIDAD' and turno_h in SEG_ACUERDO_STARTS:
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

    # ── RECEPCIÓN NOCTURNO ───────────────────────────────────
    if dept == 'RECEPCION' and turno_h == REC_NOCTURNO_START:
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

    # ── TURNO NOCTURNO NORMAL ────────────────────────────────
    sched_end    = re_m + 8 * 60
    exit_rounded = round_exit(exit_m, sched_end)
    total_min    = exit_rounded - re_m
    over_min     = total_min - 8 * 60
    actual_ord   = min(total_min, 8 * 60)
    d_o, mx_o, n_o = split_hours(re_m, re_m + actual_ord)
    xd = xm = xn = 0
    if over_min >= EXTRA_HALF_MIN:
        xh = calc_extra(over_min)
        if xh > 0:
            xs = re_m + 8 * 60
            xd, xm, xn = split_hours(xs, xs + int(xh * 60))
    nota = f'★ Feriado: {fer_name}' if is_fer else ''
    return {
        'diu_o': r2(d_o), 'mix_o': r2(mx_o), 'noc_o': r2(n_o),
        'xd': r2(xd), 'xm': r2(xm), 'xn': r2(xn),
        'status': 'OK +Extra' if xd + xm + xn > 0 else 'OK',
        'nota': nota,
        'entry_red': m2t(re_m),
        'exit_red':  m2t(exit_rounded % 1440),
    }
