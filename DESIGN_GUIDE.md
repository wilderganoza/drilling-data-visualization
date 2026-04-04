![alt text](image.png)# Guía de Diseño Visual - Drilling Data Visualization

## Índice
1. [Sistema de Colores](#sistema-de-colores)
2. [Tipografía](#tipografía)
3. [Espaciado y Layout](#espaciado-y-layout)
4. [Bordes y Sombras](#bordes-y-sombras)
5. [Componentes UI](#componentes-ui)
6. [Header y Sidebar](#header-y-sidebar)
7. [Gráficos y Visualizaciones](#gráficos-y-visualizaciones)
8. [Animaciones y Transiciones](#animaciones-y-transiciones)
9. [Estados Interactivos](#estados-interactivos)
10. [Layout Principal](#layout-principal)

---

## Sistema de Colores

### Variables CSS Base
La aplicación utiliza un sistema de variables CSS que permite cambiar entre tema claro y oscuro.

#### Colores Invariables (Ambos Temas)
```css
--radius: 8px;
--color-primary: #4a7cff;
--color-primary-hover: #3a6aee;
--color-success: #34d399;
--color-warning: #fbbf24;
--color-danger: #f87171;
```

#### Colores de Gráficos (Paleta de 8 colores)
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

### Tema Oscuro (Dark Mode)
```css
[data-theme="dark"] {
  --color-bg: #0f1117;              /* Fondo principal */
  --color-surface: #1a1d27;         /* Superficies (cards, modales) */
  --color-surface-hover: #232733;   /* Hover en superficies */
  --color-border: #2a2e3a;          /* Bordes */
  --color-border-focus: #4a7cff;    /* Bordes en focus */
  --color-text: #e4e6ed;            /* Texto principal */
  --color-text-muted: #8b8fa3;      /* Texto secundario/muted */
  --shadow: 0 2px 8px rgba(0,0,0,0.3);
  --color-chart-line: #ffffff;      /* Líneas en gráficos */
  --color-chart-axis: #8b8fa3;      /* Ejes de gráficos */
  --color-tooltip-bg: #1a1d27;      /* Fondo de tooltips */
  --color-tooltip-border: #2a2e3a;  /* Borde de tooltips */
}
```

### Tema Claro (Light Mode)
```css
[data-theme="light"] {
  --color-bg: #f5f7fa;              /* Fondo principal */
  --color-surface: #ffffff;         /* Superficies (cards, modales) */
  --color-surface-hover: #f0f2f5;   /* Hover en superficies */
  --color-border: #e1e4e8;          /* Bordes */
  --color-border-focus: #4a7cff;    /* Bordes en focus */
  --color-text: #1a1d27;            /* Texto principal */
  --color-text-muted: #6b7280;      /* Texto secundario/muted */
  --shadow: 0 2px 8px rgba(0,0,0,0.08);
  --color-chart-line: #1a1d27;      /* Líneas en gráficos */
  --color-chart-axis: #6b7280;      /* Ejes de gráficos */
  --color-tooltip-bg: #ffffff;      /* Fondo de tooltips */
  --color-tooltip-border: #e1e4e8;  /* Borde de tooltips */
}
```

### Colores Semánticos con Opacidad

#### Success (Verde)
- Fondo: `rgba(52, 211, 153, 0.1)` 
- Borde: `rgba(52, 211, 153, 0.3)` 
- Texto: `var(--color-success)` (#34d399)
- Badge: `rgba(52, 211, 153, 0.15)` 

#### Warning (Amarillo)
- Fondo: `rgba(251, 191, 36, 0.1)` 
- Borde: `rgba(251, 191, 36, 0.3)` 
- Texto: `var(--color-warning)` (#fbbf24)
- Badge: `rgba(251, 191, 36, 0.15)` 

#### Danger (Rojo)
- Fondo: `rgba(248, 113, 113, 0.1)` 
- Borde: `rgba(248, 113, 113, 0.3)` 
- Texto: `var(--color-danger)` (#f87171)
- Badge: `rgba(248, 113, 113, 0.15)` 

#### Primary (Azul)
- Fondo: `rgba(74, 124, 255, 0.12)` (activo)
- Hover: `rgba(74, 124, 255, 0.08)` 
- Badge: `rgba(74, 124, 255, 0.15)` 

#### Muted (Gris)
- Badge: `rgba(139, 143, 163, 0.15)` 

#### Purple (Púrpura)
- Badge: `rgba(167, 139, 250, 0.15)` 
- Texto: `#a78bfa` 

---

## Tipografía

### Familia de Fuentes
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

**Nota importante**: La fuente Inter debe estar cargada en el proyecto mediante Google Fonts:
```html
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
```

**Características de Inter:**
- Fuente sans-serif moderna y legible
- Optimizada para interfaces de usuario
- Excelente legibilidad en tamaños pequeños
- Soporta múltiples pesos (400, 500, 600, 700)

### Jerarquía de Tamaños

#### Títulos
- **H1 (Página principal)**: 22px, font-weight: 700, line-height: 1.2
- **H2 (Secciones)**: 20px, font-weight: 700, line-height: 1.3
- **H3 (Subsecciones)**: 16px, font-weight: 600, line-height: 1.4
- **H4 (Componentes)**: 14-15px, font-weight: 600, line-height: 1.4

#### Header
- **Título principal**: 18px, font-weight: 700, letter-spacing: -0.3px, line-height: 1.2
- **Nombre de usuario**: 13px, font-weight: 500, line-height: 1.2
- **Rol de usuario**: 12px, color: muted, line-height: 1.2
- **Avatar**: 14px, font-weight: 500

#### Sidebar
- **Labels de módulos**: 14px, font-weight: 500 (normal), 600 (activo)

#### Texto de Cuerpo
- **Normal**: 14px, line-height: 1.6
- **Pequeño**: 13px, line-height: 1.5
- **Muy pequeño**: 12px, line-height: 1.4
- **Micro**: 11px, line-height: 1.3

#### Botones
- **Normal**: 14px, font-weight: 500-600, line-height: 1
- **Pequeño**: 12px, font-weight: 500, line-height: 1
- **Grande**: 15px, font-weight: 600, line-height: 1

#### Formularios
- **Labels**: 13px, font-weight: 500, color: muted
- **Inputs**: 14px, line-height: 1.4
- **Placeholders**: 14px, color: muted
- **Error messages**: 13px, color: danger

#### Tablas
- **Headers**: 11px, font-weight: 600, text-transform: uppercase, letter-spacing: 0.5px
- **Celdas**: 13px, line-height: 1.4

#### Modales
- **Título**: 18px, font-weight: 600
- **Cuerpo**: 14px, line-height: 1.6
- **Botones**: 14px, font-weight: 500-600

#### Badges
- **General**: 11-12px, font-weight: 500-600

#### Gráficos
- **Ejes (ticks)**: 11px
- **Legend**: 12px
- **Tooltips**: 13px
- **Labels**: 12-13px

### Font Weights Utilizados
- **400**: Normal (default para texto de cuerpo)
- **500**: Medium - Labels, botones normales, texto de usuario
- **600**: Semibold - Subtítulos, headers de tabla, botones activos, badges
- **700**: Bold - Títulos principales (H1, H2, Header title)

### Letter Spacing
- **Headers de tabla**: 0.5px
- **Títulos principales (H1, Header)**: -0.3px
- **Normal**: 0 (default)
- **Uppercase text**: 0.5px

---

## Espaciado y Layout

### Sistema de Espaciado
La aplicación usa un sistema de espaciado consistente basado en múltiplos de 4px:

#### Espaciado Interno (Padding)
- **Micro**: 4px
- **Pequeño**: 8px
- **Mediano**: 12px
- **Normal**: 16px
- **Grande**: 20px
- **Extra grande**: 24px
- **XXL**: 40px

#### Espaciado Externo (Margin)
- **Entre elementos pequeños**: 4px
- **Entre elementos relacionados**: 8px
- **Entre grupos**: 16px
- **Entre secciones**: 20-24px

#### Gaps en Flexbox
- **Muy ajustado**: 2px
- **Ajustado**: 4px
- **Pequeño**: 6px
- **Normal**: 8px
- **Mediano**: 10-12px
- **Grande**: 16px
- **Extra grande**: 18px

---

## Bordes y Sombras

### Radio de Bordes
- **Estándar**: `var(--radius)` = 8px
- **Pequeño**: 4px
- **Mediano**: 6px
- **Grande**: 12px
- **Circular**: 50% o 999px (badges, avatares)

### Grosor de Bordes
- **Estándar**: 1px
- **Dashed (upload)**: 2px dashed
- **Focus/Active**: 2px

### Sombras

#### Tema Oscuro
```css
--shadow: 0 2px 8px rgba(0,0,0,0.3);
```
- **Modal**: `0 20px 40px rgba(15, 23, 42, 0.35)` 
- **Card**: `0 4px 24px rgba(0, 0, 0, 0.4)` 

#### Tema Claro
```css
--shadow: 0 2px 8px rgba(0,0,0,0.08);
```
- **Modal**: `0 20px 40px rgba(15, 23, 42, 0.15)` 
- **Card**: `0 4px 24px rgba(0, 0, 0, 0.1)` 

---

## Componentes UI

### Botones

#### Botón Estándar
```css
.btn {
  padding: 8px 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.btn:hover {
  background: var(--color-surface-hover);
}
```

#### Botón Primario
```css
.btn-primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  font-weight: 600;
}
.btn-primary:hover {
  background: var(--color-primary-hover);
}
```

#### Botón Peligro
```css
.btn-danger {
  border-color: var(--color-danger);
  color: var(--color-danger);
}
.btn-danger:hover {
  background: rgba(248,113,113,0.1);
}
```

#### Botón Pequeño
```css
.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}
```

#### Botón Grande
```css
.btn-lg {
  padding: 10px 28px;
  font-size: 15px;
  font-weight: 600;
}
```

#### Botón Deshabilitado
```css
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### Inputs y Formularios

#### Input Estándar
```css
.input {
  padding: 8px 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  color: var(--color-text);
  font-size: 14px;
  transition: border-color 0.15s;
}
.input:focus {
  outline: none;
  border-color: var(--color-border-focus);
}
```

#### Form Group
```css
.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  font-size: 13px;
  color: var(--color-text-muted);
  margin-bottom: 4px;
  font-weight: 500;
}
```

#### Select
```css
.form-group select {
  width: 100%;
  padding: 8px 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  color: var(--color-text);
  font-size: 14px;
}
.form-group select:focus {
  outline: none;
  border-color: var(--color-border-focus);
}
```

### Tablas

#### Tabla de Datos
```css
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
}
.data-table th {
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-weight: 600;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.5px;
  position: sticky;
  top: 0;
}
.data-table tr:hover td {
  background: var(--color-surface-hover);
}
```

### Modales

#### Estructura
```css
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: 24px;
}

.modal {
  background: var(--color-surface);
  border-radius: 12px;
  border: 1px solid var(--color-border);
  width: 100%;
  max-width: 460px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.35);
}

.modal-header,
.modal-footer {
  padding: 16px 20px;
}

.modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text);
}

.modal-body {
  padding: 0 20px 20px;
}

.modal-footer {
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
```

### Tabs

#### Tab Bar
```css
.tab-bar {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0;
  margin-bottom: 16px;
}

.tab-btn {
  padding: 8px 16px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  cursor: pointer;
}

.tab-btn:hover {
  color: var(--color-text);
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
```

### Badges de Estado

```css
.badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 600;
  display: inline-block;
}

.badge.success {
  background: rgba(52, 211, 153, 0.15);
  color: var(--color-success);
}

.badge.warning {
  background: rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
}

.badge.danger {
  background: rgba(248, 113, 113, 0.15);
  color: var(--color-danger);
}

.badge.primary {
  background: rgba(74, 124, 255, 0.15);
  color: var(--color-primary);
}

.badge.muted {
  background: rgba(139, 143, 163, 0.15);
  color: var(--color-text-muted);
}

.badge.purple {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
}
```

### Status Messages

```css
.status-message {
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-message.success {
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: var(--color-success);
}

.status-message.error {
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  color: var(--color-danger);
}

.status-message.warning {
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
  color: var(--color-warning);
}

.status-message.info {
  background: rgba(74, 124, 255, 0.1);
  border: 1px solid rgba(74, 124, 255, 0.3);
  color: var(--color-primary);
}
```

### Spinner (Loading)

```css
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

---

## Header y Sidebar

### Header

#### Estructura y Dimensiones
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

#### Sección Izquierda (Hamburger + Logo + Título)

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

**Icon SVG:**
```jsx
<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
    d="M4 6h16M4 12h16M4 18h16" />
</svg>
```

**Logo:**
```css
.logo {
  width: 28px;
  height: 28px;
  color: var(--color-primary);
}
```

**Título Principal:**
```css
.header-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.3px;
  line-height: 1.2;
}
```

**Subtítulo (opcional):**
```css
.header-subtitle {
  font-size: 12px;
  color: var(--color-text-muted);
}
```

#### Sección Derecha (Theme Toggle + User Info + Logout)

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

**Logout Button:**
```css
.logout-btn {
  padding: 6px;
  border-radius: 6px;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: background-color 0.15s;
}
.logout-btn:hover {
  background-color: var(--color-surface-hover);
}
```

### Sidebar

#### Estructura y Dimensiones
```css
.sidebar {
  position: fixed;
  left: 0;
  top: 56px;              /* Debajo del header */
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

#### Botones de Módulo
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

**Ejemplos de Iconos:**

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

---

## Gráficos y Visualizaciones

### Recharts Configuration

#### Ejes (XAxis, YAxis)
```javascript
<XAxis 
  dataKey="date" 
  tick={{ fontSize: 11, fill: 'var(--color-chart-axis)' }}
  stroke="var(--color-border)"
/>
<YAxis 
  tick={{ fontSize: 11, fill: 'var(--color-chart-axis)' }}
  stroke="var(--color-border)"
/>
```

#### Tooltip
```javascript
<Tooltip
  contentStyle={{ 
    background: 'var(--color-tooltip-bg)', 
    border: `1px solid var(--color-tooltip-border)`, 
    borderRadius: 8, 
    fontSize: 13,
    color: 'var(--color-text)'
  }}
  labelStyle={{ color: 'var(--color-text)' }}
/>
```

#### Legend
```javascript
<Legend 
  wrapperStyle={{ fontSize: 12 }}
  iconType="circle"
/>
```

#### Grid Lines
```javascript
<CartesianGrid 
  strokeDasharray="3 3" 
  stroke="var(--color-border)"
  opacity={0.3}
/>
```

#### Reference Lines
```javascript
<ReferenceLine
  x={date}
  stroke="var(--color-chart-line)"
  strokeDasharray="4 4"
  strokeOpacity={0.5}
/>
```

#### Area Chart
```javascript
<Area
  type="monotone"
  dataKey={dataKey}
  stroke={color}
  fill={color}
  fillOpacity={0.6}
  strokeWidth={2}
/>
```

#### Line Chart
```javascript
<Line
  type="monotone"
  dataKey={dataKey}
  stroke={color}
  strokeWidth={2}
  dot={{ r: 3 }}
/>
```

#### Chart Container
```javascript
<ResponsiveContainer width="100%" height={400}>
  {/* Chart content */}
</ResponsiveContainer>
```

### Colores Dinámicos en Gráficos

Para obtener valores de variables CSS en JavaScript:
```javascript
const chartLineColor = getComputedStyle(document.documentElement)
  .getPropertyValue('--color-chart-line').trim();
const chartAxisColor = getComputedStyle(document.documentElement)
  .getPropertyValue('--color-chart-axis').trim();
```

---

## Animaciones y Transiciones

### Duración Estándar
```css
transition: all 0.15s;
```

### Transiciones Específicas

#### Botones y Elementos Interactivos
```css
transition: all 0.15s;
```

#### Hover en Superficies
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

### Timing Functions
- **Default**: ease (implícito)
- **Linear**: usado en spinner
- **Ease**: para transiciones suaves

---

## Estados Interactivos

### Hover States

#### Botones
```css
.btn:hover {
  background: var(--color-surface-hover);
}
```

#### Botón Primario
```css
.btn-primary:hover {
  background: var(--color-primary-hover);
}
```

#### Botón Danger
```css
.btn-danger:hover {
  background: rgba(248,113,113,0.1);
}
```

#### Filas de Tabla
```css
.data-table tr:hover td {
  background: var(--color-surface-hover);
}
```

#### Nav Items
```css
.nav-item:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}
```

#### Tabs
```css
.tab-btn:hover {
  color: var(--color-text);
}
```

### Focus States

#### Inputs
```css
.input:focus {
  outline: none;
  border-color: var(--color-border-focus);
}
```

#### Selects
```css
select:focus {
  outline: none;
  border-color: var(--color-border-focus);
}
```

### Active States

#### Nav Items
```css
.nav-item.active {
  background: rgba(74, 124, 255, 0.12);
  color: var(--color-primary);
  font-weight: 600;
}
```

#### Tabs
```css
.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
```

### Disabled States

#### Botones
```css
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

---

## Layout Principal

### Estructura HTML/React

```jsx
function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const toggleSidebar = () => {
    setSidebarOpen(prev => !prev);
  };

  return (
    <div className="app-layout">
      <Header onToggleSidebar={toggleSidebar} />
      <Sidebar isOpen={sidebarOpen} />
      <main 
        className="app-main" 
        style={{ 
          marginLeft: sidebarOpen ? '200px' : '0', 
          marginTop: '56px' 
        }}
      >
        {/* Contenido de la página */}
      </main>
    </div>
  );
}
```

### CSS del Layout

```css
.app-layout {
  min-height: 100vh;
  width: 100%;
  background: var(--color-bg);
}

.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  transition: margin-left 0.3s ease;
  padding: 24px;
}
```

### Jerarquía de Z-Index

- **Header**: 50 (fijo en la parte superior)
- **Modal backdrop**: 50 (mismo nivel que header)
- **Sidebar**: 40 (fijo debajo del header)
- **Tooltips**: default de Recharts
- **Contenido principal**: 1 (default)

### Dimensiones Clave

- **Header height**: 56px (fijo)
- **Sidebar width**: 200px (cuando está abierto)
- **Sidebar top**: 56px (debajo del header)
- **Main content margin-top**: 56px (para compensar header fijo)
- **Main content margin-left**: 200px (cuando sidebar abierto), 0px (cuando cerrado)
- **Main content padding**: 24px

### Transiciones

- **Sidebar toggle**: 0.3s ease (transform)
- **Main content margin**: 0.3s ease (margin-left)
- **Sincronización**: Ambas transiciones tienen la misma duración para movimiento fluido

---

## Scrollbar Personalizado

```css
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: var(--color-bg);
}

::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-muted);
}
```

---

## Implementación del Sistema de Temas

### Cambio de Tema
El tema se controla mediante el atributo `data-theme` en el elemento `html`:
```javascript
document.documentElement.setAttribute('data-theme', 'light'); // o 'dark'
```

### Persistencia del Tema
El tema se guarda en `localStorage`:
```javascript
localStorage.setItem('theme', 'light');
const theme = localStorage.getItem('theme') || 'dark';
```

### Hook useTheme (React)
```typescript
import { useState, useEffect } from 'react';

export const useTheme = () => {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme');
    return (saved as 'light' | 'dark') || 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  return { theme, toggleTheme };
};
```

---

## Checklist de Implementación

Para replicar estos estilos en otra aplicación:

- [x] Configurar variables CSS en `:root` y `[data-theme]` 
- [x] Implementar sistema de cambio de tema con localStorage
- [x] Configurar familia de fuentes Inter
- [x] Crear componentes base: botones, inputs, tablas
- [x] Implementar sistema de colores semánticos con opacidad
- [x] Configurar Recharts con colores dinámicos
- [x] Implementar scrollbar personalizado
- [x] Crear componentes de layout: sidebar, header
- [x] Implementar sistema de tabs
- [x] Crear componentes de status y badges
- [x] Configurar transiciones y animaciones
- [x] Crear modales con backdrop
- [x] Implementar spinner
- [x] Configurar estados hover/focus/active/disabled

---

## Notas Adicionales

### Responsive Considerations
- La aplicación está diseñada principalmente para desktop
- Usa `min-width` y `max-width` para contenedores
- Los gráficos usan `ResponsiveContainer` de Recharts
- Padding de 24px en móviles puede reducirse si es necesario

### Accesibilidad
- Todos los botones interactivos tienen cursor: pointer
- Focus states claramente definidos con `--color-border-focus`
- Contraste de colores cumple con WCAG AA
- Transiciones suaves para mejor UX

### Performance
- Transiciones limitadas a propiedades específicas cuando sea posible
- Variables CSS para evitar recálculos
- SVG inline para iconos (sin dependencias adicionales)

---

**Versión**: 2.0  
**Última actualización**: Abril 2026  
**Aplicación**: Drilling Data Visualization  
**Basado en**: Subsurface Production Allocation Design System
