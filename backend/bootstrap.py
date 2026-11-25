"""Run once: ADMIN_PASSWORD='your-long-secret' python bootstrap.py"""
import os
from app import seed_admin
password=os.getenv('ADMIN_PASSWORD','')
if not password:raise SystemExit('Set ADMIN_PASSWORD (12+ characters) before running bootstrap')
print('Initialized demo entities and administrator' if seed_admin(os.getenv('ADMIN_USERNAME','admin'),password) else 'Users already exist; no changes made')
