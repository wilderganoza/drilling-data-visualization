// Diccionario de etiquetas legibles para parámetros de perforación
export const PARAMETER_LABELS: Record<string, string> = {
  // Parámetros de tiempo
  'on_bottom_hours_hrs': 'On Bottom Hours',
  'circulating_hours_hrs': 'Circulating Hours',
  
  // Parámetros de rotación
  'rotary_rpm_rpm': 'Rotary RPM',
  'motor_rpm_rpm': 'Motor RPM',
  
  // Parámetros de bombas
  'pump_1_strokes_min_spm': 'Pump 1 SPM',
  'pump_2_strokes_min_spm': 'Pump 2 SPM',
  'pump_1_total_strokes_strokes': 'Pump 1 Total Strokes',
  'pump_2_total_strokes_strokes': 'Pump 2 Total Strokes',
  'pump_3_total_strokes_strokes': 'Pump 3 Total Strokes',
  'pump_4_total_strokes_strokes': 'Pump 4 Total Strokes',
  'total_strokes_p1plusp2plusp3plusp4_strokes': 'Total Strokes (All Pumps)',
  'total_pump_output_gal_per_min': 'Total Pump Output (gpm)',
  'totalpumpdisplacement_barrels': 'Total Pump Displacement (bbl)',
  
  // Parámetros de llenado
  'fill_strokes_strokes': 'Fill Strokes',
  'total_fill_strokes_strokes': 'Total Fill Strokes',
  
  // Parámetros de carga
  'over_pull_klbs': 'Over Pull (klbs)',
  'weight_on_bit_klbs': 'Weight on Bit (klbs)',
  'hook_load_klbs': 'Hook Load (klbs)',
  'line_wear_ton_miles': 'Line Wear (ton-miles)',
  
  // Parámetros de presión
  'standpipe_pressure_psi': 'Standpipe Pressure (psi)',
  'differential_pressure_psi': 'Differential Pressure (psi)',
  
  // Parámetros de profundidad
  'hole_depth_feet': 'Hole Depth (ft)',
  'bit_depth_feet': 'Bit Depth (ft)',
  'block_height_feet': 'Block Height (ft)',
  
  // Parámetros de velocidad
  'trip_speed_ft_per_min': 'Trip Speed (ft/min)',
  'rate_of_penetration_ft_per_hr': 'ROP (ft/hr)',
  'on_bottom_rop_ft_per_hr': 'On Bottom ROP (ft/hr)',
  'time_of_penetration_min_per_ft': 'Time of Penetration (min/ft)',
};


// Función para obtener etiqueta legible de un parámetro
export const getParameterLabel = (parameterName: string): string => {
  // Si existe en el diccionario, retornar etiqueta
  // Si no, formatear el nombre: reemplazar _ por espacios y capitalizar
  return PARAMETER_LABELS[parameterName] || parameterName
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (l: string) => l.toUpperCase());
};

// Función para obtener todos los nombres de parámetros conocidos
export const getAllParameterNames = (): string[] => {
  return Object.keys(PARAMETER_LABELS);
};

// Función para obtener todas las etiquetas de parámetros
export const getAllParameterLabels = (): string[] => {
  return Object.values(PARAMETER_LABELS);
};

// Función para verificar si un parámetro es conocido
export const isKnownParameter = (parameterName: string): boolean => {
  return parameterName in PARAMETER_LABELS;
};
