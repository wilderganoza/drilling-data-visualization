// Función para descargar gráfico como imagen PNG (sin barra de Brush/zoom)
export const downloadChartAsPNG = async (chartRef: HTMLElement | null, filename: string) => {
  // Validar que existe la referencia al gráfico
  if (!chartRef) return;

  // Encontrar y ocultar elementos Brush temporalmente
  const brushElements = chartRef.querySelectorAll('.recharts-brush');
  const originalDisplayValues: string[] = [];
  
  // Iterar sobre elementos Brush y ocultarlos
  brushElements.forEach((brush) => {
    const element = brush as HTMLElement;
    // Guardar valor original de display
    originalDisplayValues.push(element.style.display);
    // Ocultar elemento
    element.style.display = 'none';
  });

  // Almacenar colores originales para restaurar después
  const elementsWithOklch: Array<{ element: HTMLElement; property: string; originalValue: string }> = [];

  // Encontrar todos los elementos con colores oklch y convertirlos
  const allElements = chartRef.querySelectorAll('*');
  allElements.forEach((el) => {
    const element = el as HTMLElement;
    const computedStyle = window.getComputedStyle(element);
    
    // Verificar propiedades comunes que podrían tener colores oklch
    const properties = ['color', 'backgroundColor', 'borderColor', 'fill', 'stroke'];
    
    // Iterar sobre cada propiedad
    properties.forEach((prop) => {
      const value = computedStyle.getPropertyValue(prop);
      // Si el valor contiene oklch
      if (value && value.includes('oklch')) {
        // Guardar valor original
        elementsWithOklch.push({
          element,
          property: prop,
          originalValue: element.style.getPropertyValue(prop)
        });
        
        // Convertir oklch a rgb obteniendo color computado
        const tempDiv = document.createElement('div');
        tempDiv.style.color = value;
        document.body.appendChild(tempDiv);
        const rgbValue = window.getComputedStyle(tempDiv).color;
        document.body.removeChild(tempDiv);
        
        // Aplicar el valor rgb
        element.style.setProperty(prop, rgbValue, 'important');
      }
    });
  });

  try {
    // Importar html2canvas dinámicamente
    const html2canvas = (await import('html2canvas')).default;
    
    // Capturar el gráfico como canvas
    const canvas = await html2canvas(chartRef, {
      backgroundColor: '#1F2937', // Color de fondo
      scale: 2, // Escala para mayor calidad
      logging: false, // Desactivar logs
      useCORS: true, // Permitir CORS
      ignoreElements: (element) => {
        // Ignorar elementos que podrían causar problemas
        return element.classList.contains('recharts-brush');
      }
    });

    // Convertir canvas a blob y descargar
    canvas.toBlob((blob) => {
      if (blob) {
        // Crear enlace de descarga
        const link = document.createElement('a');
        link.download = `${filename}.png`;
        link.href = URL.createObjectURL(blob);
        link.click();
        // Liberar URL del objeto
        URL.revokeObjectURL(link.href);
      }
    }, 'image/png');
  } finally {
    // Restaurar visibilidad de elementos Brush
    brushElements.forEach((brush, index) => {
      const element = brush as HTMLElement;
      element.style.display = originalDisplayValues[index];
    });

    // Restaurar colores oklch originales
    elementsWithOklch.forEach(({ element, property, originalValue }) => {
      if (originalValue) {
        element.style.setProperty(property, originalValue);
      } else {
        element.style.removeProperty(property);
      }
    });
  }
};

// Función para descargar datos como archivo CSV
export const downloadDataAsCSV = (
  data: Array<Record<string, any>>, // Array de objetos de datos
  filename: string, // Nombre del archivo
  columns?: string[] // Columnas opcionales a incluir
) => {
  // Validar que hay datos
  if (!data || data.length === 0) return;

  // Obtener columnas de los datos si no se proporcionan
  const cols = columns || Object.keys(data[0]);

  // Crear encabezado CSV
  const header = cols.join(',');

  // Crear filas CSV
  const rows = data.map((row) =>
    cols.map((col) => {
      const value = row[col];
      // Manejar valores null/undefined
      if (value == null) return '';
      // Escapar valores que contienen comas o comillas
      if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    }).join(',')
  );

  // Combinar encabezado y filas
  const csv = [header, ...rows].join('\n');

  // Crear blob y descargar
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${filename}.csv`;
  link.click();
  // Liberar URL del objeto
  URL.revokeObjectURL(link.href);
};

// Función para descargar datos como archivo JSON
export const downloadDataAsJSON = (data: any, filename: string) => {
  // Convertir datos a JSON con formato legible (indentación de 2 espacios)
  const json = JSON.stringify(data, null, 2);
  // Crear blob con tipo JSON
  const blob = new Blob([json], { type: 'application/json' });
  // Crear enlace de descarga
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${filename}.json`;
  link.click();
  // Liberar URL del objeto
  URL.revokeObjectURL(link.href);
};
