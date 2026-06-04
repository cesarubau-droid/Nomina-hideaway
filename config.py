# ============================================================
# CONFIGURACIÓN — NÓMINA HOTEL RIO CELESTE HIDEAWAY
# Versión: 2.2
# ============================================================

# Regla 20/45
EXTRA_HALF_MIN = 20
EXTRA_FULL_MIN = 45

# Tolerancia entrada y penalización tardío
TOLERANCE_MIN = 10
LATE_PENALTY  = 30

# Duplicados BioTime
DUPLICATE_MIN = 5

# Turno quebrado
SPLIT_GAP_MIN = 4 * 60

# Jornada ordinaria estándar
ORD_HOURS_DEFAULT    = 8
ORD_HOURS_COMPENSADO = 9

# Feriados nacionales Costa Rica 2026
FERIADOS = {
    '2026-01-01': 'Año Nuevo',
    '2026-04-02': 'Jueves Santo',
    '2026-04-03': 'Viernes Santo',
    '2026-04-11': 'Juan Santamaría',
    '2026-04-17': 'Jueves Santo',
    '2026-04-18': 'Viernes Santo',
    '2026-05-01': 'Día del Trabajador',
    '2026-07-25': 'Anexión Guanacaste',
    '2026-08-02': 'Virgen de los Ángeles',
    '2026-08-15': 'Día de la Madre',
    '2026-09-15': 'Independencia',
    '2026-10-12': 'Día de las Culturas',
    '2026-12-25': 'Navidad',
}

# Empleados de confianza (nunca extras)
CONFIANZA_NOMBRES = {
    'minor',
    'nelson ramirez',
    'nelson araya',
    'joselin arguedas',
    'jose abel espinoza',
    'tania rodriguez',
    'maria elena ocampo',
}

# Departamentos compensados (9h ordinarias)
COMPENSADO_DEPTS = {'CONTABILIDAD', 'SOSTENIBILIDAD'}

# Turnos de inicio por departamento (horas)
DEPT_STARTS = {
    'SEGURIDAD':         [6, 8, 15, 16, 22, 23],
    'RECEPCION':         [6, 8, 9, 15, 22],
    'RESTAURANTE SALON': [6, 7, 11, 12, 14, 15, 18],
    'ALIMENTOS COCINA':  [6, 7, 8, 11, 12, 14, 15, 17],
    'AMA DE LLAVES':     [6, 7, 8, 12, 14],
    'SPA':               [6, 9, 10],
    'MANTENIMIENTO':     [6, 7, 8, 9, 10],
    'JARDIN':            [6, 7, 8],
    'PROVEEDURIA':       [6, 7, 8, 10],
    'CONTABILIDAD':      [8],
    'SOSTENIBILIDAD':    [8],
    'RH':                [6, 7, 8],
}

# Seguridad: turnos con y sin acuerdo especial
SEG_ACUERDO_STARTS = [16, 22, 23]  # 6h ord noc + 1h extra noc fija
SEG_SIN_ACUERDO    = [6, 8, 15]   # 8h ord + regla 20/45

# Recepción nocturno
REC_NOCTURNO_START = 22  # 6h ord + 2h extra noc fijas

# Departamentos con turno quebrado
SPLIT_DEPTS = {'ALIMENTOS COCINA', 'RESTAURANTE SALON'}
