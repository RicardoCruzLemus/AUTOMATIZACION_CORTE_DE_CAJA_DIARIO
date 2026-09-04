import os
import time
import logging
import re
import json
import base64
from datetime import datetime, timedelta
import msal
import requests
from pathlib import Path
from app.config import Config
from app.services.watcher import authenticate, append_log

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Ruta absoluta para el archivo de correos procesados y token de MSAL
PROCESADOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'correos_procesados.json')
TOKEN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.token_cache.json')

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES_DELEGADOS = ["Mail.Read"] # Se redujo de ReadWrite a Read para evitar el bloqueo del Administrador

MONTHS = {
    '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
    '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
    '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
}

# ==========================================
# CLASES PARA OAUTH2 Y MICROSOFT GRAPH API
# ==========================================
class Autenticador:
    def __init__(self, tenant, client_id, usuario_esperado):
        self.authority = f"https://login.microsoftonline.com/{tenant}"
        self.usuario_esperado = (usuario_esperado or "").strip().lower() or None
        self.archivo_cache = Path(TOKEN_CACHE_FILE)
        
        self.cache = msal.SerializableTokenCache()
        if self.archivo_cache.exists():
            self.cache.deserialize(self.archivo_cache.read_text(encoding="utf-8"))
            
        self.app = msal.PublicClientApplication(
            client_id, authority=self.authority, token_cache=self.cache)

    def _guardar_cache(self):
        if self.cache.has_state_changed:
            self.archivo_cache.write_text(self.cache.serialize(), encoding="utf-8")

    def obtener_token(self):
        cuentas = self.app.get_accounts()
        cuenta = None
        if self.usuario_esperado and cuentas:
            for c in cuentas:
                if (c.get("username") or "").lower() == self.usuario_esperado:
                    cuenta = c
                    break
        elif cuentas:
            cuenta = cuentas[0]
            
        resultado = None
        if cuenta:
            # Intento de login silencioso con token guardado
            resultado = self.app.acquire_token_silent(SCOPES_DELEGADOS, account=cuenta)
            
        if not resultado:
            # Flujo de Dispositivo (Device Code Flow) - Pide login interactivo en navegador
            flujo = self.app.initiate_device_flow(scopes=SCOPES_DELEGADOS)
            if "user_code" not in flujo:
                raise Exception(f"No se pudo iniciar device code flow: {flujo}")
            logging.warning("\n" + "=" * 70)
            logging.warning(">>> AUTENTICACION REQUERIDA (OAUTH2) <<<")
            logging.warning(flujo["message"])
            if self.usuario_esperado:
                logging.warning(f"    Inicia sesion con: {self.usuario_esperado}")
            logging.warning("=" * 70 + "\n")
            resultado = self.app.acquire_token_by_device_flow(flujo)
            
        self._guardar_cache()
        if "access_token" not in resultado:
            raise Exception(f"Fallo de autenticacion: {resultado.get('error_description', resultado)}")
            
        return resultado["access_token"]


class ClienteGraph:
    def __init__(self, token):
        self.token = token
        self.base = f"{GRAPH_URL}/me"
        self.sesion = requests.Session()
        self.sesion.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        })

    def get(self, endpoint, params=None):
        url = f"{self.base}{endpoint}"
        r = self.sesion.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
        
    def patch(self, endpoint, json_data):
        url = f"{self.base}{endpoint}"
        r = self.sesion.patch(url, json=json_data, timeout=30)
        r.raise_for_status()
        return r.json()
# ==========================================


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

# ==========================================
# MARCA DE AGUA (HIGH WATERMARK)
# Guarda el receivedDateTime del correo más reciente visto.
# En cada ciclo solo se piden correos DESPUES de este momento.
# Esto elimina la necesidad de una ventana de días fija.
# ==========================================
WATERMARK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watermark.json')

def load_watermark():
    """Carga la fecha del último correo procesado. Si no existe, usa hace 2 días como inicio seguro."""
    if os.path.exists(WATERMARK_FILE):
        try:
            with open(WATERMARK_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_seen', None)
        except Exception:
            pass
    # Primera vez: arranca desde hace 2 dias para no perderse nada reciente
    fallback = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return fallback

def save_watermark(received_datetime_str):
    """Guarda la fecha del correo más reciente como nueva marca de agua."""
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
    # Validacion: No arrancar conexión si falta Configuración de TI
    if not Config.TENANT_ID or not Config.CLIENT_ID or "00000000" in Config.TENANT_ID:
        logging.warning("Esperando a que TI proporcione CLIENT_ID y TENANT_ID reales en el archivo .env...")
        return
        
    try:
        logging.info("Verificando sesion OAuth2 de Microsoft Graph...")
        auth = Autenticador(Config.TENANT_ID, Config.CLIENT_ID, Config.ACCOUNT_USERNAME)
        token = auth.obtener_token()
        graph = ClienteGraph(token)
        
        # MARCA DE AGUA: solo pedimos correos NUEVOS desde la ultima vez que revisamos
        # Esto garantiza que la consulta siempre devuelva pocos correos (solo los nuevos)
        # sin importar cuantos correos historicos tenga la bandeja
        watermark = load_watermark()
        # Buffer de 2 minutos para atrapar correos que llegan ligeramente fuera de orden
        watermark_dt = datetime.strptime(watermark, '%Y-%m-%dT%H:%M:%SZ') - timedelta(minutes=2)
        desde = watermark_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        params = {
            "$select": "id,internetMessageId,subject,receivedDateTime,hasAttachments",
            "$orderby": "receivedDateTime asc",  # Mas antiguo primero para avanzar la marca en orden
            "$top": "50",  # 50 es mas que suficiente para un ciclo de 60 segundos
            "$filter": f"receivedDateTime ge {desde}"
        }
        resp = graph.get("/mailFolders/inbox/messages", params=params)
        correos = resp.get("value", [])
        
        if not correos:
            logging.info("Bandeja revisada. No hay correos nuevos.")
            return
            
        procesados = load_procesados()
        nuevos = 0
        omitidos = 0
        
        for msg in correos:
            msg_id = msg.get("internetMessageId")
            graph_id = msg.get("id")
            subject = msg.get("subject", "")
            has_attachments = msg.get("hasAttachments", False)
            
            if msg_id in procesados:
                omitidos += 1
                continue
                
            nuevos += 1
            logging.info(f"Leyendo correo: {subject}")
            
            keywords = ['corte', 'cuadre', 'caja', 'cort', 'cuadr', 'cadre', 'crte']
            if not any(word in subject.lower() for word in keywords):
                logging.warning(f"Asunto sin palabra clave: {subject}. Ignorando.")
                if msg_id: save_procesado(msg_id)
                # Ya no podemos marcar como leido por falta de permisos (Mail.ReadWrite)
                continue
                
            date_str = extract_date(subject)
            company = extract_company(subject)
            
            if not date_str:
                logging.warning(f"No se encontro fecha valida en el asunto: {subject}. Saltando adjuntos.")
                if msg_id: save_procesado(msg_id)
                continue
                
            if not has_attachments:
                logging.warning(f"El correo {subject} no tiene adjuntos. Ignorando.")
                if msg_id: save_procesado(msg_id)
                continue
                
            # Autenticar red local
            try:
                authenticate()
            except Exception as e:
                logging.error(f"Error de autenticacion con el servidor local para guardar adjuntos: {str(e)}")
                continue
                
            # 2. Descargar adjuntos vía Graph API
            adjuntos_resp = graph.get(f"/messages/{graph_id}/attachments")
            adjuntos = adjuntos_resp.get("value", [])
            
            if msg_id: save_procesado(msg_id)
            
            for att in adjuntos:
                # Solo queremos adjuntos de archivos físicos
                if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                    continue
                    
                subject = msg.get("subject", "Sin asunto")
                filename = att.get("name", "")
                content_bytes = att.get("contentBytes", "")
                
                filename = sanitize_filename(filename)
                
                if filename.lower().endswith(('.pdf', '.xls', '.xlsx', '.xlsm')):
                    day, month, year = date_str.split('-')
                    month_name = MONTHS.get(month, month)
                    
                    dest_folder = os.path.join(Config.DEST_DIR, company, year, month_name, date_str)
                    os.makedirs(dest_folder, exist_ok=True)
                    
                    unique_filename = get_unique_filename(dest_folder, filename)
                    filepath = os.path.join(dest_folder, unique_filename)
                    
                    try:
                        # Decodificar el archivo que viene en Base64 desde Microsoft
                        with open(filepath, 'wb') as f:
                            f.write(base64.b64decode(content_bytes))
                            
                        msg_log = f"Guardado desde correo (Graph) como {unique_filename} en {company}/{year}/{month_name}/{date_str}"
                        logging.info(msg_log)
                        append_log(filename, "EXITO", msg_log, destino=dest_folder, asunto=subject)
                    except Exception as e:
                        msg_log = f"Error al guardar adjunto en el servidor local: {str(e)}"
                        logging.error(msg_log)
                        append_log(filename, "ERROR", msg_log, asunto=subject)
                else:
                    msg_log = f"Archivo ignorado por extension no permitida en {company}/{date_str}"
                    logging.info(f"[{filename}] {msg_log}")
                    append_log(filename, "IGNORADO", msg_log, asunto=subject)

        # Actualizar la marca de agua al correo mas reciente del ciclo
        if correos:
            ultima_fecha = correos[-1].get("receivedDateTime")  # El mas reciente (asc)
            if ultima_fecha:
                # Normalizar formato: '2026-09-04T20:18:01Z' o '2026-09-04T20:18:01+00:00'
                ultima_fecha_utc = ultima_fecha.replace('+00:00', 'Z').split('.')[0]
                if not ultima_fecha_utc.endswith('Z'):
                    ultima_fecha_utc += 'Z'
                save_watermark(ultima_fecha_utc)

        if nuevos == 0 and omitidos > 0:
            logging.info(f"Bandeja revisada. Se omitieron {omitidos} correos ya procesados. Esperando nuevos correos...")
        elif nuevos == 0 and omitidos == 0:
            logging.info("Bandeja revisada. No hay correos nuevos.")
        elif nuevos > 0:
            logging.info(f"Bandeja revisada. {nuevos} nuevos analizados, {omitidos} omitidos.")

    except Exception as e:
        logging.error(f"Error en el servicio de correos Microsoft Graph: {str(e)}", exc_info=True)

def start_email_service():
    logging.info("Servicio de Correos (OAUTH2) iniciado.")
    while True:
        check_emails()
        time.sleep(Config.EMAIL_CHECK_INTERVAL)
