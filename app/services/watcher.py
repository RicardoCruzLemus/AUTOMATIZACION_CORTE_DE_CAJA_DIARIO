import os
import time
import shutil
import subprocess
import json
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
LOG_FILE = 'transfer_logs.json'

def append_log(filename, status, message, destino=''):
    log_entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'filename': filename,
        'status': status,
        'message': message,
        'destino': destino
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            pass
    logs.insert(0, log_entry)  # Add to beginning
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs[:100], f, indent=4)  # Keep only last 100 logs

def get_unique_filename(destination_dir, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    
    while os.path.exists(os.path.join(destination_dir, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1
        
    return new_filename

def authenticate():
    cmd = f'net use "{Config.DEST_DIR}" /user:{Config.USERNAME} "{Config.PASSWORD}"'
    cmd_ipc = f'net use "{Config.IPC_SHARE}" /user:{Config.USERNAME} "{Config.PASSWORD}"'
    
    subprocess.run(cmd_ipc, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0 or b'Multiple connections' in result.stderr

class FileMoveHandler(FileSystemEventHandler):
    def process_file(self, file_path):
        filename = os.path.basename(file_path)
        
        # Solo aceptar PDFs y Excels
        if not filename.lower().endswith(('.pdf', '.xls', '.xlsx')):
            return

        # Ignorar archivos temporales comunes
        if filename.startswith('~') or filename.endswith('.tmp'):
            return

        logging.info(f"Detectado archivo: {filename}")
        time.sleep(2)
        
        try:
            authenticate()
            
            # Obtener ruta relativa para replicar subcarpetas
            rel_path = os.path.relpath(os.path.dirname(file_path), Config.SOURCE_DIR)
            
            # Construir directorio de destino
            dest_dir = Config.DEST_DIR
            if rel_path != '.':
                dest_dir = os.path.join(Config.DEST_DIR, rel_path)
            
            # Crear subcarpetas si no existen
            os.makedirs(dest_dir, exist_ok=True)
            
            dest_filename = get_unique_filename(dest_dir, filename)
            dest_path = os.path.join(dest_dir, dest_filename)
            
            logging.info(f"Moviendo a: {dest_path}")
            shutil.move(file_path, dest_path)
            
            msg = f"Movido exitosamente como {dest_filename}"
            logging.info(msg)
            append_log(filename, "EXITO", msg)
            
        except Exception as e:
            msg = f"Error al mover: {str(e)}"
            logging.error(msg)
            append_log(filename, "ERROR", msg)

    def on_created(self, event):
        if not event.is_directory:
            self.process_file(event.src_path)

def start_watcher():
    Config.init_app()
    
    event_handler = FileMoveHandler()
    
    # Procesar archivos existentes al iniciar de forma recursiva
    logging.info("Procesando archivos existentes...")
    for root_dir, dirs, files in os.walk(Config.SOURCE_DIR):
        for filename in files:
            file_path = os.path.join(root_dir, filename)
            event_handler.process_file(file_path)
            
    observer = Observer()
    observer.schedule(event_handler, Config.SOURCE_DIR, recursive=True)
    observer.start()
    logging.info(f"Observador iniciado en: {Config.SOURCE_DIR}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
