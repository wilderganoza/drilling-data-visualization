# Lista de todos los parámetros de perforación rastreados
# Estos parámetros se usan para análisis de calidad y procesamiento de datos
TRACKED_PARAMETERS = [
    # Parámetros basados en tiempo
    "on_bottom_hours_hrs",
    "circulating_hours_hrs",
    
    # Parámetros de rotación
    "rotary_rpm_rpm",
    "motor_rpm_rpm",
    
    # Parámetros de bombas
    "pump_1_strokes_min_spm",
    "pump_2_strokes_min_spm",
    "pump_1_total_strokes_strokes",
    "pump_2_total_strokes_strokes",
    "pump_3_total_strokes_strokes",
    "pump_4_total_strokes_strokes",
    "total_strokes_p1plusp2plusp3plusp4_strokes",
    "total_pump_output_gal_per_min",
    "totalpumpdisplacement_barrels",
    
    # Parámetros de golpes de llenado
    "fill_strokes_strokes",
    "total_fill_strokes_strokes",
    
    # Parámetros de carga y fuerza
    "over_pull_klbs",
    "weight_on_bit_klbs",
    "hook_load_klbs",
    "line_wear_ton_miles",
    
    # Parámetros de presión
    "standpipe_pressure_psi",
    "differential_pressure_psi",
    
    # Parámetros de profundidad
    "hole_depth_feet",
    "bit_depth_feet",
    "block_height_feet",
    
    # Parámetros de velocidad y tasa
    "trip_speed_ft_per_min",
    "rate_of_penetration_ft_per_hr",
    "on_bottom_rop_ft_per_hr",
    "time_of_penetration_min_per_ft",
]

# Función para obtener la lista de parámetros rastreados
def get_tracked_parameters():
    # Retornar una copia de la lista para evitar modificaciones accidentales
    return TRACKED_PARAMETERS.copy()
