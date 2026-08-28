from flask import Flask
import threading

def create_app():
    app = Flask(__name__)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    
    # Importar Blueprints
    from app.api.transfer_api import api_bp
    from app.views.dashboard import views_bp
    
    # Registrar Blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)
    
    # Iniciar el servicio en segundo plano (watcher)
    from app.services.watcher import start_watcher
    watcher_thread = threading.Thread(target=start_watcher, daemon=True)
    watcher_thread.start()
    
    # Iniciar el servicio de correos en segundo plano
    from app.services.email_service import start_email_service
    email_thread = threading.Thread(target=start_email_service, daemon=True)
    email_thread.start()
    
    return app
