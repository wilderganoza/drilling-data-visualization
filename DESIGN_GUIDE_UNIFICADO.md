# Guía de Diseño Visual – Plataforma de Operaciones Inteligentes (POI)

## 1. Introducción
La Plataforma de Operaciones Inteligentes (POI) unifica los lineamientos visuales y de interacción de las aplicaciones Drilling Data Visualization (DDV) y Sistema de Verificación de Permisos OIG Perú (FDA). El objetivo es ofrecer un lenguaje común que permita compartir componentes, evolucionar el sistema de manera coordinada y acelerar el trabajo de producto sin perder los matices específicos de cada dominio.

Esta guía consolida tokens de diseño, patrones de layout, criterios de visualización de datos, lineamientos de contenido y pautas de accesibilidad. Debe utilizarse como única fuente de referencia al diseñar nuevas funcionalidades, documentar componentes o implementar estilos en código.

## 2. Alcance y audiencia
- **Diseñadores de producto**: crean y mantienen pantallas para módulos analíticos y de cumplimiento.
- **Ingeniería frontend**: implementa componentes reutilizables en React (Tailwind/Vite) garantizando el soporte a tema claro/oscuro.
- **Equipos de datos y QHSE**: validan que las visualizaciones y checklists comuniquen la información crítica de forma inequívoca.
- **Stakeholders de negocio y seguridad**: auditan consistencia antes de liberaciones o demostraciones clave.

Casos de uso principales:
1. Diseñar dashboards, paneles de resultados y módulos administrativos con un lenguaje visual homogéneo.
2. Extender el inventario de componentes con variantes compatibles entre analytics (DDV) y compliance (FDA).
3. Evaluar accesibilidad, contrastes y estados críticos antes de desplegar nuevas funcionalidades.
4. Orquestar flujos complejos que combinan análisis de datos y validación documental.

## 3. Principios de diseño unificado
1. **Información primero**: métricas, veredictos y estados deben dominar el layout sobre elementos decorativos.
2. **Contexto continuo**: mantener orientación cuando el usuario navega entre pozos/datasets o solicitudes/documentos.
3. **Modularidad escalable**: cada componente debe operar tanto de forma aislada como en composiciones avanzadas.
4. **Claridad en los estados**: representar de manera explícita loading, vacíos, errores, advertencias y confirmaciones.
5. **Tono profesional con energía**: emplear una paleta técnica (azules, neutros fríos) con acentos verdes y turquesa para momentos clave.
6. **Sostenibilidad del sistema**: toda nueva regla debe reflejarse en tokens compartidos y documentación para evitar divergencias futuras.

## 4. Identidad visual
### 4.1 Personalidad
- **Núcleo**: precisión técnica, confianza y transparencia operativa.
- **Matices**: agilidad científica (analytics) y rigurosidad normativa (compliance).
- **Lenguaje visual**: limpio, basado en datos, con jerarquías tipográficas claras y componentes minimalistas.

### 4.2 Composición cromática
- El color primario azul refleja fiabilidad y se usa para CTAs principales, highlights de navegación y visualizaciones clave.
- Acentos verdes y turquesa refuerzan el éxito y la innovación, manteniendo compatibilidad entre ambos dominios.
- Rojos y amarillos conservan la semántica de riesgo y advertencia.

### 4.3 Imaginería
- Iconografía lineal (outline) basada en Heroicons, con un grosor uniforme (2 px) y adaptada a 18×18 px.
- Ilustraciones ligeras en empty states: usar la misma gama cromática y geometrías simples.

## 5. Tokens fundamentales
### 5.1 Variables base (CSS)
```css
:root {
  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius: 8px;
  --radius-lg: 12px;

  --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.08);
  --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.12);
  --shadow-md: 0 12px 30px rgba(15, 23, 42, 0.16);

  --transition-fast: 0.12s ease;
  --transition-base: 0.18s ease;
}
```

### 5.2 Paleta base
```css
:root {
  --color-primary: #4a7cff;
  --color-primary-hover: #3a6aee;
  --color-secondary: #22d3ee;      /* acento turquesa compartido */
  --color-accent: #10b981;          /* refuerzo para KPIs críticos */

  --color-success: #34d399;
  --color-warning: #fbbf24;
  --color-danger:  #f87171;

  --color-neutral-50:  #f5f7fa;
  --color-neutral-100: #e8ebf3;
  --color-neutral-200: #d9dce6;
  --color-neutral-300: #bcc2d4;
  --color-neutral-600: #6b7280;
  --color-neutral-700: #4b5563;
  --color-neutral-900: #1a1d27;
}
```

### 5.3 Temas claro y oscuro
```css
[data-theme="light"] {
  --color-bg: var(--color-neutral-50);
  --color-surface: #ffffff;
  --color-surface-hover: #f0f2f5;
  --color-border: #e1e4e8;
  --color-border-strong: #ccd1dc;
  --color-text: #1a1d27;
  --color-text-muted: #6b7280;
  --shadow: var(--shadow-sm);
  --color-chart-axis: #6b7280;
  --color-chart-line: #1a1d27;
  --color-tooltip-bg: #ffffff;
  --color-tooltip-border: #e1e4e8;
}

[data-theme="dark"] {
  --color-bg: #0f1117;
  --color-surface: #1a1d27;
  --color-surface-hover: #232733;
  --color-border: #2a2e3a;
  --color-border-strong: #3a3f4d;
  --color-text: #e4e6ed;
  --color-text-muted: #8b8fa3;
  --shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
  --color-chart-axis: #8b8fa3;
  --color-chart-line: #ffffff;
  --color-tooltip-bg: #1a1d27;
  --color-tooltip-border: #2a2e3a;
}
```

### 5.4 Paletas contextuales
- **Analytics Ops (DDV)**: `--color-context-primary: #2563eb` (líneas principales), `--color-context-emphasis: #22d3ee` (eventos de perforación), `--color-context-negative: #f97316` (anomalías).
- **Compliance Ops (FDA)**: `--color-context-primary: #2563eb`, `--color-context-emphasis: #34d399` (veredictos aprobados), `--color-context-negative: #f87171` (rechazados), `--color-context-pending: #fbbf24` (pendientes).

### 5.5 Tipografía
```css
font-family: 'Inter', 'Work Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

Jerarquía de tamaños:
- **H1 (páginas)**: 24 px, weight 700, line-height 1.2.
- **H2 (secciones)**: 20 px, weight 700, line-height 1.3.
- **H3 (subsecciones)**: 16 px, weight 600, line-height 1.4.
- **H4 (componentes)**: 14 px, weight 600.
- **Texto base**: 14 px, line-height 1.6.
- **Texto pequeño**: 12–13 px, line-height 1.5.
- **Microcopy**: 11 px, line-height 1.3.
- **Headers de tabla**: 11 px, uppercase, letter-spacing 0.5 px.

### 5.6 Iconografía y pictogramas
- Estilo outline, stroke 2 px, esquinas redondeadas, proporción 18×18 px.
- Iconografía crítica (alertas, estado) usa rellenos semitransparentes para reforzar semántica.

### 5.7 Sistema de espaciado
Basado en múltiplos de 4 px:
- **Padding**: 4, 8, 12, 16, 20, 24, 32, 40 px.
- **Margenes verticales**: 4 (micro), 8 (relacionados), 16 (grupos), 24 (secciones), 32 (cambios de contexto).
- **Gaps**: 4 (apretado), 8 (normal), 12 (medio), 16 (amplio), 24 (tableros densos).

### 5.8 Bordes y sombras
- Radios recomendados: `--radius` para componentes, `--radius-lg` para modales, 50%/999 px para avatares y badges.
- Bordes estándar de 1 px; 2 px para focus activo o contenedores destacados.
- Sombras contextuales: `--shadow-sm` en tarjetas, `--shadow-md` en modales.

## 6. Componentes base
### 6.1 Botones
```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 14px;
  font-weight: 500;
  transition: all var(--transition-base);
  cursor: pointer;
}
.btn:hover { background: var(--color-surface-hover); }

.btn-primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #ffffff;
  font-weight: 600;
}
.btn-primary:hover { background: var(--color-primary-hover); }

.btn-danger {
  border-color: var(--color-danger);
  color: var(--color-danger);
}
.btn-danger:hover {
  background: rgba(248, 113, 113, 0.12);
}

.btn-outline {
  background: transparent;
  color: var(--color-text);
}

.btn-sm { padding: 4px 12px; font-size: 12px; }
.btn-lg { padding: 12px 28px; font-size: 15px; font-weight: 600; }

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### 6.2 Inputs y formularios
```css
.input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-bg);
  color: var(--color-text);
  font-size: 14px;
  transition: border-color var(--transition-fast);
}
.input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(74, 124, 255, 0.18);
}

.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}

.select, .textarea {
  padding: 8px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text);
}
```

### 6.3 Badges
```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.badge.success { background: rgba(52, 211, 153, 0.15); color: var(--color-success); }
.badge.warning { background: rgba(251, 191, 36, 0.18); color: var(--color-warning); }
.badge.danger  { background: rgba(248, 113, 113, 0.15); color: var(--color-danger); }
.badge.primary { background: rgba(74, 124, 255, 0.15); color: var(--color-primary); }
.badge.info    { background: rgba(34, 211, 238, 0.15); color: var(--color-secondary); }
```

## 7. Componentes compuestos
### 7.1 Tarjetas (Card)
```css
.card {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card-header { display: flex; justify-content: space-between; align-items: flex-start; }
.card-footer { display: flex; justify-content: flex-end; gap: 8px; }
```

### 7.2 Tablas
```css
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: var(--color-surface);
}
.data-table th, .data-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
}
.data-table th {
  background: var(--color-surface);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  position: sticky;
  top: 0;
  z-index: 1;
}
.data-table tr:hover td { background: var(--color-surface-hover); }
```

### 7.3 Modales
```css
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 50;
}
.modal {
  width: 100%;
  max-width: 500px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}
.modal-header, .modal-footer {
  padding: 18px 24px;
}
.modal-body {
  padding: 0 24px 24px;
}
```

### 7.4 Tabs
```css
.tab-bar {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
}
.tab-btn {
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  transition: color var(--transition-fast), border-color var(--transition-fast);
  cursor: pointer;
}
.tab-btn:hover { color: var(--color-text); }
.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
```

### 7.5 Mensajes de estado
```css
.status-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  margin-bottom: 16px;
}
.status-message.success {
  background: rgba(52, 211, 153, 0.12);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: var(--color-success);
}
.status-message.error {
  background: rgba(248, 113, 113, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.3);
  color: var(--color-danger);
}
.status-message.warning {
  background: rgba(251, 191, 36, 0.12);
  border: 1px solid rgba(251, 191, 36, 0.3);
  color: var(--color-warning);
}
.status-message.info {
  background: rgba(34, 211, 238, 0.12);
  border: 1px solid rgba(34, 211, 238, 0.3);
  color: var(--color-secondary);
}
```

### 7.6 Spinner
```css
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

## 8. Estados e interacciones
- **Hover**: elevar superficie con `--color-surface-hover` o incremento ligero en sombra.
- **Focus**: borde de 2 px con `--color-primary`; mantener contraste mínimo 3:1.
- **Active**: reforzar color principal o aplicar sombra interna (`box-shadow: inset 0 0 0 1px var(--color-primary)`).
- **Disabled**: reducir opacidad al 50%, deshabilitar pointer events cuando sea necesario.

Transiciones recomendadas:
- `all var(--transition-base)` para elementos interactivos.
- `transform 0.3s ease` en toggles de sidebar o paneles colapsables.

## 9. Visualización de datos y reportes
### 9.1 Configuración de Recharts
```jsx
<XAxis
  dataKey="label"
  tick={{ fontSize: 11, fill: 'var(--color-chart-axis)' }}
  stroke="var(--color-border)"
/>
<YAxis
  tick={{ fontSize: 11, fill: 'var(--color-chart-axis)' }}
  stroke="var(--color-border)"
/>
<Tooltip
  contentStyle={{
    background: 'var(--color-tooltip-bg)',
    border: `1px solid var(--color-tooltip-border)`,
    borderRadius: 8,
    fontSize: 13,
    color: 'var(--color-text)'
  }}
  labelStyle={{ color: 'var(--color-text-muted)' }}
/>
<CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} />
<Line type="monotone" dataKey="value" stroke={getVar('--color-context-primary')} strokeWidth={2} dot={{ r: 3 }} />
```

Utilidad para leer variables CSS en JS:
```ts
const getVar = (token: string) =>
  getComputedStyle(document.documentElement)
    .getPropertyValue(token)
    .trim();
```

### 9.2 Visualizaciones analíticas (DDV)
- Destacar tendencias con degradados `fillOpacity 0.4–0.6`.
- Señalar eventos críticos con badges flotantes usando `--color-context-negative`.
- Sincronizar tooltips cuando varias gráficas comparten eje temporal.

### 9.3 Visualizaciones de veredictos (FDA)
- Utilizar `verdict-banner` con borde lateral de 4 px y color semántico.
- Incluir iconos (`CheckCircle`, `XCircle`, `Clock`) acompañados de texto descriptivo.
- Para checklists, mostrar badges por ítem y un resumen colapsable por persona/vehículo.

## 10. Patrones de pantalla unificados
### 10.1 Paneles analíticos (Analytics Ops)
- Layout de dos columnas (280 px controles / restante para visualizaciones).
- Header con breadcrumbs (Pozo → Dataset → Registro) y acciones rápidas.
- Tabs para cambiar entre KPIs, gráficos y logs de eventos.
- Estados previsibles: sin datos, cargando, error de conexión.

### 10.2 Validación documental (Compliance Ops)
- Flujo Wizard: carga → análisis → resultados.
- Barra superior con progreso y estado del pipeline (iconos + texto).
- Resultados divididos en tabs (Resumen, Documentos, Checklist) reutilizando `tab-bar`.
- Logs en tiempo real con timestamps HH:MM:SS y badges de severidad.

### 10.3 Patrones compartidos
- **Layout principal**: header fijo (56 px), sidebar 200 px colapsable, `app-main` con `padding: 24px`.
- **Empty states**: ilustración sutil + texto directo + CTA secundario.
- **Acciones masivas**: barras contextuales sobre tablas con botones outline.
- **Feedback**: `status-message` persistente para confirmaciones críticas.

## 11. Contenido y microcopy
### 11.1 Principios
1. Claridad operativa: verbos imperativos cortos ("Analizar", "Exportar", "Reintentar").
2. Contexto técnico: usar unidades aprobadas (m, psi, MB) o categorías oficiales (Aprobado, Pendiente, Observado).
3. Proactividad: ante errores, ofrecer siguiente paso o referencia ("Configura tu API Key" / "Ajusta filtros").
4. Consistencia lingüística: compartir glosario entre equipos para alinear términos (pozo, solicitud, checklist, veredicto).

### 11.2 Tonalidad por dominio
- **Analytics**: insights basados en datos, tono consultivo ("Se detectó una anomalía en 3 registros").
- **Compliance**: tono normativo y determinista ("Veredicto: Rechazado por licencia vencida").

### 11.3 Formatos
- Fechas largas en español para resultados: `8 de abril de 2026, 16:31 h`.
- Logs con timestamps `HH:MM:SS`.
- Porcentajes con un decimal: `92.4 %`.
- Tamaños de archivo con unidad apropiada: `1.2 MB`.

## 12. Implementación técnica
### 12.1 Tema y persistencia
```ts
import { useState, useEffect } from 'react';

type Theme = 'light' | 'dark';

export const useTheme = () => {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme') as Theme | null;
    return saved ?? 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(prev => (prev === 'dark' ? 'light' : 'dark'));

  return { theme, toggleTheme };
};
```

### 12.2 Layout base
```jsx
function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="app-layout">
      <Header onToggleSidebar={() => setSidebarOpen(v => !v)} />
      <Sidebar isOpen={sidebarOpen} />
      <main
        className="app-main"
        style={{
          marginLeft: sidebarOpen ? '200px' : '0',
          marginTop: '56px'
        }}
      >
        {/* Contenido */}
      </main>
    </div>
  );
}
```

```css
.app-layout {
  min-height: 100vh;
  background: var(--color-bg);
  color: var(--color-text);
}
.app-main {
  min-width: 0;
  padding: 24px;
  transition: margin-left 0.3s ease;
}
.sidebar {
  position: fixed;
  top: 56px;
  left: 0;
  bottom: 0;
  width: 200px;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  transform: translateX(0);
  transition: transform 0.3s ease;
}
.sidebar.hidden { transform: translateX(-100%); }
```

### 12.3 Scrollbar y accesibilidad
```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--color-bg); }
::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: var(--color-text-muted); }

:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

## 13. Checklist de implementación
- [ ] Definir variables CSS en `:root` y temas en `[data-theme]`.
- [ ] Cargar tipografía Inter (weights 400–700) y fallback Work Sans.
- [ ] Implementar botones, inputs, tablas, modales, tabs y badges con los tokens actualizados.
- [ ] Configurar `status-message`, `spinner` y estados hover/focus/active/disabled.
- [ ] Aplicar layout con header fijo, sidebar colapsable y `app-main` responsivo.
- [ ] Integrar gráficos Recharts con colores dinámicos y tooltips consistentes.
- [ ] Documentar variantes contextuales (analytics/compliance) en Storybook o guía interna.
- [ ] Validar contrastes (WCAG AA) en ambos temas y estados de interacción.
- [ ] Sincronizar microcopy con glosario común y revisar localización.
- [ ] Mantener versión de la guía y changelog accesibles a todo el equipo.

## 14. Glosario rápido
- **Analytics Ops**: módulos de exploración y monitoreo de datos de perforación.
- **Compliance Ops**: flujos de verificación documental y permisos regulados.
- **Veredicto**: resultado global de la evaluación de una solicitud (Aprobado/Rechazado/Pendiente).
- **Checklist**: subconjunto de validaciones individuales asociadas a una persona, vehículo o pozo.
- **Pipeline**: secuencia de pasos automatizados para procesar datos o documentos.

## 15. Gobierno del sistema
- Nombrar un *Design Ops Owner* responsable de aprobar nuevas variantes.
- Registrar cambios en un changelog compartido y versionar tokens (ej. `tokens@2.1.0`).
- Alinear ciclos de release entre DDV y FDA para evitar divergencias de componentes.
- Incorporar QA visual y pruebas de accesibilidad en el pipeline de CI/CD.

---

**Versión**: 3.0 (Unificación POI)

**Última actualización**: abril 2026  
**Aplicaciones cubiertas**: Drilling Data Visualization · Sistema de Verificación de Permisos OIG Perú  
**Stack de referencia**: React 19 · Vite · Tailwind/Vanilla CSS · Recharts · Express · PostgreSQL · Servicios OpenAI
