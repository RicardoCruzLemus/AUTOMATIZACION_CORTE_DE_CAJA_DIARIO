from flask import Blueprint, Response
import os

views_bp = Blueprint('views', __name__)

# Ruta absoluta hardcodeada para eliminar toda ambigüedad
TEMPLATE_PATH = r'C:\Users\inforcruz\Desktop\AUTOMATIZACION_CORTE_DE_CAJA_DIARIO\AUTOMATIZACION_CORTE_DE_CAJA_DIARIO\app\templates\index.html'

print(f"[DASHBOARD] Template path: {TEMPLATE_PATH}")
print(f"[DASHBOARD] File exists: {os.path.exists(TEMPLATE_PATH)}")
print(f"[DASHBOARD] File size: {os.path.getsize(TEMPLATE_PATH)} bytes")

@views_bp.route('/')
def index():
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    print(f"[DASHBOARD] Serving {len(content)} chars")
    return Response(content, mimetype='text/html')

