# Guía de Diseño Visual – Plataforma de Operaciones Inteligentes (POI)

## 1. Introducción
La Plataforma de Operaciones Inteligentes (POI) unifica los lineamientos visuales y de interacción de tres aplicaciones especializadas del sector energético:
- **Drilling Data Visualization (DDV)**: análisis de datos de perforación y detección de anomalías.
- **Sistema de Verificación de Permisos OIG Perú (FDA)**: validación documental y cumplimiento normativo.
- **Subsurface Production Allocation (SPA)**: asignación de producción por arenas y análisis de curvas de declinación.

El objetivo es ofrecer un lenguaje común que permita compartir componentes, evolucionar el sistema de manera coordinada y acelerar el trabajo de producto sin perder los matices específicos de cada dominio.

Esta guía consolida tokens de diseño, patrones de layout, criterios de visualización de datos, lineamientos de contenido y pautas de accesibilidad. Debe utilizarse como única fuente de referencia al diseñar nuevas funcionalidades, documentar componentes o implementar estilos en código.

## 2. Alcance y audiencia
- **Diseñadores de producto**: crean y mantienen pantallas para módulos analíticos, de cumplimiento y de ingeniería de petróleo.
- **Ingeniería frontend**: implementa componentes reutilizables en React (Tailwind/Vite) garantizando el soporte a tema claro/oscuro.
- **Equipos de datos, QHSE e ingenieros de petróleo**: validan que las visualizaciones, checklists y resultados técnicos comuniquen la información crítica de forma inequívoca.
- **Stakeholders de negocio, seguridad y reservorios**: auditan consistencia antes de liberaciones o demostraciones clave.

Casos de uso principales:
1. Diseñar dashboards, paneles de resultados y módulos administrativos con un lenguaje visual homogéneo.
2. Extender el inventario de componentes con variantes compatibles entre analytics (DDV), compliance (FDA) y petroleum engineering (SPA).
3. Evaluar accesibilidad, contrastes y estados críticos antes de desplegar nuevas funcionalidades.
4. Orquestar flujos complejos que combinan análisis de datos, validación documental y asignación de producción.

## 3. Principios de diseño unificado
1. **Información primero**: métricas, veredictos y estados deben dominar el layout sobre elementos decorativos.
2. **Contexto continuo**: mantener orientación cuando el usuario navega entre pozos/datasets o solicitudes/documentos.
3. **Modularidad escalable**: cada componente debe operar tanto de forma aislada como en composiciones avanzadas.
4. **Claridad en los estados**: representar de manera explícita loading, vacíos, errores, advertencias y confirmaciones.
5. **Tono profesional con energía**: emplear una paleta técnica (azules, neutros fríos) con acentos verdes y turquesa para momentos clave.
6. **Sostenibilidad del sistema**: toda nueva regla debe reflejarse en tokens compartidos y documentación para evitar divergencias futuras.

## 4. Índice de contenidos
1. [Introducción](#1-introducción)
2. [Alcance y audiencia](#2-alcance-y-audiencia)
3. [Principios de diseño unificado](#3-principios-de-diseño-unificado)
4. [Índice de contenidos](#4-índice-de-contenidos)
5. [Identidad visual](#5-identidad-visual)
6. [Tokens fundamentales](#6-tokens-fundamentales)
7. [Componentes base](#7-componentes-base)
8. [Componentes compuestos](#8-componentes-compuestos)
9. [Estados e interacciones](#9-estados-e-interacciones)
10. [Visualización de datos y reportes](#10-visualización-de-datos-y-reportes)
11. [Patrones de pantalla unificados](#11-patrones-de-pantalla-unificados)
12. [Header y Sidebar](#12-header-y-sidebar)
13. [Contenido y microcopy](#13-contenido-y-microcopy)
14. [Implementación técnica](#14-implementación-técnica)
15. [Animaciones y transiciones](#15-animaciones-y-transiciones)
16. [Checklist de implementación](#16-checklist-de-implementación)
17. [Glosario rápido](#17-glosario-rápido)
18. [Gobierno del sistema](#18-gobierno-del-sistema)
19. [Consideraciones específicas por aplicación](#19-consideraciones-específicas-por-aplicación)
20. [Notas adicionales](#20-notas-adicionales)

## 5. Identidad visual
### 5.1 Personalidad
- **Núcleo**: precisión técnica, confianza y transparencia operativa.
- **Matices**: agilidad científica (analytics), rigurosidad normativa (compliance) y expertise ingenieril (petroleum).
- **Lenguaje visual**: limpio, basado en datos, con jerarquías tipográficas claras y componentes minimalistas.

### 5.2 Composición cromática
- El color primario azul refleja fiabilidad y se usa para CTAs principales, highlights de navegación y visualizaciones clave.
- Acentos verdes y turquesa refuerzan el éxito y la innovación, manteniendo compatibilidad entre los tres dominios.
- Rojos y amarillos conservan la semántica de riesgo y advertencia.
- Paleta de 8 colores para diferenciación de series en gráficos multi-variable.

### 5.3 Imaginería
- Iconografía lineal (outline) basada en Heroicons, con un grosor uniforme (2 px) y adaptada a 18×18 px.
- Ilustraciones ligeras en empty states: usar la misma gama cromática y geometrías simples.
- SVG inline para iconos (sin dependencias adicionales).

## 6. Tokens fundamentales
### 6.1 Variables base (CSS)
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

### 6.2 Paleta base
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

### 6.3 Temas claro y oscuro
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

### 6.4 Paleta de gráficos (8 colores)
```css
--color-chart-1: #4a7cff;  /* Azul primario */
--color-chart-2: #34d399;  /* Verde */
--color-chart-3: #fbbf24;  /* Amarillo */
--color-chart-4: #f87171;  /* Rojo */
--color-chart-5: #a78bfa;  /* Púrpura */
--color-chart-6: #f472b6;  /* Rosa */
--color-chart-7: #38bdf8;  /* Cyan */
--color-chart-8: #fb923c;  /* Naranja */
```

### 6.5 Colores semánticos con opacidad

#### Success (Verde)
- **Fondo**: `rgba(52, 211, 153, 0.1)`
- **Borde**: `rgba(52, 211, 153, 0.3)`
- **Texto**: `var(--color-success)` (#34d399)
- **Badge**: `rgba(52, 211, 153, 0.15)`

#### Warning (Amarillo)
- **Fondo**: `rgba(251, 191, 36, 0.1)`
- **Borde**: `rgba(251, 191, 36, 0.3)`
- **Texto**: `var(--color-warning)` (#fbbf24)
- **Badge**: `rgba(251, 191, 36, 0.15)`

#### Danger (Rojo)
- **Fondo**: `rgba(248, 113, 113, 0.1)`
- **Borde**: `rgba(248, 113, 113, 0.3)`
- **Texto**: `var(--color-danger)` (#f87171)
- **Badge**: `rgba(248, 113, 113, 0.15)`

#### Primary (Azul)
- **Fondo activo**: `rgba(74, 124, 255, 0.12)`
- **Hover**: `rgba(74, 124, 255, 0.08)`
- **Badge**: `rgba(74, 124, 255, 0.15)`

#### Muted (Gris)
- **Badge**: `rgba(139, 143, 163, 0.15)`

#### Purple (Púrpura)
- **Badge**: `rgba(167, 139, 250, 0.15)`
- **Texto**: `#a78bfa`

### 6.6 Paletas contextuales
- **Analytics Ops (DDV)**: `--color-context-primary: #2563eb` (líneas principales), `--color-context-emphasis: #22d3ee` (eventos de perforación), `--color-context-negative: #f97316` (anomalías).
- **Compliance Ops (FDA)**: `--color-context-primary: #2563eb`, `--color-context-emphasis: #34d399` (veredictos aprobados), `--color-context-negative: #f87171` (rechazados), `--color-context-pending: #fbbf24` (pendientes).
- **Petroleum Ops (SPA)**: paleta de 8 colores para arenas (`--color-chart-1` a `--color-chart-8`), `--color-context-primary: #4a7cff` (producción total), `--color-context-emphasis: #34d399` (asignación exitosa), líneas de intervención con `strokeDasharray="4 4"` y opacidad 0.5.

### 6.7 Tipografía
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

### 6.8 Iconografía y pictogramas
- Estilo outline, stroke 2 px, esquinas redondeadas, proporción 18×18 px.
- Iconografía crítica (alertas, estado) usa rellenos semitransparentes para reforzar semántica.

### 6.9 Sistema de espaciado
Basado en múltiplos de 4 px:
- **Padding**: 4, 8, 12, 16, 20, 24, 32, 40 px.
- **Margenes verticales**: 4 (micro), 8 (relacionados), 16 (grupos), 24 (secciones), 32 (cambios de contexto).
- **Gaps**: 4 (apretado), 8 (normal), 12 (medio), 16 (amplio), 24 (tableros densos).

### 6.10 Bordes y sombras
- Radios recomendados: `--radius` para componentes, `--radius-lg` para modales, 50%/999 px para avatares y badges.
- Bordes estándar de 1 px; 2 px para focus activo o contenedores destacados.
- Sombras contextuales: `--shadow-sm` en tarjetas, `--shadow-md` en modales.

## 7. Componentes base
### 7.1 Botones
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

### 7.2 Inputs y formularios
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

### 7.3 Badges
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

## 8. Componentes compuestos
### 8.1 Tarjetas (Card)
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

### 8.2 Tablas
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

### 8.3 Modales
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

### 8.4 Tabs
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

### 8.5 Mensajes de estado
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

### 8.6 Spinner
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

## 9. Estados e interacciones
- **Hover**: elevar superficie con `--color-surface-hover` o incremento ligero en sombra.
- **Focus**: borde de 2 px con `--color-primary`; mantener contraste mínimo 3:1.
- **Active**: reforzar color principal o aplicar sombra interna (`box-shadow: inset 0 0 0 1px var(--color-primary)`).
- **Disabled**: reducir opacidad al 50%, deshabilitar pointer events cuando sea necesario.

Transiciones recomendadas:
- `all var(--transition-base)` para elementos interactivos.
- `transform 0.3s ease` en toggles de sidebar o paneles colapsables.

## 10. Visualización de datos y reportes
### 10.1 Configuración de Recharts
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

### 10.2 Visualizaciones analíticas (DDV)
- Destacar tendencias con degradados `fillOpacity 0.4–0.6`.
- Señalar eventos críticos con badges flotantes usando `--color-context-negative`.
- Sincronizar tooltips cuando varias gráficas comparten eje temporal.
- Usar `ReferenceLine` para marcar eventos de perforación con `strokeDasharray="4 4"`.

### 10.3 Visualizaciones de veredictos (FDA)
- Utilizar `verdict-banner` con borde lateral de 4 px y color semántico.
- Incluir iconos (`CheckCircle`, `XCircle`, `Clock`) acompañados de texto descriptivo.
- Para checklists, mostrar badges por ítem y un resumen colapsable por persona/vehículo.
- Renderizar markdown con `react-markdown`, `remark-gfm` y `remark-breaks` para resúmenes ejecutivos.

### 10.4 Visualizaciones de producción (SPA)
- **Area Chart apilado**: mostrar asignación por arena usando la paleta de 8 colores, `fillOpacity={0.6}`, `stackId="1"`.
- **Line Chart de declinación**: línea sólida para datos reales (`strokeWidth={2}`), línea punteada para curva ajustada (`strokeDasharray="8 4"`, `strokeWidth={2.5}`).
- **Reference Lines**: marcar fechas de intervención con líneas verticales (`strokeDasharray="4 4"`, `strokeOpacity={0.5}`), incluir label en posición `top`.
- **Tooltips**: mostrar unidades técnicas (bbl/d, md-ft) y parámetros de declinación (qi, Di, b, R²).
- **Legend**: usar `iconType="circle"` y `fontSize: 12` para diferenciar arenas.
- Validar que haya al menos 3 puntos de datos antes de ajustar curvas; mostrar advertencia si es insuficiente.

## 11. Patrones de pantalla unificados
### 11.1 Paneles analíticos (Analytics Ops)
- Layout de dos columnas (280 px controles / restante para visualizaciones).
- Header con breadcrumbs (Pozo → Dataset → Registro) y acciones rápidas.
- Tabs para cambiar entre KPIs, gráficos y logs de eventos.
- Estados previsibles: sin datos, cargando, error de conexión.

### 11.2 Validación documental (Compliance Ops)
- Flujo Wizard: carga → análisis → resultados.
- Barra superior con progreso y estado del pipeline (iconos + texto).
- Resultados divididos en tabs (Resumen, Documentos, Checklist) reutilizando `tab-bar`.
- Logs en tiempo real con timestamps HH:MM:SS y badges de severidad.

### 11.3 Asignación de producción (Petroleum Ops)
- **Wells**: tabla de pozos con badges de estado (new, prod, props, events, allocated), modal de creación con selección de modelo de declinación (exponencial, hiperbólica, armónica, best_fit).
- **Production**: file uploader con drag & drop para Excel (.xlsx, .xls), tabla de datos históricos, gráfico de líneas de producción total.
- **Petrophysics**: tabla de arenas con propiedades k·h (permeabilidad × espesor), modal de edición con validación numérica.
- **Events**: matriz de intervenciones (filas=arenas, columnas=fechas, celdas=checkbox), gestión de fechas de workover/completaciones.
- **Allocation**: tabs con Production Data (área apilada), Decline Curves (líneas ajustadas), Allocation Results (tabla), Decisions (log del motor), botón "Run Allocation", sección de warnings para datos insuficientes.
- **Users**: CRUD de usuarios con roles (admin/user), validación de username único y password mínimo 6 caracteres.

### 11.4 Patrones compartidos
- **Layout principal**: header fijo (56 px), sidebar 200 px colapsable, `app-main` con `padding: 24px`.
- **Empty states**: ilustración sutil + texto directo + CTA secundario.
- **Acciones masivas**: barras contextuales sobre tablas con botones outline.
- **Feedback**: `status-message` persistente para confirmaciones críticas.
- **Step indicators**: para flujos multi-paso (FDA wizard, SPA well configuration).
- **File uploaders**: drag & drop con alternativa de botón "Browse Files" para accesibilidad.

## 12. Header y Sidebar

### 12.1 Header

#### Estructura y dimensiones
```css
.header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  z-index: 50;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
```

#### Sección izquierda (Hamburger + Logo + Título)

**Hamburger Button:**
```css
.hamburger-btn {
  padding: 6px;
  border-radius: 6px;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: background-color 0.15s;
}
.hamburger-btn:hover {
  background-color: var(--color-surface-hover);
}
```

**Logo:**
```css
.logo {
  width: 28px;
  height: 28px;
  color: var(--color-primary);
}
```

**Título principal:**
```css
.header-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.3px;
  line-height: 1.2;
}
```

#### Sección derecha (Theme Toggle + User Info + Logout)

**Theme Toggle Button:**
```css
.theme-toggle {
  padding: 6px;
  border-radius: 6px;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: background-color 0.15s;
}
.theme-toggle:hover {
  background-color: var(--color-surface-hover);
}
```

**User Info:**
```css
.user-info {
  text-align: right;
}
.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
  line-height: 1.2;
}
.user-role {
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.2;
}
```

**Avatar:**
```css
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 500;
}
```

### 12.2 Sidebar

#### Estructura y dimensiones
```css
.sidebar {
  position: fixed;
  left: 0;
  top: 56px;
  bottom: 0;
  width: 200px;
  min-width: 200px;
  z-index: 40;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  transition: transform 0.3s ease;
}

.sidebar.hidden {
  transform: translateX(-100%);
}
```

#### Navegación
```css
.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  gap: 2px;
  overflow-y: auto;
}
```

#### Botones de módulo
```css
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: none;
  border: none;
  border-radius: 6px;
  color: var(--color-text-muted);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.12s;
  cursor: pointer;
  text-align: left;
  text-decoration: none;
}

.nav-item:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.nav-item.active {
  background: rgba(74, 124, 255, 0.12);
  color: var(--color-primary);
  font-weight: 600;
}
```

#### Iconos SVG (Heroicons Style)

**Especificaciones:**
- Tamaño: 18x18 píxeles
- ViewBox: 0 0 24 24
- Stroke: currentColor (hereda color del botón)
- StrokeWidth: 2
- StrokeLinecap: round
- StrokeLinejoin: round
- Fill: none (outline style)

**Ejemplos de iconos:**

```jsx
// Database/Wells
<svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
    d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
</svg>

// Chart Bar
<svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
</svg>

// Users
<svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
    d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
</svg>
```

## 13. Contenido y microcopy
### 13.1 Principios
1. Claridad operativa: verbos imperativos cortos ("Analizar", "Exportar", "Reintentar").
2. Contexto técnico: usar unidades aprobadas (m, psi, MB) o categorías oficiales (Aprobado, Pendiente, Observado).
3. Proactividad: ante errores, ofrecer siguiente paso o referencia ("Configura tu API Key" / "Ajusta filtros").
4. Consistencia lingüística: compartir glosario entre equipos para alinear términos (pozo, solicitud, checklist, veredicto).

### 13.2 Tonalidad por dominio
- **Analytics (DDV)**: insights basados en datos, tono consultivo ("Se detectó una anomalía en 3 registros").
- **Compliance (FDA)**: tono normativo y determinista ("Veredicto: Rechazado por licencia vencida").
- **Petroleum (SPA)**: precisión técnica, tono ingenieril ("Insufficient data for decline fit. Need at least 3 data points", "Allocation completed successfully").

### 13.3 Formatos
- **Fechas**: formato largo en español para resultados FDA (`8 de abril de 2026, 16:31 h`), formato ISO para datos de producción SPA (`YYYY-MM-DD`).
- **Logs**: timestamps `HH:MM:SS`.
- **Porcentajes**: un decimal (`92.4 %`).
- **Tamaños de archivo**: unidad apropiada (`1.2 MB`).
- **Unidades técnicas SPA**: producción con separador de miles (`1,234.5 bbl/d`), k·h con decimales (`2,500.00 md-ft`), parámetros de declinación (qi, Di, b, R²).
- **Unidades DDV**: profundidad (`m`, `ft`), presión (`psi`), temperatura (`°C`).

## 14. Implementación técnica
### 14.1 Tema y persistencia
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

### 14.2 Layout base
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

### 14.3 Scrollbar y accesibilidad
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

## 15. Animaciones y transiciones

### 15.1 Duración estándar
```css
transition: all 0.15s;
```

### 15.2 Transiciones específicas

#### Botones y elementos interactivos
```css
transition: all 0.15s;
```

#### Hover en superficies
```css
transition: all 0.12s;
```

#### Sidebar Toggle
```css
transition: transform 0.3s ease;
```

#### Spinner
```css
animation: spin 0.8s linear infinite;
```

### 15.3 Timing Functions
- **Default**: ease (implícito)
- **Linear**: usado en spinner
- **Ease**: para transiciones suaves

### 15.4 Buenas prácticas
- Transiciones limitadas a propiedades específicas cuando sea posible para mejor performance
- Evitar transiciones en `all` para elementos que cambian frecuentemente
- Mantener duraciones bajo 300ms para respuesta inmediata
- Usar `will-change` con precaución en elementos animados críticos

## 16. Checklist de implementación
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

## 17. Glosario rápido
- **Analytics Ops (DDV)**: módulos de exploración y monitoreo de datos de perforación, detección de anomalías.
- **Compliance Ops (FDA)**: flujos de verificación documental y permisos regulados.
- **Petroleum Ops (SPA)**: módulos de asignación de producción por arenas y análisis de curvas de declinación.
- **Veredicto**: resultado global de la evaluación de una solicitud (Aprobado/Rechazado/Pendiente).
- **Checklist**: subconjunto de validaciones individuales asociadas a una persona, vehículo o pozo.
- **Pipeline**: secuencia de pasos automatizados para procesar datos o documentos.
- **Arena (Sand)**: capa productora de petróleo con propiedades petrofísicas específicas (k·h).
- **k·h**: producto de permeabilidad (k) por espesor (h), medida en md-ft.
- **Decline Curve**: curva de declinación de producción (exponencial, hiperbólica, armónica).
- **Intervention Matrix**: matriz que define qué arenas están abiertas/cerradas en cada fecha de workover.
- **Allocation**: proceso de asignar producción total del pozo a cada arena productora.
- **qi, Di, b**: parámetros de curvas de declinación (producción inicial, tasa de declinación, exponente hiperbólico).
- **R²**: coeficiente de correlación que indica calidad del ajuste de curva.

## 18. Gobierno del sistema
- Nombrar un *Design Ops Owner* responsable de aprobar nuevas variantes.
- Registrar cambios en un changelog compartido y versionar tokens (ej. `tokens@2.1.0`).
- Alinear ciclos de release entre DDV, FDA y SPA para evitar divergencias de componentes.
- Incorporar QA visual y pruebas de accesibilidad en el pipeline de CI/CD.
- Mantener sincronización de componentes compartidos entre las tres aplicaciones.
- Documentar casos de uso específicos por dominio cuando se desvíen del patrón base.

## 19. Consideraciones específicas por aplicación

### 19.1 DDV (Drilling Data Visualization)
- **Componentes únicos**: ChartWrapper con sincronización de tooltips, MetricCard con tendencias, DataTable con selección de columnas.
- **Patrones de navegación**: breadcrumbs jerárquicos (Pozo → Dataset → Análisis).
- **Visualizaciones**: énfasis en series temporales, detección de outliers, overlays de eventos.
- **Stack técnico**: React/Tailwind, Recharts, backend científico Python.

### 19.2 FDA (Sistema de Verificación de Permisos)
- **Componentes únicos**: VerdictBanner, ChecklistItem, FileItem, Pipeline Steps, Log Console.
- **Patrones de navegación**: wizard lineal (Nueva Solicitud → Análisis → Resultados).
- **Visualizaciones**: markdown renderizado, badges semánticos, agrupación por persona/vehículo.
- **Stack técnico**: React 19 + Vite, Express, PostgreSQL, OpenAI GPT-4.1.

### 19.3 SPA (Subsurface Production Allocation)
- **Componentes únicos**: Matrix Editor (intervenciones), Step Indicator (4 pasos), Well Status Badges.
- **Patrones de navegación**: módulos independientes (Wells, Production, Petrophysics, Events, Allocation, Users).
- **Visualizaciones**: área apilada multi-arena, curvas de declinación con ajuste, reference lines para intervenciones.
- **Stack técnico**: React 19 + Vite, Express, PostgreSQL, Recharts, ml-levenberg-marquardt.

---

## 20. Notas adicionales

### 20.1 Consideraciones responsive
- Las aplicaciones están diseñadas principalmente para desktop (≥1280px)
- Sidebar colapsable en móviles con botón hamburguesa
- Usar `min-width` y `max-width` para contenedores de formularios
- Padding de 24px en móviles puede reducirse a 16px si es necesario
- Tablas con scroll horizontal en pantallas pequeñas
- Gráficos con `ResponsiveContainer` de Recharts para adaptación automática
- Breakpoints recomendados:
  - Mobile: < 768px
  - Tablet: 768px - 1024px
  - Desktop: ≥ 1024px
  - Large Desktop: ≥ 1280px

### 20.2 Accesibilidad
- Todos los botones interactivos tienen `cursor: pointer` y labels descriptivos
- Focus states claramente definidos con `--color-border-focus` y visibles en ambos temas
- Contraste de colores cumple con WCAG AA (verificar con herramientas automáticas al introducir nuevos tonos)
- Transiciones suaves (<200 ms) para evitar mareos y mantener respuesta inmediata
- Drag & drop: proporcionar alternativa con botón "Browse Files" para usuarios con limitaciones motoras
- Status badges: usar color + texto para no depender solo del color
- Gráficos: incluir tooltips descriptivos y legend para facilitar interpretación de datos
- Tablas: headers sticky para mantener contexto al hacer scroll
- Navegación por teclado: todos los elementos interactivos deben ser accesibles con Tab
- Roles ARIA apropiados en componentes complejos (modales, tabs, accordions)
- Alt text descriptivo en imágenes e ilustraciones

### 20.3 Performance
- Transiciones limitadas a propiedades específicas cuando sea posible
- Variables CSS para evitar recálculos
- SVG inline para iconos (sin dependencias adicionales)
- Recharts con `ResponsiveContainer` para optimizar renderizado
- Lazy loading de datos para tablas con muchos registros
- Debounce en inputs de búsqueda y filtros
- Memoización de componentes pesados (gráficos, tablas grandes)
- Code splitting por rutas principales
- Optimización de imágenes (WebP cuando sea posible)

### 20.4 Consideraciones de ingeniería (SPA)
- **Unidades**: Mantener consistencia en unidades (bbl/d para producción, md-ft para k·h)
- **Precisión numérica**: Usar decimales apropiados (2 decimales para k·h, 1 decimal para producción)
- **Validación de datos**: Verificar que fechas sean cronológicas y valores sean positivos
- **Curvas de declinación**: Mostrar R² para indicar calidad del ajuste
- **Warnings**: Alertar cuando hay menos de 3 puntos para ajuste de curva

### 20.5 Consideraciones de validación (FDA)
- **Procesamiento asíncrono**: Mostrar progreso en tiempo real durante análisis de documentos
- **Manejo de errores**: Mensajes claros cuando fallan llamadas a API de OpenAI
- **Caché de resultados**: Evitar reprocesar documentos ya analizados
- **Logs detallados**: Registrar cada paso del pipeline para debugging
- **Timeouts**: Configurar timeouts apropiados para análisis largos

### 20.6 Consideraciones de análisis (DDV)
- **Manejo de datasets grandes**: Implementar paginación o virtualización
- **Sincronización de gráficos**: Mantener tooltips sincronizados en vistas comparativas
- **Detección de anomalías**: Usar colores consistentes para alertas
- **Exportación de datos**: Permitir exportar resultados filtrados a CSV/Excel

### 20.7 Jerarquía de Z-Index
- **Header**: 50 (fijo en la parte superior)
- **Modal backdrop**: 50 (mismo nivel que header)
- **Sidebar**: 40 (fijo debajo del header)
- **Tooltips**: default de Recharts
- **Dropdowns**: 30
- **Contenido principal**: 1 (default)

### 20.8 Dimensiones clave
- **Header height**: 56px (fijo)
- **Sidebar width**: 200px (cuando está abierto)
- **Sidebar top**: 56px (debajo del header)
- **Main content margin-top**: 56px (para compensar header fijo)
- **Main content margin-left**: 200px (cuando sidebar abierto), 0px (cuando cerrado)
- **Main content padding**: 24px
- **Modal max-width**: 460px (pequeño), 500px (mediano), 800px (grande)
- **Form max-width**: 600px
- **Card padding**: 20px

---

**Versión**: 3.0 (Unificación POI - Tres Aplicaciones)

**Última actualización**: abril 2026  
**Aplicaciones cubiertas**: 
- Drilling Data Visualization (DDV)
- Sistema de Verificación de Permisos OIG Perú (FDA)
- Subsurface Production Allocation (SPA)

**Stack de referencia**: React 19 · Vite · Tailwind/Vanilla CSS · Recharts · Express · PostgreSQL · OpenAI · ml-levenberg-marquardt

---

**Mantenimiento de esta guía:**
- Actualizar tokens cuando se introduzcan nuevos colores o espaciados
- Documentar nuevos componentes con ejemplos de código
- Registrar cambios en changelog con fecha y versión
- Validar compatibilidad entre las tres aplicaciones antes de cada release
- Revisar accesibilidad con herramientas automatizadas trimestralmente
