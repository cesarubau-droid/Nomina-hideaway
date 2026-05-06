# ============================================================
# PROCESADOR — Lee BioTime + empleados.xlsx → Calcula nómina
# Hotel Rio Celeste Hideaway | Versión 2.3
# ============================================================

import pandas as pd
from datetime import datetime, timedelta
from calculador import calcular_dia, t2m, clean_punches, r2
from calculador_nocturno import calcular_nocturno
from generador_excel import generar_excel
from config import FERIADOS, COMPENSADO_DEPTS, DEPT_STARTS, CONFIANZA_NOMBRES

NOCTURNO_ENTRY = 22 * 60

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


def normalizar_dept(biotime_dept, eid):
    d = str(biotime_dept).strip().upper()
    if d in DEPT_MAP:
        return DEPT_MAP[d]
    if eid in EMP_MAP:
        return EMP_MAP[eid][0]
    return None


def get_tipo(eid, biotime_dept, tipo_excel):
    dept = normalizar_dept(biotime_dept, eid)
    if dept in COMPENSADO_DEPTS:
        return 'Compensado'
    if eid in EMP_MAP and EMP_MAP[eid][1]:
        return 'Por Horas'
    return tipo_excel


def es_confianza(first, last, tipo_excel):
    if tipo_excel == 'Confianza':
        return True
    return any(c in f"{first} {last}".strip().lower() for c in CONFIANZA_NOMBRES)


def es_nocturno(entry_m, dept):
    return dept in ('SEGURIDAD', 'RECEPCION') and entry_m >= NOCTURNO_ENTRY


def cargar_empleados(emp_path):
    df = pd.read_excel(emp_path)
    df['Employee_ID'] = df['Employee_ID'].astype(int)
    return dict(zip(df['Employee_ID'], df['Tipo']))


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


def procesar(biotime_path, emp_path, fecha_inicio, fecha_fin):
    df = pd.read_excel(biotime_path, sheet_name=0, header=None, skiprows=2)
    df.columns = [
        'Employee_ID','First_Name','Last_Name','Nick_Name','Gender',
        'Dept_Code','Department','Position_Code','Position','Date','Time',
        'Punch_State','Temperature','With_Mask','Verify_Type',
        'Work_Code','Data_Sources'
    ]
    df = df.dropna(subset=['Employee_ID'])
    df['Employee_ID'] = df['Employee_ID'].astype(int)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(['Employee_ID','Date','Time']).reset_index(drop=True)

    emp_tipos = cargar_empleados(emp_path)

    fi = datetime.strptime(fecha_inicio, '%Y-%m-%d') - timedelta(days=1)
    ff = datetime.strptime(fecha_fin,    '%Y-%m-%d') + timedelta(days=1)
    df_wide = df[(df['Date'] >= fi) & (df['Date'] <= ff)]

    all_punches = {}
    emp_info    = {}
    for _, row in df_wide.iterrows():
        eid  = int(row['Employee_ID'])
        date = row['Date'].date()
        key  = (eid, date)
        all_punches.setdefault(key, [])
        all_punches[key].append(str(row['Time']))
        if eid not in emp_info:
            emp_info[eid] = {
                'first':        str(row['First_Name']),
                'last':         str(row['Last_Name']),
                'biotime_dept': str(row['Department']),
            }

    for k in all_punches:
        all_punches[k] = clean_punches(
            sorted(all_punches[k], key=lambda x: t2m(x))
        )

    nocturno_exits = set()
    for (eid, d), punches in all_punches.items():
        if not punches: continue
        dept = normalizar_dept(emp_info.get(eid, {}).get('biotime_dept', ''), eid)
        if dept and len(punches) == 1 and es_nocturno(t2m(punches[0]), dept):
            nocturno_exits.add((eid, d + timedelta(days=1)))

    fi_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    ff_date = datetime.strptime(fecha_fin,    '%Y-%m-%d').date()

    records = []
    emp_days = {}
    for (eid, d) in all_punches:
        if fi_date <= d <= ff_date:
            emp_days.setdefault(eid, set())
            emp_days[eid].add(d)

    for eid, days in emp_days.items():
        if eid not in emp_info: continue
        info         = emp_info[eid]
        first        = info['first']
        last         = info['last']
        biotime_dept = info['biotime_dept']
        dept         = normalizar_dept(biotime_dept, eid)
        if not dept: continue

        tipo_excel = emp_tipos.get(eid, 'Fijo')
        tipo       = get_tipo(eid, biotime_dept, tipo_excel)
        is_conf    = es_confianza(first, last, tipo)
        if is_conf: tipo = 'Confianza'

        for d in sorted(days):
            punches   = list(all_punches.get((eid, d), []))
            fecha_str = d.strftime('%Y-%m-%d')

            if (eid, d) in nocturno_exits and punches:
                punches = punches[1:]
            if not punches:
                continue

            first_m = t2m(punches[0])

            if es_nocturno(first_m, dept):
                next_day     = d + timedelta(days=1)
                next_punches = all_punches.get((eid, next_day), [])
                exit_punch   = next_punches[0] if next_punches else None

                if exit_punch:
                    res = calcular_nocturno(fecha_str, punches[0], exit_punch, dept)
                    records.append(make_record(eid, first, last, dept, tipo,
                                               fecha_str, punches[0], exit_punch, res))
                else:
                    from calculador import empty
                    res = empty('Sin salida — Andry ajusta',
                                f'Entrada: {punches[0]}',
                                entry_red=punches[0], exit_red='?')
                    records.append(make_record(eid, first, last, dept, tipo,
                                               fecha_str, punches[0], '?', res))

                if len(punches) > 1:
                    extra = punches[1:]
                    if len(extra) >= 2:
                        res2 = calcular_dia(fecha_str, extra, dept, tipo)
                        records.append(make_record(eid, first, last, dept, tipo,
                                                   fecha_str, extra[0], extra[-1], res2))
            else:
                res       = calcular_dia(fecha_str, punches, dept, tipo)
                entry_raw = punches[0] if punches else ''
                exit_raw  = punches[-1] if len(punches) > 1 else '?'
                records.append(make_record(eid, first, last, dept, tipo,
                                           fecha_str, entry_raw, exit_raw, res))

    return pd.DataFrame(records)


if __name__ == '__main__':
    import sys

    biotime = sys.argv[1] if len(sys.argv) > 1 else 'biotime.xlsx'
    emp     = sys.argv[2] if len(sys.argv) > 2 else 'empleados.xlsx'
    fi      = sys.argv[3] if len(sys.argv) > 3 else '2026-03-25'
    ff      = sys.argv[4] if len(sys.argv) > 4 else '2026-04-09'

    print(f"Procesando {biotime} del {fi} al {ff}...")
    df = procesar(biotime, emp, fi, ff)

    print(f"\nTotal registros: {len(df)}")
    print(f"Empleados: {df['ID'].nunique()}")
    print(f"\nResumen por departamento:")
    grp = df.groupby('Departamento')[['Diurnas Ord','Mixtas Ord','Nocturnas Ord',
                                       'Extra Diurnas','Extra Mixtas','Extra Nocturnas']].sum()
    print(grp.round(2).to_string())

    generar_excel(df, 'output_nomina.xlsx')
    print("Listo.")
