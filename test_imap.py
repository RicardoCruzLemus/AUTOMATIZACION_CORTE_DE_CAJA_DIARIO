"""
Script de prueba de conexion IMAP.
Ejecutar con: python test_imap.py
"""
import imaplib
from dotenv import load_dotenv
import os

load_dotenv()

IMAP_SERVER   = os.getenv("IMAP_SERVER")
IMAP_PORT     = int(os.getenv("IMAP_PORT", 993))
IMAP_USER     = os.getenv("IMAP_USER")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

print("=" * 50)
print("  TEST DE CONEXION IMAP")
print("=" * 50)
print(f"  Servidor : {IMAP_SERVER}:{IMAP_PORT}")
print(f"  Usuario  : {IMAP_USER}")
print("=" * 50)

try:
    print("\n[1/3] Conectando al servidor...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    print("      OK - Conexion SSL establecida")

    print("[2/3] Autenticando...")
    mail.login(IMAP_USER, IMAP_PASSWORD)
    print("      OK - Autenticacion exitosa")

    print("[3/3] Buscando correos no leidos...")
    mail.select("inbox")
    status, messages = mail.search(None, "UNSEEN")
    count = len(messages[0].split()) if messages[0] else 0
    print(f"      OK - Bandeja accesible - {count} correo(s) no leido(s)")

    mail.logout()
    print("\nCONEXION EXITOSA - El sistema puede leer correos de Outlook.")

except imaplib.IMAP4.error as e:
    error = str(e)
    print(f"\nERROR DE IMAP: {error}")
    if "Basic authentication is disabled" in error:
        print("  CAUSA: Microsoft 365 tiene deshabilitada la autenticacion basica.")
        print("  SOLUCION: TI debe habilitar IMAP y deshabilitar MFA para este buzon.")
    elif "AUTHENTICATE failed" in error:
        print("  CAUSA: Credenciales incorrectas o autenticacion no soportada.")
        print("  SOLUCION: Verificar usuario y contrasena, o esperar a que TI habilite el acceso.")
    elif "Login failed" in error:
        print("  CAUSA: Usuario o contrasena incorrectos.")
        print("  SOLUCION: Verificar las credenciales en el archivo .env")

except Exception as e:
    print(f"\nERROR GENERAL: {str(e)}")
