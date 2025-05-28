from main import app # Import your FastAPI app
from os import environ
from uvicorn import Config, Server
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

port = int(environ.get('PORT', 8002)) # Get port from environment variable
logger.info(f"Running on port {port}")

config = Config(app, host="0.0.0.0", port=port, workers=1, log_level="info")
server = Server(config)
logger.info("Server running...")
server.run()
logger.info("Server stopped")

# # passenger_wsgi.py

# from asgiref.wsgi import WsgiToAsgi
# from .main import app   # your FastAPI() instance

# # Wrap the ASGI app as WSGI for Passenger
# application = WsgiToAsgi(app)
