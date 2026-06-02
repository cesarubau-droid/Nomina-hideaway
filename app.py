# ============================================================
# FLASK APP — Interfaz web para Andry
# Hotel Rio Celeste Hideaway | Nómina
# ============================================================

import os
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
from procesador import procesar, validar_ids, validar_fechas
from generador_excel import generar_excel

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

UPLOAD_FOLDER  = 'uploads'
OUTPUT_FOLDER  = 'outputs'
EMPLEADOS_PATH = 'empleados.xlsx'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/generar', methods=['POST'])
def generar():
    try:
        if 'biotime' not in request.files:
            return jsonify({'error': 'No se subió ningún archivo.'}), 400

        archivo = request.files['biotime']
        if archivo.filename == '':
            return jsonify({'error': 'No se seleccionó ningún archivo.'}), 400

        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin    = request.form.get('fecha_fin')
        if not fecha_inicio or not fecha_fin:
            return jsonify({'error': 'Por favor ingresá las fechas.'}), 400

        filename     = secure_filename(archivo.filename)
        biotime_path = os.path.join(UPLOAD_FOLDER, filename)
        archivo.save(biotime_path)

        # ── VALIDACIÓN DE IDs FALTANTES ───────────────────────
        faltantes = validar_ids(biotime_path)
        if faltantes:
            lista = '\n'.join(f'• {n}' for n in faltantes)
            return jsonify({
                'error': f'Hay {len(faltantes)} fila(s) sin Employee ID. '
                         f'Completá los siguientes nombres en el archivo antes de subir:\n\n{lista}'
            }), 400

        # ── VALIDACIÓN DE FECHAS ──────────────────────────────
        fechas = validar_fechas(biotime_path, fecha_inicio, fecha_fin)
        advertencia = fechas.get('advertencia')

        # ── PROCESAMIENTO ─────────────────────────────────────
        df = procesar(biotime_path, EMPLEADOS_PATH, fecha_inicio, fecha_fin)

        output_name = f"Nomina_{fecha_inicio}_al_{fecha_fin}.xlsx"
        output_path = os.path.join(OUTPUT_FOLDER, output_name)
        generar_excel(df, output_path)

        return jsonify({
            'success':     True,
            'archivo':     output_name,
            'registros':   len(df),
            'empleados':   int(df['ID'].nunique()),
            'advertencia': advertencia,
            'biotime_rango': f"{fechas['biotime_inicio']} al {fechas['biotime_fin']}",
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/descargar/<nombre>')
def descargar(nombre):
    path = os.path.join(OUTPUT_FOLDER, secure_filename(nombre))
    if not os.path.exists(path):
        return 'Archivo no encontrado.', 404
    return send_file(path, as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
