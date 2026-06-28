#!/usr/bin/env bash
set -o errexit

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "🗄️ Creating database tables..."
python -c "
import os
os.environ['FLASK_ENV'] = 'production'
from app import create_app, db
app = create_app('production')
with app.app_context():
    db.create_all()
    print('✅ Database tables created successfully!')
"

echo "🚀 Build complete!"