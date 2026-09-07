# Integración en tiempo real con el sistema SZJ-II (WITS0)

Este documento explica, de punta a punta, cómo conectar nuestra app al
sistema de captura de datos de perforación SZJ-II para recibir información
en tiempo real: qué hay que hacer en el equipo del taladro, qué se construyó
de nuestro lado, cómo activarlo pozo por pozo, y cómo verificar que los
datos que llegan son correctos antes de confiar en ellos.

Está pensado para dos lectores distintos:
- Quien coordina con JPIM / el personal del taladro (sección 1).
- Quien mantiene o extiende esta app (secciones 2 en adelante).

---

## 1. Qué hay que hacer en el sistema SZJ-II (lado taladro)

El manual del SZJ-II (sección 2.2.6.6, "Third-party data communication")
confirma que el sistema expone un canal WITS0 — el protocolo estándar de la
industria para transmitir datos de perforación en tiempo real por TCP, en
texto ASCII plano. Es el mecanismo oficial pensado exactamente para esto:
que un sistema de terceros (nuestra app) reciba los datos sin tocar la base
de datos interna del SZJ-II.

Checklist de coordinación, **para cada uno de los 3 taladros**:

1. **Confirmar que el canal WITS0 está habilitado** en el software del
   SZJ-II instalado en ese taladro. Es una opción de configuración del
   sistema (no viene activada exportando datos por sí sola en todas las
   instalaciones) — hay que pedirle al operador/ingeniero de JPIM en sitio
   que lo verifique o lo active.

2. **Decidir el modo de conexión** — hay dos formas de establecer el canal
   TCP, y hay que confirmar cuál soporta/prefiere el equipo instalado:
   - **El SZJ-II se conecta hacia nosotros** ("server" desde nuestro punto
     de vista): nosotros abrimos un puerto y escuchamos, el equipo del
     taladro se conecta como cliente. Requiere que el taladro tenga
     visibilidad de red hacia nuestro servidor (o VPN).
   - **Nosotros nos conectamos hacia el SZJ-II** ("client" desde nuestro
     punto de vista): el equipo del taladro escucha en una IP:puerto fijos,
     nosotros nos conectamos como cliente. Requiere que nuestro servidor
     tenga visibilidad de red hacia esa IP del taladro.
   En la mayoría de instalaciones de este tipo, el SZJ-II actúa como
   servidor WITS0 (opción "nosotros nos conectamos"), pero hay que
   confirmarlo con JPIM — el sistema soporta ambos modos.

3. **Obtener, por cada taladro**: la IP y el puerto TCP configurados para el
   canal WITS0 (si el SZJ-II es el servidor), o confirmar el puerto en el
   que debemos escuchar (si nosotros somos el servidor). Los 3 equipos
   estarán en taladros físicamente distintos, así que cada uno tendrá su
   propia IP — hay que pedir esta tripleta (IP, puerto, modo) una vez por
   taladro.

4. **Pedir el archivo `WITS_Predefined_xx.ini`** (o el listado impreso de
   record/item) del equipo instalado. Este archivo NO viene en el manual
   general del SZJ-II — es específico de cada instalación/vendor y define
   qué código de 4 dígitos (record + item) corresponde a cada canal (
   profundidad de broca, peso sobre broca, RPM, presión de standpipe, ROP,
   etc.) y en qué unidades viene cada uno. **Sin este archivo no podemos
   mapear los datos de forma segura** — ver sección 3 para el motivo exacto.

5. **Confirmar alcance de red** entre nuestro servidor y cada taladro:
   VPN, IP pública, o red corporativa compartida. Si los taladros están en
   sitios remotos sin salida a internet fija, puede hacer falta una VPN
   site-to-site o un túnel — esto es una conversación de IT, no de la app.

6. **Probar la conexión de forma aislada** antes de la puesta en marcha
   real: con `netcat`/`telnet` (o el "debug" test de conexión que trae
   nuestra pantalla de Taladros, ver sección 4) confirmar que el puerto
   responde y que se ven tramas `&&...!!` llegando por texto plano.

Nada de esto requiere cambios en la base de datos ni en la lógica interna
del SZJ-II — es una función de exportación que el sistema ya trae, solo hay
que habilitarla y obtener sus parámetros de conexión.

---

## 2. Qué se construyó de nuestro lado — arquitectura

### 2.1 Separación Rig / RealtimeSource

Se modelaron dos conceptos distintos, deliberadamente separados:

- **`Rig`** (`ops_rigs`) — catálogo de los taladros físicos. Una fila por
  cada uno de los 3 equipos, creada una sola vez: nombre, modo de conexión
  (`client`/`server`), host, puerto, activo/inactivo, notas. No cambia con
  cada pozo — es el hardware.
- **`RealtimeSource`** (`ops_realtime_sources`) — el vínculo *histórico*
  entre un Rig y un Event (pozo/campaña). Se crea y se habilita cuando ese
  taladro empieza a perforar un pozo, se deshabilita (sin borrarse) cuando
  termina o se mueve a otro pozo. Guarda estado observado (`connecting`,
  `connected`, `disconnected`, `error`), último error, última llegada de
  datos, y contador de filas insertadas.

Esta separación permite que un mismo taladro tenga historial de conexión a
lo largo de muchos pozos distintos en su vida útil, y evita "doble uso": la
base de datos garantiza, con dos índices únicos parciales (solo sobre las
filas `enabled = true`), que:
- Un taladro no puede estar transmitiendo a dos eventos a la vez.
- Un evento no puede tener dos canales activos a la vez.

Esto es justo lo que responde a la pregunta "tenemos este equipo en 3
taladros, ¿cómo distinguimos cuáles son?" — cada `Rig` es una fila
independiente con su propia IP/puerto, y activar el canal para un pozo es
simplemente elegir cuál `Rig` le corresponde en ese momento.

### 2.2 El parser WITS0

`app/services/realtime/wits0.py` implementa el protocolo puro, sin ninguna
suposición específica del SZJ-II:
- Una trama empieza con una línea `&&` y termina con `!!`.
- Cada línea intermedia es un código de 4 dígitos (2 de "record" + 2 de
  "item") seguido del valor, ej. `0108 4521.30` = record 1, item 8, valor
  `4521.30`.
- `parse_wits0_text()` — parser síncrono, usado en tests.
- `iter_wits0_frames(reader)` — generador async que lee línea por línea de
  un `asyncio.StreamReader` y entrega una trama completa (`Wits0Frame`) cada
  vez que ve un `!!`. Una trama sin cerrar (otra `&&` antes del `!!`) se
  descarta, no se mezcla con la siguiente.
- `encode_wits0_frame()` — el inverso, usado para generar tramas de prueba.

Cubierto por 11 tests en [tests/test_wits0.py](../tests/test_wits0.py), incluyendo casos límite (tramas
truncadas, códigos no numéricos, ruido antes del primer `&&`).

### 2.3 El mapeo (record, item) → columna — deliberadamente vacío

`app/services/realtime/wits0_map.py` define `WITS_ITEM_MAP`, el diccionario
que traduce cada código WITS0 a una columna de `well_data_time` (con un
factor de escala/offset opcional para conversión de unidades). **Hoy está
vacío a propósito.**

Motivo: el estándar WITS0 público solo estandariza de forma parcial el
"record 1" (datos básicos de perforación); más allá de eso, y en la
práctica también dentro del record 1, cada fabricante define su propia
asignación en su `WITS_Predefined_xx.ini`. Adivinar esos códigos y
publicarlos como si estuvieran verificados escribiría silenciosamente el
dato de un sensor bajo el nombre de columna equivocado — un tipo de error
mucho peor que simplemente no ingerir ese canal todavía. Por eso cualquier
slot `(record, item)` que no esté en el mapeo se ignora sin error: no se
guarda, y tampoco rompe la ingesta de los demás canales que sí estén
mapeados.

**Cómo completarlo, una vez tengamos el `WITS_Predefined_xx.ini` real**
(instrucciones también documentadas como comentario en el propio archivo):

1. Abrir `app/services/realtime/wits0_map.py`.
2. Por cada canal de interés, agregar una entrada:
   ```python
   WITS_ITEM_MAP: dict[tuple[int, int], WitsColumn] = {
       (1, 8):  WitsColumn("bit_depth_feet"),
       (1, 10): WitsColumn("weight_on_bit_klbs"),
       (1, 13): WitsColumn("rotary_rpm_rpm"),
       (1, 17): WitsColumn("standpipe_pressure_psi"),
       (1, 19): WitsColumn("rate_of_penetration_ft_per_hr"),
       # ... según lo que confirme el .ini del equipo
   }
   ```
3. Los nombres de columna deben coincidir con los de `well_data`/
   `well_data_time` (ver `app/constants/parameters.py`). Si la unidad del
   WITS0 no coincide con la de nuestra columna, usar `scale`/`offset`
   (`valor_final = valor_wits * scale + offset`).
4. Correr `pytest tests/test_wits0.py -q` — valida que el parser y el mapeo
   siguen funcionando después de la edición.
5. Antes de confiar en datos en vivo con un mapeo nuevo, verificar la
   primera transmisión real (ver sección 5, "Verificación del mapeo").

Este archivo es intencionalmente el único lugar de todo el sistema que
necesita el `.ini` específico de cada instalación — todo lo demás (parser,
manager, modelos, UI) es genérico y no cambia entre taladros.

### 2.4 El gestor de ingesta en background (`RealtimeIngestManager`)

`app/services/realtime/ingest_manager.py` — un singleton (`realtime_manager`)
que vive durante toda la vida del proceso (arranca en `app.main`'s
`startup_event`, se apaga en `shutdown_event`, mismo patrón que `db_manager`).

Por cada `RealtimeSource` con `enabled=True` mantiene **una tarea asyncio**
que:
1. Se conecta al taladro (modo `client`) o espera a que el taladro se
   conecte (modo `server`, con timeout de 5 minutos).
2. Lee tramas WITS0 del socket a medida que llegan.
3. Traduce cada trama con `map_frame_to_row()` — si ningún slot está
   mapeado, la ignora silenciosamente (ver 2.3).
4. Inserta la fila resultante en `well_data_time`, sellada con
   `yyyy_mm_dd`/`hh_mm_ss` en el mismo formato que usan los datos ya
   importados.
5. Actualiza el estado observado (`status`, `last_data_at`,
   `rows_ingested`) como mucho cada 5 segundos (no en cada trama, para no
   golpear la base con un UPDATE por segundo si el equipo transmite rápido).
6. Si la conexión se cae o falla, reintenta automáticamente cada 5 segundos
   — hasta que alguien desactive el canal desde la UI, momento en el que la
   tarea se cancela y no vuelve a intentar.

El stack ORM de esta app es 100% síncrono (psycopg2), así que cada llamada
a la base dentro de esta tarea async pasa por `asyncio.to_thread(...)` —
así una consulta lenta nunca bloquea el loop de eventos que también está
leyendo el socket en vivo.

**Pozo nuevo sin datos legacy previos**: `well_data`/`well_data_time` son
tablas legacy indexadas por un `well_id` entero (tabla `wells`), no por el
UUID de la jerarquía ops. Si el pozo ops nunca se vinculó a un pozo legacy
(porque nunca se le importaron datos históricos), el manager crea
automáticamente ese vínculo la primera vez que necesita insertar un dato en
tiempo real para ese pozo — no hace falta ningún paso manual de
"preparación" antes de activar el canal.

**Bug real encontrado y corregido durante el desarrollo** (vale la pena
documentarlo porque puede reaparecer si se toca este archivo): en modo
`server`, `_accept_once()` originalmente hacía `server.close()` seguido de
`await server.wait_closed()` para dejar de escuchar tras aceptar la primera
conexión. Eso genera un **deadlock permanente**: `wait_closed()` espera a
que *todas* las conexiones que el server llegó a aceptar se cierren —
incluida la que se acababa de aceptar y que justamente se quería mantener
abierta para seguir leyendo datos. Se confirmó el cuelgue de forma aislada,
se corrigió quitando el `await wait_closed()` (dejando solo `server.close()`,
que basta para dejar de aceptar conexiones nuevas), y se volvió a confirmar
—con una prueba end-to-end real contra un socket y una base Postgres reales—
que el flujo completo funciona: conexión, dos tramas WITS0, inserción en
`well_data_time` con los valores y timestamps correctos.

### 2.5 Interfaz web

- **Catálogo de taladros** — `/master-data/rigs` (`app/web/rigs.py`,
  plantilla `ops/partials/rigs_table.html`). CRUD simple: nombre, modo
  (`client`/`server`), host, puerto, activo, notas. Accesible desde la
  página de Companies con el botón "📡 Rigs". Roles `ADMIN` /
  `OFFICE_ENGINEER`.
- **Activación por Event** — dentro del detalle de cada Event de Daily
  Operations (`/ops/events/{event_id}`), justo debajo de los datos del
  evento, aparece la sección "Real-time connection" (`app/web/realtime.py`,
  plantilla `ops/partials/realtime_section.html`). Se auto-refresca sola
  cada 5 segundos vía HTMX (`hx-trigger="every 5s"`), sin recargar la
  página. Roles `ADMIN` / `OFFICE_ENGINEER` / `RIG_SUPERVISOR`.
  - Si el evento no tiene canal activo: muestra un selector con los
    taladros activos (excluyendo los que ya están ocupados transmitiendo a
    otro evento) y un botón "Activar".
  - Si tiene un canal activo: muestra el estado (`connecting` /
    `connected` / `error` / `disconnected`), la última vez que llegó un
    dato, cuántas filas se han insertado, el último error si lo hay, y un
    botón "Desactivar".
  - La app rechaza activar un canal si el evento ya tiene uno activo, o si
    el taladro elegido ya está transmitiendo a otro evento — nunca
    desconecta silenciosamente un pozo distinto.

---

## 3. Flujo de uso, paso a paso

1. **Una sola vez por taladro**: ir a `/master-data/rigs`, crear el Rig con
   su nombre, modo de conexión, host y puerto (los datos obtenidos en la
   sección 1). Repetir para los 3 taladros.
2. **Al iniciar la perforación de un pozo con uno de esos taladros**: crear
   el pozo/Event como se hace normalmente hoy (sin ningún paso adicional).
3. **Entrar al detalle del Event**, bajar a la sección "Real-time
   connection", elegir el `Rig` correspondiente en el selector, y presionar
   "Activar". La app queda en estado `connecting` y el `RealtimeIngestManager`
   arranca la tarea de conexión inmediatamente (sin reiniciar el servidor).
4. **Los datos empiezan a llegar solos** — cada trama WITS0 válida y
   mapeada se inserta en `well_data_time`, visible desde las mismas
   pantallas de sensores/gráficos que ya usa la app para datos importados.
5. **Cuando el taladro termina ese pozo o se mueve a otro**: entrar al
   mismo Event y presionar "Desactivar". El historial de esa conexión queda
   guardado (no se borra), y el `Rig` queda libre para activarse en otro
   Event.
6. **Si la app se reinicia** (deploy, reinicio del servidor), al arrancar
   vuelve a levantar automáticamente todas las conexiones que hayan quedado
   con `enabled=true` — no hace falta reactivarlas a mano.

---

## 4. Verificación del mapeo antes de confiar en los datos

Después de llenar `WITS_ITEM_MAP` con los códigos reales del `.ini` de un
taladro (sección 2.3), antes de dar por buena la instalación en producción:

1. Activar el canal para un Event de prueba (o el pozo real, apenas
   arranca) y observar la sección "Real-time connection" — debe pasar de
   `connecting` a `connected` en cuanto el taladro conecte.
2. Confirmar que `rows_ingested` empieza a subir y `last_data_at` se va
   actualizando.
3. Ir a las pantallas de visualización de sensores del pozo (Crossplots /
   comparación / dashboard) y comparar visualmente 2-3 valores en tiempo
   real contra lo que muestra la propia pantalla del SZJ-II en el taladro,
   en el mismo instante — confirma que el mapeo de unidades (`scale`/
   `offset`) es correcto, no solo que "algo" está llegando.
4. Si `status` queda en `error`, el campo `last_error` en la UI trae el
   mensaje de la excepción real (fallo de conexión, host/puerto
   incorrectos, etc.) — es el primer lugar a revisar.

---

## 5. Resumen de archivos nuevos

| Archivo | Rol |
|---|---|
| `app/models/realtime.py` | Modelos `Rig` y `RealtimeSource` |
| `supabase/migrations/20260816000000_baseline_ddv.sql` | Esquema base, incluye `ops_rigs` y `ops_realtime_sources` |
| `app/repositories/realtime_repository.py` | Acceso a datos de `Rig`/`RealtimeSource` |
| `app/services/realtime/wits0.py` | Parser del protocolo WITS0 |
| `app/services/realtime/wits0_map.py` | Mapeo (record,item) → columna — **completar con el .ini real** |
| `app/services/realtime/ingest_manager.py` | Gestor de conexiones en background |
| `app/web/rigs.py` | CRUD del catálogo de taladros |
| `app/web/realtime.py` | Activar/desactivar canal por Event |
| `app/templates/ops/pages/rigs.html`, `ops/partials/rigs_table.html` | UI del catálogo |
| `app/templates/ops/partials/realtime_section.html` | UI de activación/estado por Event |
| `tests/test_wits0.py` | 11 tests unitarios del parser y el mapeo |

## 6. Lo único pendiente para ir a producción

**Obtener el `WITS_Predefined_xx.ini` (o tabla record/item equivalente) de
cada uno de los 3 taladros y completar `WITS_ITEM_MAP`** — es el único paso
que falta y depende exclusivamente de la coordinación con JPIM descrita en
la sección 1. Todo lo demás (modelos, migración, parser, manager, UI) ya
está implementado, probado (54/54 tests unitarios pasando, más una prueba
end-to-end manual contra un socket y una base de datos reales) y verificado
en el servidor de desarrollo sin errores de arranque.
