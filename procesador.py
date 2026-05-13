import pandas as pd
from datetime import datetime, timedelta

from calculador_base import t2m, empty
from calculadores import seguridad, recepcion, quebrado, estandar, compensado
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
    65:  ('PROVEEDURIA',       True),
    84:  ('CONTABILIDAD',      False),
    # 1: Joseph Arroyo — outsourcing, excluido
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

# Empleados excluidos de la nómina (outsourcing u otros)
EXCLUIDOS = {1}  # Joseph Arroyo — outsourcing

# Punch states
CHECK_IN_STATES  = {'Check In', 'Overtime In'}
CHECK_OUT_STATES = {'Check Out', 'Overtime Out'}
# Break In/Out solo se usan para quebrados — se pasan como punches crudos

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
    df['Time_sort'] = pd.to_numeric(df['Time'].apply(lambda x: int(x[:2])*60+int(x[3:5]) if x and len(x) >= 5 else 0), errors='coerce').fillna(0)
    df['Employee_ID'] = pd.to_numeric(df['Employee_ID'], errors='coerce')
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
                       tipo, is_conf, es_nocturno=False, exit_str=None):
    """
    Llama al calculador correcto según el departamento.

    punches_check: solo Check In / Check Out (para depts normales)
    punches_todos: todas las marcas ordenadas (para quebrados)
    """
    if dept == 'SEGURIDAD':
        return seguridad.calcular(
            fecha_str, punches_check,
            es_nocturno=es_nocturno, exit_str=exit_str,
            es_confianza=is_conf
        )

    if dept == 'RECEPCION':
        return recepcion.calcular(
            fecha_str, punches_check,
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

    # Estándar: Ama de Llaves, Spa, Jardín, Mantenimiento, RH, Proveeduría
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

    # Construir estructura de punches por (eid, date)
    emp_info = {}
    punches_map = {}  # (eid, date) → lista de (time, state)

    for _, row in df.iterrows():
        eid = row['Employee_ID']
        if pd.isna(eid): continue
        eid = int(eid)
        if eid in EXCLUIDOS: continue
        date  = row['Date'].date()
        time  = row['Time']
        state = str(row['Punch_State']).strip()
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

    # Generar lista de fechas del período
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

            # ── SIN MARCACIONES → LIBRE ───────────────────────────
            if not day_punches:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            # ── SEPARAR TIPOS DE PUNCH ────────────────────────────
            check_ins  = sorted(
                [t for t, s in day_punches if s in CHECK_IN_STATES],
                key=lambda x: t2m(x)
            )
            check_outs = sorted(
                [t for t, s in day_punches if s in CHECK_OUT_STATES],
                key=lambda x: t2m(x)
            )
            # Todas las marcas ordenadas (para quebrados)
            todos = sorted(
                [t for t, s in day_punches],
                key=lambda x: t2m(x)
            )

            # ── SOLO SALIDAS SIN ENTRADA → LIBRE ─────────────────
            # Son salidas del turno nocturno del día anterior
            if not check_ins and check_outs:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            # ── SIN CHECK IN NI CHECK OUT ─────────────────────────
            if not check_ins and not check_outs:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            # ── DEPARTAMENTOS QUEBRADOS ───────────────────────────
            # Pasan TODAS las marcas al calculador
            if dept in SPLIT_DEPTS:
                # Si no hay check out hoy → buscar en día siguiente
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
                            tipo, is_conf
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
                        tipo, is_conf
                    )
                    records.append(make_record(
                        eid, first, last, dept, tipo, fecha_str,
                        check_ins[0], check_outs[-1], res
                    ))
                continue

            # ── RESTO DE DEPARTAMENTOS ────────────────────────────
            # Procesar pares Check In → Check Out
            # Un empleado normalmente tiene un solo par por día
            # excepto casos especiales (doble turno, nocturno cruzado)

            salidas_usadas = set()
            turnos_dia     = []

            for entry_t in check_ins:
                entry_m   = t2m(entry_t)
                best_exit = None
                best_diff = 999999

                for i, exit_t in enumerate(check_outs):
                    if i in salidas_usadas: continue
                    exit_m = t2m(exit_t)
                    # Si salida < entrada → cruzó medianoche
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
                    # Buscar salida en el día siguiente
                    next_day     = d + timedelta(days=1)
                    next_punches = punches_map.get((eid, next_day), [])
                    next_outs    = sorted(
                        [t for t, s in next_punches if s in CHECK_OUT_STATES],
                        key=lambda x: t2m(x)
                    )
                    if next_outs:
                        exit_t = next_outs[0]
                        res = calcular_resultado(
                            dept, fecha_str,
                            [entry_t], todos,
                            tipo, is_conf,
                            es_nocturno=True, exit_str=exit_t
                        )
                        records.append(make_record(
                            eid, first, last, dept, tipo,
                            fecha_str, entry_t, exit_t, res
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
                    # Verificar si cruza medianoche
                    es_noc = t2m(exit_t) < t2m(entry_t)
                    res = calcular_resultado(
                        dept, fecha_str,
                        [entry_t, exit_t], todos,
                        tipo, is_conf,
                        es_nocturno=es_noc,
                        exit_str=exit_t if es_noc else None
                    )
                    records.append(make_record(
                        eid, first, last, dept, tipo,
                        fecha_str, entry_t, exit_t, res
                    ))

    return pd.DataFrame(records)


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
