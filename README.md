# Automatización Corte de Caja Diario

Este proyecto es un sistema automatizado para la recolección, clasificación y almacenamiento de archivos de "Corte de Caja" provenientes de dos fuentes distintas:
1. **Correos Electrónicos (IMAP):** Un robot revisa constantemente la bandeja de entrada en busca de correos con el asunto de cortes/cuadres.
2. **Carpeta Local (Watchdog):** Un monitor observa en tiempo real una carpeta específica para detectar archivos depositados manualmente.

El sistema también incluye un **Dashboard Web en tiempo real** (construido con Flask) para monitorear el estado de los archivos procesados.

---

## 🚀 Características Principales

* **Recepción por Correo Electrónico:** 
  * Se conecta vía IMAP a Gmail.
  * Busca correos no leídos que contengan palabras clave (`corte`, `cuadre`).
  * Extrae dinámicamente la **fecha** y la **empresa** (Maquipos, VESA, Canella, Cobradores) desde el asunto.
  * Descarga los adjuntos permitidos (PDF y Excel) y los guarda en la ruta de red correspondiente.
  * Responde automáticamente con un correo de confirmación de éxito.

* **Monitoreo de Carpeta Local (Watchdog):**
  * Observa una carpeta específica (ej. `C:\Users\inforcruz\Documents\Cortes_de_Caja`).
  * Cuando se deposita un archivo, analiza el nombre usando expresiones regulares (Regex) para determinar la empresa y la fecha.
  * Transfiere automáticamente el archivo a la ruta de red final.

* **Enrutamiento Inteligente:**
  * Crea automáticamente la estructura de carpetas: `[EMPRESA] / [AÑO] / [MES] / [FECHA]`.
  * Ejemplo: `\\SRV-DESAIT5\Corte_de_Caja\MAQUIPOS\2026\Agosto\25-08-2026`
  * Previene sobreescritura de archivos agregando un contador `(1)`, `(2)` a los archivos duplicados.

* **Dashboard de Monitoreo (Web):**
  * Interfaz web moderna (Modo Oscuro) en `http://127.0.0.1:5000`.
  * Tabla con historial de archivos procesados, indicando nombre, estado (ÉXITO/ERROR/IGNORADO), destino y fecha/hora.
  * Filtros por nombre de archivo y rango de fechas.
  * Paginación integrada (15 registros por página).

---

## 🛠️ Requisitos Previos

Necesitas tener instalado Python 3.8+ y las siguientes librerías externas (puedes instalarlas ejecutando este comando en la terminal):

```bash
pip install flask watchdog
```

*(Librerías como `imaplib`, `smtplib`, `email`, `os`, `re`, `json`, `threading` ya vienen incluidas por defecto en Python).*

---

## ⚙️ Configuración (app/config.py)

Antes de ejecutar el proyecto, asegúrate de revisar el archivo `app/config.py`. En él se definen las variables clave:

- `IMAP_USER`: Tu correo de Gmail (`ricardocruzprogra@gmail.com`).
- `IMAP_PASSWORD`: Tu **Contraseña de Aplicación** de Gmail (NO tu contraseña normal).
- `IMAP_SERVER` / `SMTP_SERVER`: Servidores de Google (`imap.gmail.com` y `smtp.gmail.com`).
- `WATCH_DIR`: Ruta de la carpeta local que se va a monitorear.
- `DEST_DIR`: Ruta raíz del servidor/red donde se van a organizar las carpetas por empresa y fecha (`\\SRV-DESAIT5\Corte_de_Caja`).
- `EMAIL_CHECK_INTERVAL`: Cada cuántos segundos el robot revisa los correos nuevos (por defecto 120s).

---

## ▶️ Cómo Ejecutar el Proyecto

Abre una terminal (Git Bash, PowerShell o CMD), navega a la carpeta del proyecto y ejecuta el archivo principal:

```bash
python run.py
```

Deberías ver en la consola los mensajes de inicialización:
```
- Observador iniciado en: C:\Users\...
- Servicio de Correos iniciado.
- Conectando al servidor IMAP...
* Running on http://127.0.0.1:5000
```

Para ver el **Dashboard Web**, abre tu navegador y entra a:
👉 `http://127.0.0.1:5000`

---

## 📁 Estructura del Proyecto

```text
AUTOMATIZACION_CORTE_DE_CAJA_DIARIO/
│
├── app/
│   ├── __init__.py            # Inicializa la App Flask y los sub-servicios (Hilos)
│   ├── config.py              # Variables de entorno y configuraciones globales
│   ├── api/
│   │   └── transfer_api.py    # Endpoint REST que provee los logs (JSON) al Dashboard
│   ├── services/
│   │   ├── email_service.py   # Lógica IMAP/SMTP (lectura, descarga y respuesta de correos)
│   │   └── watcher.py         # Lógica Watchdog (monitoreo de carpeta local)
│   ├── templates/
│   │   └── index.html         # Frontend del Dashboard (HTML/CSS/JS Vainilla)
│   └── views/
│       └── dashboard.py       # Ruta principal Flask ('/') que sirve el index.html
│
├── run.py                     # Script principal para encender el servidor
├── correos_procesados.json    # Base de datos local (memoria) de correos ya leídos
└── transfer_logs.json         # Base de datos local de logs históricos para el Dashboard
```

---

## 💡 Notas Importantes sobre el Entorno de Pruebas

- **Correos a ti mismo:** Si haces pruebas enviándote correos desde tu propio Gmail a tu propio Gmail, Gmail los marcará automáticamente como **"Leídos"**. Dado que el sistema busca correos "No Leídos" (`UNSEEN`), ignorará tus pruebas a menos que las marques manualmente como "No leídas" en tu bandeja de entrada antes de que el robot pase.
- **Seguridad Gmail:** Asegúrate de siempre utilizar "Contraseñas de Aplicación" para la autenticación en IMAP/SMTP.
