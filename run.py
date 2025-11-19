from app import create_app
from app.models import db
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

load_dotenv()

app = create_app()
migrate = Migrate(app, db)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)