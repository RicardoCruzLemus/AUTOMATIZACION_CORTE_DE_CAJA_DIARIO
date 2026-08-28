import os
import time
import logging
import imaplib
import email
import email.utils
from email.header import decode_header
import re
import json
from app.config import Config
from app.services.watcher import authenticate, append_log
from app.services.smtp_service import send_confirmation

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

PROCESADOS_FILE = 'correos_procesados.json'

MONTHS = {
    '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
    '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
    '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
}

def load_procesados():
    if os.path.exists(PROCESADOS_FILE):
        try:
            with open(PROCESADOS_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_procesado(msg_id):
    procesados = load_procesados()
    if msg_id and msg_id not in procesados:
        procesados.add(msg_id)
        with open(PROCESADOS_FILE, 'w') as f:
            json.dump(list(procesados), f)

def extract_date(subject):
    # Busca patrones como DD/MM/YYYY o DD-MM-YYYY
    match = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', subject)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None

def extract_company(subject):
    subject_lower = subject.lower()
    if 'maquipo' in subject_lower:
        return 'MAQUIPOS'
    elif 'vesa' in subject_lower or 'besa' in subject_lower:
        return 'VESA'
    elif 'colaborador' in subject_lower or 'cobrador' in subject_lower:
        return 'Cobradores'
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

def check_emails():
    try:
        logging.info("Conectando al servidor IMAP...")
        # Intentar conexión segura (SSL) en el puerto configurado (993)
        try:
            mail = imaplib.IMAP4_SSL(Config.IMAP_SERVER, Config.IMAP_PORT)
        except ConnectionRefusedError:
            logging.warning(f"Conexión rechazada en el puerto {Config.IMAP_PORT}. Intentando puerto estándar 143 (Sin SSL)...")
            mail = imaplib.IMAP4(Config.IMAP_SERVER, 143)
            # A veces los servidores en el puerto 143 requieren STARTTLS
            try:
                mail.starttls()
            except Exception:
                pass # Si no soporta starttls, seguimos con la conexión plana
                
        mail.login(Config.IMAP_USER, Config.IMAP_PASSWORD)
        
        # Seleccionar la bandeja de entrada
        mail.select('inbox')
        
        # Buscar correos no leídos
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            logging.error("Error al buscar correos.")
            return

        email_ids = messages[0].split()
        if not email_ids:
            logging.info("No hay correos nuevos.")
            
        for email_id in email_ids:
            procesados = load_procesados()
            
            # Usar PEEK para no marcar el correo como leído
            status, msg_data = mail.fetch(email_id, '(BODY.PEEK[])')
            if status != 'OK':
                continue
                
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Verificar la libreta de memoria
                    msg_id = msg.get("Message-ID")
                    if msg_id in procesados:
                        continue
                        
                    # Decodificar el asunto
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else 'utf-8', errors='ignore')
                        
                    logging.info(f"Leyendo correo: {subject}")
                    
                    # Validar que el asunto contenga palabras clave (cuadre, corte)
                    if not any(word in subject.lower() for word in ['cuadre', 'corte']):
                        logging.warning(f"Asunto sin palabra clave (cuadre/corte): {subject}. Ignorando.")
                        # Guardar en procesados para no volver a leerlo
                        if msg_id: save_procesado(msg_id)
                        continue
                        
                    date_str = extract_date(subject)
                    company = extract_company(subject)
                    
                    if not date_str:
                        logging.warning(f"No se encontró fecha válida en el asunto: {subject}. Saltando adjuntos.")
                        if msg_id: save_procesado(msg_id)
                        continue
                        
                    # Autenticar con el servidor de red antes de guardar
                    try:
                        authenticate()
                    except Exception as e:
                        logging.error(f"Error de autenticación con el servidor para guardar adjuntos: {str(e)}")
                        continue
                        
                    archivos_exitosos = []
                    
                    # Procesar partes del correo buscando adjuntos
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                            
                        filename = part.get_filename()
                        if filename:
                            # Decodificar el nombre del archivo
                            filename_decoded, encoding = decode_header(filename)[0]
                            if isinstance(filename_decoded, bytes):
                                filename = filename_decoded.decode(encoding if encoding else 'utf-8', errors='ignore')
                                
                            filename = sanitize_filename(filename)
                            
                            # Solo PDFs y Excels
                            if filename.lower().endswith(('.pdf', '.xls', '.xlsx')):
                                # Extraer Año y Mes para enrutamiento histórico
                                day, month, year = date_str.split('-')
                                month_name = MONTHS.get(month, month)
                                
                                # Crear estructura de carpetas: Empresa/Año/Mes/Fecha
                                dest_folder = os.path.join(Config.DEST_DIR, company, year, month_name, date_str)
                                os.makedirs(dest_folder, exist_ok=True)
                                
                                unique_filename = get_unique_filename(dest_folder, filename)
                                filepath = os.path.join(dest_folder, unique_filename)
                                
                                # Guardar archivo directamente en el servidor
                                try:
                                    with open(filepath, 'wb') as f:
                                        f.write(part.get_payload(decode=True))
                                        
                                    msg_log = f"Guardado desde correo como {unique_filename} en {company}/{year}/{month_name}/{date_str}"
                                    logging.info(msg_log)
                                    append_log(filename, "EXITO", msg_log, destino=dest_folder)
                                    archivos_exitosos.append(unique_filename)
                                except Exception as e:
                                    msg_log = f"Error al guardar adjunto en el servidor: {str(e)}"
                                    logging.error(msg_log)
                                    append_log(filename, "ERROR", msg_log)
                            else:
                                msg_log = f"Archivo ignorado por extensión no permitida en {company}/{date_str}"
                                logging.info(f"[{filename}] {msg_log}")
                                append_log(filename, "IGNORADO", msg_log)
                                
            # Enviar correo de confirmación si hubo archivos exitosos
            if archivos_exitosos:
                # El usuario solicitó que la confirmación llegue siempre a ricardocruzprogra@gmail.com
                # en lugar de al remitente original.
                send_confirmation(Config.IMAP_USER, company, date_str, archivos_exitosos)
                                
            # Guardar en la libreta una vez procesado este correo
            if msg_id:
                save_procesado(msg_id)
            
        mail.close()
        mail.logout()
    except Exception as e:
        logging.error(f"Error en el servicio de correos: {str(e)}")

def start_email_service():
    logging.info("Servicio de Correos iniciado.")
    while True:
        check_emails()
        time.sleep(Config.EMAIL_CHECK_INTERVAL)
