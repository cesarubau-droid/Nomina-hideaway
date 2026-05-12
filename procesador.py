# ============================================================
# PROCESADOR v3.1 — Fix turno quebrado (Break Out / Break In)
# Hotel Rio Celeste Hideaway
# ============================================================

import pandas as pd
from datetime import datetime, timedelta
from calculador import calcular_dia, t2m, r2
from calculador_nocturno import calcular_nocturno
from generador_excel import generar_excel
from config import FERIADOS, COMPENSADO_DEPTS, CONFIANZA_NOMBRES, SPLIT_DEPTS

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
    2:   ('RH',               False),
    22:  ('SOSTENIBILIDAD',   False),
    47:  ('PROVEEDURIA',      False),
    54:  ('PROVEEDURIA',      False),
    65:  ('PROVEEDURIA',      True),
    84:  ('CONTABILIDAD',     False),
    1:   ('PROVEEDURIA',      False),
    138: ('AMA DE LLAVES',    True),
    141: ('ALIMENTOS COCINA', True),
    121: ('AMA DE LLAVES',    True),
    62:  ('RESTAURANTE SALON',True),
    35:  ('RESTAURANTE SALON',True),
    76:  ('RESTAURANTE SALON',True),
    12:  ('AMA DE LLAVES',    True),
    40:  ('RESTAURANTE SALON',True),
    112: ('RESTAURANTE SALON',True),
    34:  ('RESTAURANTE SALON',True),
    36:  ('RESTAURANTE SALON',True),
}

# v3.1: Solo Check In/Out para entrada/salida principal
# Break In/Out se manejan aparte para turnos quebrados
CHECK_IN_STATES  = {'Check In', 'Overtime In'}
CHECK_OUT_STATES = {'Check Out', 'Overtime Out'}
BREAK_OUT_STATES = {'Break Out'}
BREAK_IN_STATES  = {'Break In'}

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
    return any(c in f"{first} {last}".strip().lower() for c in CONFIANZA_NOMBRES)

def cargar_empleados(emp_path):
    df = pd.read_excel(emp_path)
    df['Employee_ID'] = df['Employee_ID'].astype(int)
    return dict(zip(df['Employee_ID'], df['Tipo']))

def leer_biotime(biotime_path):
    """Lee el archivo de BioTime con el nuevo formato (skiprows=1)."""
    df = pd.read_excel(biotime_path, header=None, skiprows=1)
    df.columns = [
        'Employee_ID','First_Name','Last_Name','Nick_Name','Gender',
        'Dept_Code','Department','Position_Code','Position','Date','Time',
        'Punch_State','Temperature','With_Mask','Verify_Type','Work_Code','Data_Sources'
    ]
    df = df[df['Date'] != 'Date'].copy()
    df = df.dropna(subset=['Time'])
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Time'] = df['Time'].apply(lambda x: str(x)[:5] if x else None)
    df['Employee_ID'] = pd.to_numeric(df['Employee_ID'], errors='coerce')
    df = df.sort_values(['Employee_ID','Date','Time']).reset_index(drop=True)
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

def construir_punches_quebrado(day_punches):
    """
    v3.1 — Para turnos quebrados (SPLIT_DEPTS):
    Reconstruye la secuencia real de horas ignorando el tipo de punch.
    Retorna lista ordenada de horas ['HH:MM', ...] para pasarle a calcular_dia.
    
    Lógica:
    - Check In / Break In  → marcas de presencia
    - Check Out / Break Out → marcas de presencia
    - Se ordenan todas por hora y se pasan como punches crudos
    - calcular_dia → detect_split se encarga de identificar el quebrado
    """
    todas = sorted(day_punches, key=lambda x: t2m(x[0]))
    return [t for t, s in todas]

def procesar(biotime_path, emp_path, fecha_inicio, fecha_fin):
    df = leer_biotime(biotime_path)
    emp_tipos = cargar_empleados(emp_path)

    fi_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    ff_date = datetime.strptime(fecha_fin,    '%Y-%m-%d').date()

    emp_info = {}
    turnos   = {}  # (eid, date) → lista de (time, state)

    for _, row in df.iterrows():
        eid  = row['Employee_ID']
        if pd.isna(eid): continue
        eid  = int(eid)
        date = row['Date'].date()
        time = row['Time']
        state = str(row['Punch_State']).strip()
        bdept = str(row['Department'])

        if eid not in emp_info:
            emp_info[eid] = {
                'first': str(row['First_Name']),
                'last':  str(row['Last_Name']),
                'bdept': bdept,
            }

        key = (eid, date)
        turnos.setdefault(key, [])
        turnos[key].append((time, state))

    records = []
    emp_set = set(eid for (eid, d) in turnos if fi_date <= d <= ff_date)

    all_dates = []
    d = fi_date
    while d <= ff_date:
        all_dates.append(d)
        d += timedelta(days=1)

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
        is_conf    = es_confianza(first, last, tipo)
        if is_conf: tipo = 'Confianza'

        for d in all_dates:
            fecha_str   = d.strftime('%Y-%m-%d')
            day_punches = turnos.get((eid, d), [])

            if not day_punches:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            # ── TURNO QUEBRADO (SPLIT_DEPTS) ─────────────────────────
            # v3.1: Para quebrados, todas las marcas son punches de presencia.
            # Se pasan ordenadas a calcular_dia → detect_split resuelve el quebrado.
            # Break Out del final del B1 y Break In del inicio del B2
            # se incluyen como marcas adicionales — detect_split usa el gap para
            # encontrar la división correcta.
            if dept in SPLIT_DEPTS:
                todas = sorted(day_punches, key=lambda x: t2m(x[0]))
                todas_t = [t for t, s in todas]

                # Verificar si hay Check In en este día
                check_ins  = [t for t, s in todas if s in CHECK_IN_STATES]
                check_outs = [t for t, s in todas if s in CHECK_OUT_STATES]

                if not check_ins and not check_outs:
                    # Solo breaks sueltos — salidas de nocturno anterior, libre
                    records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                    continue

                if not check_ins and check_outs:
                    # Solo Check Out sin Check In → salidas de turno anterior
                    records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                    continue

                # Hay al menos un Check In → procesar
                entry_t = check_ins[0]

                # Buscar Check Out: primero en este día, si no en el siguiente
                if check_outs:
                    exit_t = check_outs[-1]
                    # Incluir todos los punches del día para detect_split
                    res = calcular_dia(fecha_str, todas_t, dept, tipo)
                    records.append(make_record(
                        eid, first, last, dept, tipo,
                        fecha_str, entry_t, exit_t, res))
                else:
                    # Sin Check Out hoy → buscar en día siguiente
                    next_day = d + timedelta(days=1)
                    next_punches = turnos.get((eid, next_day), [])
                    next_outs = [t for t, s in next_punches if s in CHECK_OUT_STATES]
                    next_outs.sort(key=lambda x: t2m(x))

                    if next_outs:
                        exit_t = next_outs[0]
                        if t2m(exit_t) < t2m(entry_t):
                            res = calcular_nocturno(fecha_str, entry_t, exit_t, dept)
                        else:
                            res = calcular_dia(fecha_str, todas_t + [exit_t], dept, tipo)
                        records.append(make_record(
                            eid, first, last, dept, tipo,
                            fecha_str, entry_t, exit_t, res))
                    else:
                        from calculador import empty
                        res = empty('Sin salida — Andry ajusta',
                                   f'Entrada: {entry_t}',
                                   entry_red=entry_t, exit_red='?')
                        records.append(make_record(
                            eid, first, last, dept, tipo,
                            fecha_str, entry_t, '?', res))
                continue

            # ── RESTO DE DEPARTAMENTOS (no quebrados) ────────────────
            entradas = [(t, s) for t, s in day_punches if s in CHECK_IN_STATES]
            salidas  = [(t, s) for t, s in day_punches if s in CHECK_OUT_STATES]

            if not entradas and not salidas:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            if entradas and salidas:
                entradas.sort(key=lambda x: t2m(x[0]))
                salidas.sort(key=lambda x: t2m(x[0]))

                turnos_dia = []
                salidas_usadas = set()
                for entry_t, entry_s in entradas:
                    entry_m = t2m(entry_t)
                    best_exit = None
                    best_diff = 999999
                    for i, (exit_t, exit_s) in enumerate(salidas):
                        if i in salidas_usadas: continue
                        exit_m = t2m(exit_t)
                        if exit_m < entry_m:
                            exit_m_adj = exit_m + 24*60
                        else:
                            exit_m_adj = exit_m
                        diff = exit_m_adj - entry_m
                        if 0 < diff < best_diff:
                            best_diff = diff
                            best_exit = (i, exit_t)
                    if best_exit:
                        salidas_usadas.add(best_exit[0])
                        turnos_dia.append((entry_t, best_exit[1]))
                    else:
                        turnos_dia.append((entry_t, None))

            elif entradas and not salidas:
                turnos_dia = [(t, None) for t, s in entradas]
            else:
                records.append(make_libre(eid, first, last, dept, tipo, fecha_str))
                continue

            for entry_t, exit_t in turnos_dia:
                if exit_t is None:
                    next_day = d + timedelta(days=1)
                    next_punches = turnos.get((eid, next_day), [])
                    next_outs = [(t,s) for t,s in next_punches if s in CHECK_OUT_STATES]
                    next_outs.sort(key=lambda x: t2m(x[0]))

                    if next_outs:
                        exit_t = next_outs[0][0]
                        res = calcular_nocturno(fecha_str, entry_t, exit_t, dept)
                        records.append(make_record(eid, first, last, dept, tipo,
                                                   fecha_str, entry_t, exit_t, res))
                    else:
                        from calculador import empty
                        res = empty('Sin salida — Andry ajusta',
                                   f'Entrada: {entry_t}',
                                   entry_red=entry_t, exit_red='?')
                        records.append(make_record(eid, first, last, dept, tipo,
                                                   fecha_str, entry_t, '?', res))
                else:
                    if t2m(exit_t) < t2m(entry_t):
                        res = calcular_nocturno(fecha_str, entry_t, exit_t, dept)
                    else:
                        res = calcular_dia(fecha_str, [entry_t, exit_t], dept, tipo)
                    records.append(make_record(eid, first, last, dept, tipo,
                                               fecha_str, entry_t, exit_t, res))

    return pd.DataFrame(records)


if __name__ == '__main__':
    import sys

    biotime = sys.argv[1] if len(sys.argv) > 1 else 'biotime.xlsx'
    emp     = sys.argv[2] if len(sys.argv) > 2 else 'empleados.xlsx'
    fi      = sys.argv[3] if len(sys.argv) > 3 else '2026-04-10'
    ff      = sys.argv[4] if len(sys.argv) > 4 else '2026-04-24'

    print(f"Procesando {biotime} del {fi} al {ff}...")
    df = procesar(biotime, emp, fi, ff)

    print(f"\nTotal registros: {len(df)}")
    print(f"Empleados: {df['ID'].nunique()}")

    generar_excel(df, 'output_nomina.xlsx')
    print("\nReporte guardado.")
