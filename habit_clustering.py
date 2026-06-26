import os
import pandas as pd
from collections import Counter

def analizar_habitos(csv_path="~/.jarvis/logs/context_habits.csv"):
    """
    Analiza el CSV de hábitos contextuales y devuelve
    las acciones que se repiten con alta frecuencia por hora.
    """
    # 1. Cargar CSV
    df = pd.read_csv(os.path.expanduser(csv_path))
    
    # 2. Extraer hora, acción y día
    df['hora'] = pd.to_datetime(df['timestamp']).dt.hour
    
    # 3. Contar frecuencia de acciones por hora
    rutinas = df.groupby(['hora', 'action']).size().reset_index(name='frecuencia')
    
    # 4. Filtrar por alta frecuencia (>3 repeticiones)
    rutinas_altas = rutinas[rutinas['frecuencia'] > 3]
    
    # 5. Devolver lista de posibles automatizaciones
    return rutinas_altas
