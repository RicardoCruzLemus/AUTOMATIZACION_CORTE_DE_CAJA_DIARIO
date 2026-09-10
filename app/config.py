import os
from dotenv import load_dotenv

# Cargar las variables desde el archivo .env
load_dotenv()

class Config:
    # Servidor de destino
    SERVER_IP = os.getenv('SERVER_IP', '')
    USERNAME = os.getenv('SERVER_USERNAME', '')
    PASSWORD = os.getenv('SERVER_PASSWORD', '')

    # Rutas
    SOURCE_DIR = os.getenv('SOURCE_DIR', r'C:\Users\inforcruz\Documents\Cortes_de_Caja')
    
    # La ruta UNC de destino (usando la carpeta compartida)
    DEST_DIR = os.getenv('DEST_DIR', r'')
    
    # Recurso base para autenticacion
    IPC_SHARE = os.getenv('IPC_SHARE', r'')

    # Configuraciones de Email (Microsoft Graph API - OAUTH2)
    TENANT_ID = os.getenv('TENANT_ID')
    CLIENT_ID = os.getenv('CLIENT_ID')
    AUTH_MODE = os.getenv('AUTH_MODE', 'delegated')
    ACCOUNT_USERNAME = os.getenv('ACCOUNT_USERNAME')
    
    # Tiempo de espera entre lecturas (en segundos, ej: 60 = 1 minuto)
    EMAIL_CHECK_INTERVAL = 60

    @staticmethod
    def init_app():
        # Nos aseguramos de que el directorio base de origen exista
        os.makedirs(Config.SOURCE_DIR, exist_ok=True)
