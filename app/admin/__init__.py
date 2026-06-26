from flask import Blueprint

bp = Blueprint('admin', __name__)

# Import routes AFTER bp is defined to avoid circular import
from app.admin import routes