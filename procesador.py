# ============================================================
# PROCESADOR v4.0 — Arquitectura por departamento
# Hotel Rio Celeste Hideaway
# ============================================================

import pandas as pd
from datetime import datetime, timedelta

from calculador_base import t2m, empty
from calculadores import seguridad, recepcion, quebrado, estandar, compensado, ama_de_llaves, restaurante, jardin, mantenimiento, rh, spa, cocina
from generador_excel import generar_excel
from config import (
    FERIADOS, COMPENSADO_DEPTS, CONFIANZA_NOMBRES, SPLIT_DEPTS
)

# ── MAPAS ────────────────────────────────────────────────────

DEPT_MAP = {
    'SEGURIDAD':     'SEGURIDAD',
    'ALIMENTOS':     'ALIMENTOS COCINA',
    'AMA DE LLAVES': 'AMA DE LLAVES',
    'RESTAURANTE':   'RESTAURANTE SALON',
    'RECEPCION':     'RECEPCION',
    'SPA':           'SPA',
    'JARDIN':        'JARDIN',
    'MANTENIMIENTO': 'MANTENIMIENTO',
}

EMP_MAP = {
    2:   ('RH',                False),
    22:  ('SOSTENIBILIDAD',    False),
    47:  ('PROVEEDURIA',       False),
    54:  ('PROVEEDURIA',       False),
    84:  ('CONTABILIDAD',      False),
    138: ('AMA DE LLAVES',     True),
    141: ('ALIMENTOS COCINA',  True),
    121: ('AMA DE LLAVES',     True),
    62:  ('RESTAURANTE SALON', True),
    35:  ('RESTAURANTE SALON', True),
    76:  ('RESTAURANTE SALON', True),
    12:  ('AMA DE LLAVES',     True),
    40:  ('RESTAURANTE SALON', True),
    112: ('RESTAURANTE SALON', True),
    34:  ('RESTAURANTE SALON', True),
    36:  ('RESTAURANTE SALON', True),
}

EXCLUIDOS = {1, 65}

CHECK_IN_STATES  = {'Check In', 'Overtime In'}
CHECK_OUT_STATES = {'Check Out', 'Overtime Out'}

# ── HELPERS ──────────────────────────────────────────────────

def normalizar_dept(biotime_dept, eid):
    d = str(biotime_dept).strip().upper()
    if d in DEPT_MAP: return DEPT_MAP[d]
    if eid in EMP_MAP: return EMP_MAP[eid][0]
    return None


def get_tipo(eid, biotime_dept, tipo_excel):
    dept = normalizar_dept(biotime_dept, eid)
    if dept in COMPENSADO_DEPTS: return 'Compensado'
    if eid in EMP_MAP and EMP_MAP[eid][1]: return 'Por Horas'
    return tipo_excel


def es_confianza(first, last, tipo_excel):
    if tipo_excel == 'Confianza': return True
    nombre = f"{first} {last}".strip().lower()
    return any(c in nombre for c in CONFIANZA_NOMBRES)


def cargar_empleados(emp_path):
    df = pd.read_excel(emp_path)
    df['Employee_ID'] = df['Employee_ID'].astype(int)
    return dict(zip(df['Employee_ID'], df['Tipo']))


def leer_biotime(biotime_path):
    df = pd.read_excel(biotime_path, header=None, skiprows=1)
    df.columns = [
        'Employee_ID', 'First_Name', 'Last_Name', 'Nick_Name', 'Gender',
        'Dept_Code', 'Department', 'Position_Code', 'Position', 'Date', 'Time',
        'Punch_State', 'Temperature', 'With_Mask', 'Verify_Type',
        'Work_Code', 'Data_Sources'
    ]
    df = df[df['Date'] != 'Date'].copy()
    df = df.dropna(subset=['Time'])
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Time'] = df['Time'].apply(lambda x: str(x)[:5] if pd.notna(x) and x != '' else None)
    df['Time_sort'] = pd.to_numeric(df['Time'].apply(
        lambda x: int(x[:2])*60+int(x[3:5]) if x and len(x) >= 5 else 0
    ), errors='coerce').fillna(0)
    df['Employee_ID'] = pd.to_numeric(df['Employee_ID'], errors='coerce')

    nombre_a_eid = {}
    nombre_fn_a_eid = {}
    for _, r in df[df['Employee_ID'].notna()].iterrows():
        fn = str(r['First_Name']).strip()
        ln = str(r['Last_Name']).strip() if pd.notna(r['Last_Name']) else ''
        nombre_completo = (fn + ' ' + ln).strip().lower()
        if nombre_completo not in nombre_a_eid:
            nombre_a_eid[nombre_completo] = int(r['Employee_ID'])
        if fn.lower() not in nombre_fn_a_eid:
            nombre_fn_a_eid[fn.lower()] = int(r['Employee_ID'])

    def inferir_eid(row):
        if pd.notna(row['Employee_ID']):
            return row['Employee_ID']
        fn = str(row['First_Name']).strip()
        ln = str(row['Last_Name']).strip() if pd.notna(row['Last_Name']) else ''
        nombre_completo = (fn + ' ' + ln).strip().lower()
        if nombre_completo in nombre_a_eid:
            return nombre_a_eid[nombre_completo]
        return nombre_fn_a_eid.get(fn.lower(), float('nan'))

    df['Employee_ID'] = df.apply(inferir_eid, axis=1)
    df = df.sort_values(['Employee_ID', 'Date', 'Time_sort']).reset_index(drop=True)
    df = df.drop(columns=['Time_sort'])
    return df


def make_record(eid, first, last, dept, tipo, fecha_str,
                entry_raw, exit_raw, resultado):
    return {
        'ID':              eid,
        'Nombre':          first,
        'Apellido':        last,
        'Departamento':    dept,
        'Tipo':            tipo,
        'Fecha':           fecha_str,
        'Feriado':         FERIADOS.get(fecha_str, ''),
        'Entrada Real':    entry_raw,
        'Entrada Redond':  resultado['entry_red'],
        'Salida Real':     exit_raw,
        'Salida Redond':   resultado['exit_red'],
        'Diurnas Ord':     resultado['diu_o'],
        'Mixtas Ord':      resultado['mix_o'],
        'Nocturnas Ord':   resultado['noc_o'],
        'Extra Diurnas':   resultado['xd'],
        'Extra Mixtas':    resultado['xm'],
        'Extra Nocturnas': resultado['xn'],
        'Estado':          resultado['status'],
        'Notas':           resultado['nota'],
    }


def make_libre(eid, first, last, dept, tipo, fecha_str):
    fer = FERIADOS.get(fecha_str, '')
    return {
        'ID': eid, 'Nombre': first, 'Apellido': last,
        'Departamento': dept, 'Tipo': tipo,
        'Fecha': fecha_str, 'Feriado': fer,
        'Entrada Real': 'LIBRE', 'Entrada Redond': '',
        'Salida Real': 'LIBRE', 'Salida Redond': '',
        'Diurnas Ord': 0, 'Mixtas Ord': 0, 'Nocturnas Ord': 0,
        'Extra Diurnas': 0, 'Extra Mixtas': 0, 'Extra Nocturnas': 0,
        'Estado': 'Libre',
        'Notas': f'★ Feriado: {fer}' if fer else 'Día libre',
    }


# ── ENRUTADOR ────────────────────────────────────────────────

def calcular_resultado(dept, fecha_str, punches_check, punches_todos,
                       tipo, is_conf, es_nocturno=False, exit_str=None,
                       eid=None):
    if dept == 'SEGURIDAD':
        return seguridad.calcular(
            fecha_str, punches_check,
            es_nocturno=es_nocturno, exit_str=exit_str,
            es_confianza=is_conf, eid=eid
        )

    if dept == 'RECEPCION':
        return recepcion.calcular(
            fecha_str, punches_check,
            es_nocturno=es_nocturno, exit_str=exit_str,
            es_confianza=is_conf
        )

    if dept == 'RESTAURANTE SALON':
        return restaurante.calcular(
            fecha_str, punches_todos,
            es_nocturno=es_nocturno, exit_str=exit_str,
            es_confianza=is_conf
        )

    if dept == 'ALIMENTOS COCINA':
        return cocina.calcular(
            fecha_str, punches_todos,
            es_nocturno=es_nocturno, exit_str=exit_str,
            es_confianza=is_conf
        )

    if dept in SPLIT_DEPTS:
        return quebrado.calcular(
            fecha_str, punches_todos, dept,
            es_confianza=is_conf
        )

    if dept in COMPENSADO_DEPTS:
        return compensado.calcular(fecha_str, punches_check, dept)

    if dept == 'AMA DE LLAVES':
        return ama_de_llaves.calcular(
            fecha_str, punches_check,
            es_nocturno=es_nocturno, exit_str=exit_str
        )

    if dept == 'SPA':
        return spa.calcular(fecha_str, punches_check, es_confianza=is_conf)

    if dept == 'RH':
        return rh.calcular(fecha_str, punches_check)

    if dept == 'MANTENIMIENTO':
        return mantenimiento.calcular(fecha_str, punches_check)

    if dept == 'JARDIN':
        return jardin.calcular(
            fecha_str, punches_check,
            es_nocturno=es_nocturno, exit_str=exit_str
        )

    return estandar.calcular(
        fecha_str, punches_check, dept,
        es_nocturno=es_nocturno, exit_str=exit_str,
        es_confianza=is_conf
    )


# ── PROCESADOR PRINCIPAL ─────────────────────────────────────

def procesar(biotime_path, emp_path, fecha_inicio, fecha_fin):
    df        = leer_biotime(biotime_path)
    emp_tipos = cargar_empleados(emp_path)

    fi_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    ff_date = datetime.strptime(fecha_fin,    '%Y-%m-%d').date()

    emp_info = {}
    punches_map = {}

    for _, row in df.iterrows():
        eid = row['Employee_ID']
        if pd.isna(eid): continue
        eid = int(eid)
        if eid in EXCLUIDOS: continue
        date  = row['Date'].date()
        time  = row['Time']
        state = str(row['Punch_State']).strip()
        state_map = {
            'check in':   'Check In',
            'check out':  'Check Out',
            'break in':   'Break In',
            'break out':  'Break Out',
        }
        state = state_map.get(state.lower(), state)
        bdept = str(row['Department'])

        if eid not in emp_info:
            emp_info[eid] = {
                'first': str(row['First_Name']),
                'last':  str(row['Last_Name']),
                'bdept': bdept,
            }

        key = (eid, date)
        punches_map.setdefault(key, [])
        punches_map[key].append((time, state))

    all_dates = []
    d = fi_date
    while d <= ff_date:
        all_dates.append(d)
        d += timedelta(days=1)

    emp_set = set(eid for (eid, dt) in punches_map if fi_date <= dt <= ff_date)
    records = []

    for eid in sorted(emp_set):
        if eid not in emp_info: continue
        info  = emp_info[eid]
        first = info['first']
        last  = info['last']
        bdept = info['bdept']
        dept  = normalizar_dept(bdept, eid)
        if not dept: continue

        tipo_excel = emp_tipos.get(eid, 'Fijo')
        tipo       = get_tipo(eid, bdept, tipo_excel)
        is_conf    = es_confianza(first, last, tipo_excel)
        if is_conf: tipo = 'Confianza'

        for d in all_dates:
            fecha_str   = d.strftime('%Y-%m-%d')
            day_punches = punches_map.get((eid, d), [])

            if not day_punches:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            check_ins  = sorted(
                [t for t, s in day_punches if s in CHECK_IN_STATES],
                key=lambda x: t2m(x)
            )
            check_outs = sorted(
                [t for t, s in day_punches if s in CHECK_OUT_STATES],
                key=lambda x: t2m(x)
            )
            todos = sorted(
                [t for t, s in day_punches],
                key=lambda x: t2m(x)
            )

            if not check_ins and check_outs:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            # ── FILTRO MADRUGADA ──────────────────────────────
            # Elimina Check Outs de madrugada que sean anteriores
            # al primer Check In del día. Mantiene los que son
            # posteriores al Check In (salidas de turno nocturno válidas).
            if check_ins and check_outs:
                first_in_m = t2m(check_ins[0])
                check_outs_filtrados = [
                    t for t in check_outs
                    if t2m(t) >= 6 * 60 + 30 or t2m(t) > first_in_m
                ]
                if check_outs_filtrados:
                    check_outs = check_outs_filtrados
                # Reconstruir todos con check_outs filtrados
                todos = sorted(
                    check_ins + check_outs +
                    [t for t, s in day_punches if s in ('Break In', 'Break Out')],
                    key=lambda x: t2m(x)
                )

            if not check_ins and not check_outs:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            if not check_ins:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            if dept in SPLIT_DEPTS:
                if not check_outs:
                    next_day = d + timedelta(days=1)
                    next_punches = punches_map.get((eid, next_day), [])
                    next_outs = sorted(
                        [t for t, s in next_punches if s in CHECK_OUT_STATES],
                        key=lambda x: t2m(x)
                    )
                    if next_outs:
                        todos_ext = todos + [next_outs[0]]
                        res = calcular_resultado(
                            dept, fecha_str, check_ins, todos_ext,
                            tipo, is_conf, eid=eid
                        )
                        records.append(make_record(
                            eid, first, last, dept, tipo, fecha_str,
                            check_ins[0], next_outs[0], res
                        ))
                    else:
                        res = empty('Sin salida — Andry ajusta',
                                    f'Entrada: {check_ins[0]}',
                                    entry_red=check_ins[0], exit_red='?')
                        records.append(make_record(
                            eid, first, last, dept, tipo, fecha_str,
                            check_ins[0], '?', res
                        ))
                else:
                    res = calcular_resultado(
                        dept, fecha_str, check_ins, todos,
                        tipo, is_conf, eid=eid
                    )
                    records.append(make_record(
                        eid, first, last, dept, tipo, fecha_str,
                        check_ins[0], check_outs[-1], res
                    ))
                continue

            break_outs = [t for t, s in day_punches if s == 'Break Out']
            break_ins  = [t for t, s in day_punches if s == 'Break In']

            if break_outs and break_ins and check_ins and dept == 'RECEPCION':
                entry_principal = t2m(check_ins[-1])
                outs_post = [t for t in check_outs if t2m(t) > entry_principal]
                todos_rec = sorted(
                    check_ins +
                    [t for t, s in day_punches if s in ('Break Out', 'Break In')],
                    key=lambda x: t2m(x)
                )
                next_day = d + timedelta(days=1)
                next_punches = punches_map.get((eid, next_day), [])
                next_outs = sorted(
                    [t for t, s in next_punches if s in CHECK_OUT_STATES],
                    key=lambda x: t2m(x)
                )
                if next_outs:
                    res = recepcion.calcular(
                        fecha_str, todos_rec,
                        es_nocturno=True, exit_str=next_outs[0],
                        es_confianza=is_conf
                    )
                    records.append(make_record(
                        eid, first, last, dept, tipo, fecha_str,
                        check_ins[-1], next_outs[0], res
                    ))
                elif outs_post:
                    res = recepcion.calcular(
                        fecha_str, todos_rec,
                        es_confianza=is_conf
                    )
                    records.append(make_record(
                        eid, first, last, dept, tipo, fecha_str,
                        check_ins[-1], outs_post[-1], res
                    ))
                else:
                    res = empty('Sin salida — Andry ajusta',
                                f'Entrada: {check_ins[-1]}',
                                entry_red=check_ins[-1], exit_red='?')
                    records.append(make_record(
                        eid, first, last, dept, tipo, fecha_str,
                        check_ins[-1], '?', res
                    ))
                continue

            salidas_usadas = set()
            turnos_dia     = []

            for entry_t in check_ins:
                entry_m   = t2m(entry_t)
                best_exit = None
                best_diff = 999999

                for i, exit_t in enumerate(check_outs):
                    if i in salidas_usadas: continue
                    exit_m = t2m(exit_t)
                    exit_m_adj = exit_m + 24 * 60 if exit_m < entry_m else exit_m
                    diff = exit_m_adj - entry_m
                    if 0 < diff < best_diff:
                        best_diff = diff
                        best_exit = (i, exit_t)

                if best_exit:
                    salidas_usadas.add(best_exit[0])
                    turnos_dia.append((entry_t, best_exit[1]))
                else:
                    turnos_dia.append((entry_t, None))

            for entry_t, exit_t in turnos_dia:
                if exit_t is None:
                    next_day     = d + timedelta(days=1)
                    next_punches = punches_map.get((eid, next_day), [])
                    next_outs    = sorted(
                        [t for t, s in next_punches if s in CHECK_OUT_STATES],
                        key=lambda x: t2m(x)
                    )
                    if next_outs:
    exit_t = next_outs[0]
    if eid == 141:
        print(f"DEBUG 141 | fecha={fecha_str} | entry_t={entry_t} | exit_t={exit_t} | todos={todos}")
    res = calcular_resultado(
        dept, fecha_str,
        [entry_t], todos,
        tipo, is_conf,
        es_nocturno=True, exit_str=exit_t,
        eid=eid
    )
    records.append(make_record(
        eid, first, last, dept, tipo,
        fecha_str, entry_t, exit_t, res
    ))
                        ))
                    else:
                        res = empty('Sin salida — Andry ajusta',
                                    f'Entrada: {entry_t}',
                                    entry_red=entry_t, exit_red='?')
                        records.append(make_record(
                            eid, first, last, dept, tipo,
                            fecha_str, entry_t, '?', res
                        ))
                else:
                    es_noc = t2m(exit_t) < t2m(entry_t)
                    res = calcular_resultado(
                        dept, fecha_str,
                        [entry_t, exit_t], todos,
                        tipo, is_conf,
                        es_nocturno=es_noc,
                        exit_str=exit_t if es_noc else None,
                        eid=eid
                    )
                    records.append(make_record(
                        eid, first, last, dept, tipo,
                        fecha_str, entry_t, exit_t, res
                    ))

    return pd.DataFrame(records)


# ── VALIDADOR DE FECHAS ──────────────────────────────────────

def validar_fechas(biotime_path: str, fecha_inicio: str, fecha_fin: str) -> dict:
    df = pd.read_excel(biotime_path, header=None, skiprows=1)
    df.columns = [
        'Employee_ID', 'First_Name', 'Last_Name', 'Nick_Name', 'Gender',
        'Dept_Code', 'Department', 'Position_Code', 'Position', 'Date', 'Time',
        'Punch_State', 'Temperature', 'With_Mask', 'Verify_Type',
        'Work_Code', 'Data_Sources'
    ]
    df = df[df['Date'] != 'Date'].copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])

    bt_inicio = df['Date'].min().date()
    bt_fin    = df['Date'].max().date()

    fi = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    ff = datetime.strptime(fecha_fin,    '%Y-%m-%d').date()

    advertencia      = None
    sin_interseccion = False

    if ff < bt_inicio or fi > bt_fin:
        sin_interseccion = True
    elif fi < bt_inicio or ff > bt_fin:
        advertencia = (
            f"Las fechas ingresadas ({fecha_inicio} al {fecha_fin}) "
            f"están parcialmente fuera del rango del archivo BioTime "
            f"({bt_inicio} al {bt_fin}). El reporte solo incluye los días disponibles."
        )

    return {
        'ok':               not sin_interseccion,
        'sin_interseccion': sin_interseccion,
        'biotime_inicio':   str(bt_inicio),
        'biotime_fin':      str(bt_fin),
        'advertencia':      advertencia,
    }


# ── VALIDADOR DE IDs ─────────────────────────────────────────

def validar_ids(biotime_path: str) -> list:
    df = pd.read_excel(biotime_path, header=None, skiprows=1)
    df.columns = [
        'Employee_ID', 'First_Name', 'Last_Name', 'Nick_Name', 'Gender',
        'Dept_Code', 'Department', 'Position_Code', 'Position', 'Date', 'Time',
        'Punch_State', 'Temperature', 'With_Mask', 'Verify_Type',
        'Work_Code', 'Data_Sources'
    ]
    df = df[df['Date'] != 'Date'].copy()
    df['Employee_ID'] = pd.to_numeric(df['Employee_ID'], errors='coerce')

    sin_id = df[df['Employee_ID'].isna()].copy()
    sin_id = sin_id.dropna(subset=['First_Name'])
    sin_id = sin_id[sin_id['First_Name'].str.strip() != '']

    faltantes = []
    for _, r in sin_id.drop_duplicates(subset=['First_Name']).iterrows():
        nombre = str(r['First_Name']).strip()
        faltantes.append(nombre)

    return faltantes


# ── MAIN ─────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    biotime = sys.argv[1] if len(sys.argv) > 1 else 'biotime.xlsx'
    emp     = sys.argv[2] if len(sys.argv) > 2 else 'empleados.xlsx'
    fi      = sys.argv[3] if len(sys.argv) > 3 else '2026-04-10'
    ff      = sys.argv[4] if len(sys.argv) > 4 else '2026-04-24'

    print(f"Procesando {biotime} del {fi} al {ff}...")
    df_result = procesar(biotime, emp, fi, ff)

    print(f"Total registros : {len(df_result)}")
    print(f"Empleados       : {df_result['ID'].nunique()}")

    generar_excel(df_result, 'output_nomina.xlsx')
    print("Reporte guardado en output_nomina.xlsx")
