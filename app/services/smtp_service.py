import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from app.config import Config

def send_confirmation(to_email, company, date_str, processed_files):
    logging.info("El envío de correo de confirmación está deshabilitado.")
    return # Función deshabilitada a petición del usuario
    
    if not processed_files:
        return # No enviamos nada si no se procesó ningún archivo exitosamente
        
    logging.info(f"Enviando correo de confirmación a {to_email}...")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Confirmación: Corte de Caja {company} - {date_str} procesado con éxito"
    msg["From"] = Config.IMAP_USER
    msg["To"] = to_email
    
    # Lista de archivos en HTML
    files_list_html = "".join([f"<li><strong>{f}</strong></li>" for f in processed_files])
    
    # Plantilla HTML Profesional
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; background-color: #f4f7f6; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
            .header {{ background-color: #0f172a; color: #ffffff; padding: 20px; text-align: center; border-bottom: 4px solid #38bdf8; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; }}
            .content {{ padding: 30px; }}
            .success-banner {{ background-color: #ecfdf5; border-left: 4px solid #10b981; padding: 15px; margin-bottom: 25px; color: #065f46; border-radius: 4px; }}
            .footer {{ background-color: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            ul {{ background: #f8fafc; padding: 15px 15px 15px 35px; border-radius: 6px; border: 1px solid #e2e8f0; }}
            li {{ margin-bottom: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Automatización Corte de Caja</h1>
            </div>
            
            <div class="content">
                <div class="success-banner">
                    <strong>✅ ¡Recepción Exitosa!</strong>
                    <p style="margin: 5px 0 0 0;">Los documentos correspondientes a <strong>{company}</strong> con fecha <strong>{date_str}</strong> han sido procesados y almacenados en el servidor correctamente.</p>
                    <p style="margin: 5px 0 0 0;">📁 <strong>Carpeta de destino:</strong> {company}</p>
                </div>
                
                <p>Se guardaron los siguientes archivos válidos (PDFs y Excel):</p>
                <ul>
                    {files_list_html}
                </ul>
                
                <p><em>Nota: Cualquier otro tipo de archivo adjunto (como imágenes o documentos de texto) fue ignorado automáticamente por el sistema de seguridad.</em></p>
                
                <p style="margin-top: 30px;">
                    Saludos cordiales,<br>
                    <strong>Departamento de Sistemas - Canella</strong><br>
                    <span style="font-size: 0.9em; color: #64748b;">Este es un mensaje generado automáticamente.</span>
                </p>
            </div>
            
            <div class="footer">
                Sistema de Transferencia Automática &copy; {date_str.split('-')[-1]}
            </div>
        </div>
    </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    msg.attach(part)
    
    try:
        # Usamos SMTP_SSL si es puerto 465, pero como es 587 usamos SMTP + starttls
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.login(Config.IMAP_USER, Config.IMAP_PASSWORD)
        server.sendmail(Config.IMAP_USER, to_email, msg.as_string())
        server.quit()
        logging.info(f"Correo de confirmación enviado exitosamente a {to_email}")
    except Exception as e:
        logging.error(f"Error al enviar correo de confirmación a {to_email}: {str(e)}")
