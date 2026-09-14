import os
import time
import logging
import re
import json
import base64
import unicodedata
import threading
from datetime import datetime, timedelta
from pathlib import Path

from exchangelib import Credentials, Account, Configuration, DELEGATE, HTMLBody
from exchangelib.ewsdatetime import EWSDateTime, EWSTimeZone
from exchangelib.attachments import FileAttachment

from app.config import Config
from app.services.watcher import authenticate, append_log, append_rejected_log

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Ruta absoluta para el archivo de correos procesados y watermark
PROCESADOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'correos_procesados.json')
WATERMARK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watermark.json')

MONTHS = {
    '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
    '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
    '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
}

procesados_lock = threading.Lock()
watermark_lock = threading.Lock()

def load_procesados():
    with procesados_lock:
        if os.path.exists(PROCESADOS_FILE):
            try:
                with open(PROCESADOS_FILE, 'r') as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

def save_procesado(msg_id):
    if not msg_id: return
    with procesados_lock:
        procesados = set()
        if os.path.exists(PROCESADOS_FILE):
            try:
                with open(PROCESADOS_FILE, 'r') as f:
                    procesados = set(json.load(f))
            except Exception:
                pass
        if msg_id not in procesados:
            procesados.add(msg_id)
            with open(PROCESADOS_FILE, 'w') as f:
                json.dump(list(procesados), f)

def load_watermark():
    """Carga la fecha del último correo procesado en UTC. Si no existe, usa hace 2 días."""
    with watermark_lock:
        if os.path.exists(WATERMARK_FILE):
            try:
                with open(WATERMARK_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('last_seen', None)
            except Exception:
                pass
    fallback = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return fallback

def save_watermark(received_datetime_str):
    """Guarda la fecha del correo más reciente como nueva marca de agua."""
    with watermark_lock:
        with open(WATERMARK_FILE, 'w') as f:
            json.dump({'last_seen': received_datetime_str, 'updated': datetime.utcnow().isoformat()}, f)

def extract_date(subject):
    match = re.search(r'(\d{2})[/\-\.](\d{2})[/\-\.](\d{2,4})', subject)
    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            year = f"20{year}"
        return f"{day}-{month}-{year}"
    match = re.search(r'(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)', subject)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
    match = re.search(r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', subject)
    if match:
        return f"{match.group(1)}-{match.group(2)}-20{match.group(3)}"
        
    return None

def extract_company(subject):
    subject_clean = unicodedata.normalize('NFD', subject or '')
    subject_clean = ''.join(c for c in subject_clean if unicodedata.category(c) != 'Mn').lower()
    
    if 'maquipo' in subject_clean:
        return 'MAQUIPOS'
    elif 'vesa' in subject_clean or 'besa' in subject_clean:
        return 'VESA'
    elif 'colaborador' in subject_clean or 'cobrador' in subject_clean:
        return 'Cobradores'
    elif 'mauto' in subject_clean or 'mantenimiento automotriz' in subject_clean:
        return 'Mauto'
    elif re.search(r'(?:mr\.?\s*credit|mister\s*credit)', subject_clean):
        return 'MR. Credit'
    return 'CANELLA'

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def get_unique_filename(destination_dir, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    
    while os.path.exists(os.path.join(destination_dir, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1
        
    return new_filename

def get_exchange_account():
    username = "automatizacionescaja"
    credentials = Credentials(username, Config.EXCHANGE_PASSWORD)
    config = Configuration(server=Config.EXCHANGE_SERVER, credentials=credentials)
    account = Account(primary_smtp_address=Config.EXCHANGE_EMAIL, config=config, autodiscover=False, access_type=DELEGATE)
    return account

# === NUEVAS FUNCIONES DE VALIDACION ===
def validar_asunto(subject):
    if not subject:
        return False, "El asunto está completamente vacío."
    
    # 1. Buscar palabra clave (case-insensitive, ignora tildes)
    keywords = ['corte', 'cuadre', 'caja', 'cort', 'cuadr', 'cadre', 'crte']
    subject_clean = unicodedata.normalize('NFD', subject.lower())
    has_keyword = any(word in subject_clean for word in keywords)
    
    if not has_keyword:
        return False, "El asunto no contiene palabras clave válidas (ej. 'Corte', 'Cuadre', 'Caja')."
        
    # 2. Buscar fecha en cualquier lugar del asunto
    if not extract_date(subject):
        return False, "No se encontró una fecha válida (DD/MM/YYYY o DD-MM-YYYY) en el asunto."
        
    return True, ""

def validar_nombre_archivo(filename):
    if not filename:
        return False
    name, ext = os.path.splitext(filename)
    # 1. Validar extensión permitida (Parámetro 4)
    if ext.lower() not in ['.pdf', '.xls', '.xlsx', '.xlsm']:
        return False
    # 2. Validar formato con al menos 2 guiones: PARTE1 - PARTE2 - PARTE3 (Parámetro 3)
    parts = name.split('-')
    if len(parts) < 3:
        return False
    return True

def enviar_rechazo(msg, errores):
    lista_errores = "".join(f"<li style='margin-bottom: 5px;'>{e}</li>" for e in errores)
    cuerpo_html = f"""
    <html>
    <body>
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 750px; margin: 0 auto; color: #333; line-height: 1.6; border: 1px solid #e1e4e8; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <div style="background-color: #d32f2f; color: white; padding: 20px; text-align: center;">
            <h2 style="margin: 0; font-size: 24px; font-weight: 600;">&#9888;&#65039; Aviso de Rechazo de Corte de Caja</h2>
        </div>
        
        <div style="padding: 30px;">
            <p style="font-size: 16px;">Buen d&iacute;a,</p>
            <p style="font-size: 16px;">El sistema autom&aacute;tico ha detectado que el correo con asunto <strong>"{msg.subject}"</strong> no cumple con los est&aacute;ndares establecidos y <strong>no ha podido ser procesado</strong>.</p>
            
            <div style="background-color: #ffebee; border-left: 4px solid #f44336; padding: 15px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #d32f2f; font-size: 18px;">Motivo(s) del rechazo:</h3>
                <ul style="margin-bottom: 0; color: #b71c1c; font-weight: 500; font-size: 15px;">
                    {lista_errores}
                </ul>
            </div>

            <h3 style="color: #1976d2; border-bottom: 2px solid #bbdefb; padding-bottom: 8px; margin-top: 30px;">&#128203; Lineamientos Correctos</h3>
            <p>Por favor, revisa y corrige tu env&iacute;o bas&aacute;ndote en los siguientes par&aacute;metros oficiales:</p>
            
            <div style="background-color: #f5f7fa; border: 1px solid #e0e6ed; padding: 20px; border-radius: 6px; margin-bottom: 20px;">
                <h4 style="margin-top: 0; color: #2c3e50; font-size: 16px;">1. Formato del Asunto (Env&iacute;o Normal)</h4>
                <p style="margin-top: 5px; font-size: 14px;">Debe contener la palabra clave y la fecha en formato DD/MM/YYYY. Te sugerimos la siguiente estructura:</p>
                <ul style="font-family: monospace; background: white; padding: 10px 10px 10px 30px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; list-style-type: square;">
                    <li style="margin-bottom: 4px;">Corte de Caja, Canella, 03/09/2025</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Vesa, 03/09/2025</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Maquipos, 03/09/2025</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Cobradores, 03/09/2025</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Mister Credit, 03/09/2026</li>
                    <li>Corte de Caja, Mauto, 03/09/2026</li>
                </ul>

                <h4 style="margin-top: 25px; color: #2c3e50; font-size: 16px;">2. Formato del Asunto (Para Correcciones)</h4>
                <p style="margin-top: 5px; font-size: 14px;">Si est&aacute;s enviando una correcci&oacute;n, debes agregar la palabra "Correcci&oacute;n" al final:</p>
                <ul style="font-family: monospace; background: white; padding: 10px 10px 10px 30px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; list-style-type: square;">
                    <li style="margin-bottom: 4px;">Corte de Caja, Canella, 03/09/2025 Correcci&oacute;n</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Vesa, 03/09/2025 Correcci&oacute;n</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Maquipos, 03/09/2025 Correcci&oacute;n</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Cobradores, 03/09/2025 Correcci&oacute;n</li>
                    <li style="margin-bottom: 4px;">Corte de Caja, Mister Credit, 03/09/2026 Correcci&oacute;n</li>
                    <li>Corte de Caja, Mauto, 03/09/2026 Correcci&oacute;n</li>
                </ul>

                <h4 style="margin-top: 25px; color: #2c3e50; font-size: 16px;">3. Nomenclatura de Archivos Adjuntos (PDF o Excel)</h4>
                <p style="margin-top: 5px; font-size: 14px;">El nombre del archivo debe estar separado por guiones (<code>-</code>) siguiendo este orden: <strong>Fecha - Nomenclatura Tienda - Nombre del documento</strong>.</p>
                <ul style="font-family: monospace; background: white; padding: 10px 10px 10px 30px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; list-style-type: square;">
                    <li style="margin-bottom: 4px;">31072026-ABC-CORTE EXCEL.xlsx</li>
                    <li>31072026-ABC-CORTE SAP.pdf</li>
                </ul>
            </div>
            
            <p style="font-size: 15px; font-weight: 600; text-align: center; color: #e65100; padding: 15px; background: #fff3e0; border-radius: 6px;">
                Por favor, vuelve a enviar un NUEVO CORREO cumpliendo estrictamente estos par&aacute;metros para que tu corte sea registrado.
            </p>
        </div>
        
        <div style="background-color: #f1f1f1; color: #777; font-size: 12px; text-align: center; padding: 15px; border-top: 1px solid #ddd;">
            <em>Este es un mensaje autom&aacute;tico generado por el Sistema de Automatizaci&oacute;n de Cortes de Caja.<br>Por favor, no respondas a esta direcci&oacute;n.</em>
        </div>
    </div>
    </body>
    </html>
    """
    try:
        msg.reply_all(
            subject=f"RECHAZADO: Formato incorrecto en tu corte de caja",
            body=HTMLBody(cuerpo_html)
        )
        logging.info(f"Correo de rechazo enviado automáticamente para: {msg.subject}")
    except Exception as e:
        logging.error(f"No se pudo enviar correo de rechazo: {str(e)}")

# =======================================

def check_emails():
    if not Config.EXCHANGE_EMAIL or not Config.EXCHANGE_PASSWORD:
        logging.warning("Faltan credenciales de Exchange en el archivo .env...")
        return
        
    try:
        logging.info("Conectando al servidor OWA local (EWS)...")
        account = get_exchange_account()
        
        watermark = load_watermark()
        # Parse UTC watermark to EWSDateTime
        tz = EWSTimeZone('UTC')
        watermark_dt = datetime.strptime(watermark, '%Y-%m-%dT%H:%M:%SZ') - timedelta(minutes=2)
        ews_desde = EWSDateTime.from_datetime(watermark_dt.replace(tzinfo=tz))
        
        # Filtrar correos desde la marca de agua
        correos = list(account.inbox.filter(datetime_received__gte=ews_desde).order_by('datetime_received')[:50])
        
        if not correos:
            logging.info("Bandeja revisada. No hay correos nuevos.")
            return
            
        procesados = load_procesados()
        nuevos = 0
        omitidos = 0
        
        for msg in correos:
            msg_id = msg.message_id
            subject = msg.subject or "Sin asunto"
            has_attachments = msg.has_attachments
            
            if msg_id in procesados:
                omitidos += 1
                continue
                
            nuevos += 1
            logging.info(f"Leyendo correo: {subject}")
            
            # --- INCIO DE VALIDACIONES ESTRICTAS ---
            errores = []
            
            # Validación 1: Asunto (Flexible - solo busca fecha y palabra clave)
            es_valido, msj_error = validar_asunto(subject)
            if not es_valido:
                errores.append(msj_error)
            
            # Extraemos la fecha y empresa
            date_str = extract_date(subject)
            company = extract_company(subject)
            
            # Validación 2: Archivos adjuntos y sus nombres
            archivos_a_procesar = []
            if not has_attachments:
                errores.append("El correo <strong>no contiene archivos adjuntos</strong>.")
            else:
                archivos_validos = False
                for att in msg.attachments:
                    if isinstance(att, FileAttachment):
                        # Ignorar imagenes comunes de firmas (inline attachments)
                        ext = os.path.splitext(att.name or "")[1].lower()
                        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']:
                            continue # Ignorar silenciosamente las imágenes
                            
                        if not validar_nombre_archivo(att.name):
                            errores.append(
                                f"El archivo <strong>'{att.name}'</strong> no cumple el formato requerido de guiones o la extensión no es Excel/PDF."
                            )
                        else:
                            archivos_validos = True
                            archivos_a_procesar.append(att)
                
                if not archivos_validos and not [e for e in errores if "archivo" in e.lower()]:
                    errores.append("No se encontró ningún archivo físico válido (PDF o Excel).")
                    
            # Si hay errores de validación, rechazamos el correo y NO guardamos nada en red
            if errores:
                logging.warning(f"Correo '{subject}' RECHAZADO por validaciones. Enviando alerta a caja...")
                
                # Nombres de archivos adjuntos (para el log visual en dashboard)
                nombres_archivos = [att.name for att in getattr(msg, 'attachments', []) if isinstance(att, FileAttachment)]
                motivo_limpio = " / ".join(errores).replace("<strong>", "").replace("</strong>", "")
                append_rejected_log(subject, motivo_limpio, nombres_archivos)
                
                enviar_rechazo(msg, errores)
                if msg_id: save_procesado(msg_id)
                continue
            
            # --- FIN DE VALIDACIONES ESTRICTAS ---
            
            # Si llegó aquí, significa que todo es válido y procedemos a guardar en red
            try:
                authenticate()
            except Exception as e:
                logging.error(f"Error de autenticacion con el servidor local para guardar adjuntos: {str(e)}")
                continue
                
            has_error = False
            
            for att in archivos_a_procesar:
                filename = att.name
                content_bytes = att.content
                
                if not content_bytes:
                    continue
                    
                filename = sanitize_filename(filename)
                
                day, month, year = date_str.split('-')
                month_name = MONTHS.get(month, month)
                
                dest_folder = os.path.join(Config.DEST_DIR, company, year, month_name, date_str)
                os.makedirs(dest_folder, exist_ok=True)
                
                unique_filename = get_unique_filename(dest_folder, filename)
                filepath = os.path.join(dest_folder, unique_filename)
                
                try:
                    with open(filepath, 'wb') as f:
                        f.write(content_bytes)
                        
                    msg_log = f"Guardado desde correo (EWS) como {unique_filename} en {company}/{year}/{month_name}/{date_str}"
                    logging.info(msg_log)
                    append_log(filename, "EXITO", msg_log, destino=dest_folder, asunto=subject)
                except Exception as e:
                    msg_log = f"Error al guardar adjunto en el servidor local: {str(e)}"
                    logging.error(msg_log)
                    append_log(filename, "ERROR", msg_log, asunto=subject)
                    has_error = True

            if not has_error and msg_id:
                save_procesado(msg_id)

        # Actualizar la marca de agua
        if correos:
            ultima_fecha = correos[-1].datetime_received
            if ultima_fecha:
                ultima_fecha_utc = ultima_fecha.astimezone(EWSTimeZone('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
                save_watermark(ultima_fecha_utc)

        if nuevos == 0 and omitidos > 0:
            logging.info(f"Bandeja revisada. Se omitieron {omitidos} correos ya procesados. Esperando nuevos correos...")
        elif nuevos > 0:
            logging.info(f"Bandeja revisada. {nuevos} nuevos analizados, {omitidos} omitidos.")

    except Exception as e:
        logging.error(f"Error en el servicio de correos EWS: {str(e)}", exc_info=True)

def start_email_service():
    logging.info("Servicio de Correos (EWS) iniciado con Validación Estricta.")
    while True:
        check_emails()
        time.sleep(Config.EMAIL_CHECK_INTERVAL)
