#!/usr/bin/env python3
"""
build_app_cache.py - Escanea todas las apps instaladas y las guarda en cache.
Se ejecuta al iniciar JarvisBot para tener un listado rápido de apps disponibles.
"""

import os
import json
import glob
from pathlib import Path

CACHE_FILE = os.path.expanduser("~/.jarvis/app_cache.json")

def parse_desktop_file(filepath):
    """Extrae nombre y exec de un archivo .desktop"""
    name = None
    exec_cmd = None
    generic_name = None
    icon = None
    no_display = False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('Name=') and not name:
                    name = line.split('=', 1)[1]
                elif line.startswith('GenericName=') and not generic_name:
                    generic_name = line.split('=', 1)[1]
                elif line.startswith('Exec=') and not exec_cmd:
                    exec_cmd = line.split('=', 1)[1].split()[0]  # Solo el comando base
                elif line.startswith('Icon=') and not icon:
                    icon = line.split('=', 1)[1]
                elif line.startswith('NoDisplay='):
                    if 'true' in line.lower():
                        no_display = True
    except Exception:
        return None
    
    if not name or not exec_cmd or no_display:
        return None
    
    return {
        'name': name,
        'generic_name': generic_name or '',
        'exec': exec_cmd,
        'icon': icon or '',
        'desktop_file': os.path.basename(filepath),
        'keywords': [
            name.lower(),
            os.path.basename(filepath).replace('.desktop', '').lower(),
            generic_name.lower() if generic_name else '',
        ]
    }

def build_cache():
    """Escanea todos los .desktop y construye el cache"""
    apps = []
    seen_names = set()
    
    # Directorios donde Linux guarda los .desktop
    desktop_dirs = [
        '/usr/share/applications',
        os.path.expanduser('~/.local/share/applications'),
        '/usr/local/share/applications',
    ]
    
    for desktop_dir in desktop_dirs:
        if not os.path.exists(desktop_dir):
            continue
        
        for desktop_file in glob.glob(os.path.join(desktop_dir, '*.desktop')):
            app = parse_desktop_file(desktop_file)
            if app and app['name'] not in seen_names:
                apps.append(app)
                seen_names.add(app['name'])
    
    # Guardar cache
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(apps, f, indent=2, ensure_ascii=False)
    
    print(f"[APP_CACHE] ✅ {len(apps)} aplicaciones cacheadas en {CACHE_FILE}")
    
    # Mostrar algunas apps importantes para verificar
    important_apps = ['spotify', 'firefox', 'chrome', 'discord', 'code', 'steam', 'terminal', 'calculator']
    print("\n[APP_CACHE] Apps importantes encontradas:")
    for app in apps:
        for kw in app['keywords']:
            if any(imp in kw for imp in important_apps):
                print(f"  - {app['name']} → {app['exec']} ({app['desktop_file']})")
                break
    
    return apps

def find_app(query):
    """Busca una app en el cache por nombre o keyword"""
    if not os.path.exists(CACHE_FILE):
        build_cache()
    
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        apps = json.load(f)
    
    query = query.lower().strip()
    
    # Búsqueda exacta primero
    for app in apps:
        if query in app['keywords']:
            return app
    
    # Búsqueda fuzzy
    for app in apps:
        for kw in app['keywords']:
            if query in kw or kw in query:
                return app
    
    return None

if __name__ == '__main__':
    build_cache()
