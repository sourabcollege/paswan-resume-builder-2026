from flask import Blueprint
bp = Blueprint('ai', __name__)
from app.ai import routes
