import os
from dotenv import load_dotenv
from app import create_app
from flask_basicauth import BasicAuth

load_dotenv()
app = create_app()

app.config['BASIC_AUTH_USERNAME'] = os.getenv('BASIC_AUTH_USERNAME', 'empresa')
app.config['BASIC_AUTH_PASSWORD'] = os.getenv('BASIC_AUTH_PASSWORD', 'defaultpass')
app.config['BASIC_AUTH_FORCE'] = True
basic_auth = BasicAuth(app)

if __name__ == '__main__':
    # debug=True recarga plantillas automáticamente
    # use_reloader=False evita que los hilos de fondo se dupliquen
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
