/* Librería de gráficos en D3 del sistema de diseño OIG.
   Fuente única: cada app la consume como copia sincronizada.

   Reemplaza a Recharts. Todos los colores salen de tokens.css, así que los
   gráficos siguen el tema claro/oscuro sin duplicar la paleta en ningún sitio.

   Tipos disponibles:
     line(cont, series)          series temporales, una o varias
     area(cont, rows, keys)      área apilada
     bars(cont, rows, opts)      barras verticales, agrupadas o no
     donut(cont, rows)           anillo con leyenda
     sparkline(cont, valores)    miniatura sin ejes, para las tarjetas KPI
*/

(function () {
  "use strict";

  // Lee un token CSS. Es como la guía indica leer la paleta desde JavaScript.
  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // Devuelve el color de la serie n, ciclando sobre la paleta de 8
  function seriesColor(i) {
    return token("--color-chart-" + ((i % 8) + 1));
  }

  // Formatea un número con separador de miles
  function fmt(v, decimals) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return v.toLocaleString("es-PE", {
      minimumFractionDigits: decimals === undefined ? 1 : decimals,
      maximumFractionDigits: decimals === undefined ? 1 : decimals,
    });
  }

  const MARGIN = { top: 16, right: 16, bottom: 34, left: 60 };

  // Crea el lienzo y devuelve el grupo interior ya desplazado
  function canvas(container, height, margin) {
    const m = margin || MARGIN;
    const width = container.clientWidth || 720;
    container.replaceChildren();

    const svg = d3.select(container).append("svg")
      .attr("width", width).attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "img");

    return {
      svg,
      g: svg.append("g").attr("transform", `translate(${m.left},${m.top})`),
      w: width - m.left - m.right,
      h: height - m.top - m.bottom,
      m,
    };
  }

  // Dibuja los ejes con los colores del tema
  function axes(g, x, y, w, h, yLabel, xIsTime) {
    const axisColor = token("--color-chart-axis");
    const gridColor = token("--color-border");

    // Rejilla horizontal tenue, como indica la guía
    g.append("g")
      .call(d3.axisLeft(y).tickSize(-w).tickFormat(""))
      .call(s => s.select(".domain").remove())
      .call(s => s.selectAll("line")
        .attr("stroke", gridColor).attr("stroke-dasharray", "3 3").attr("opacity", 0.3));

    const ejeX = xIsTime ? d3.axisBottom(x).ticks(6) : d3.axisBottom(x);

    g.append("g").attr("transform", `translate(0,${h})`).call(ejeX)
      .call(s => s.selectAll("text").attr("fill", axisColor).style("font-size", "11px"))
      .call(s => s.selectAll("line,path").attr("stroke", gridColor));

    g.append("g").call(d3.axisLeft(y).ticks(6))
      .call(s => s.selectAll("text").attr("fill", axisColor).style("font-size", "11px"))
      .call(s => s.selectAll("line,path").attr("stroke", gridColor));

    if (yLabel) {
      g.append("text").attr("transform", "rotate(-90)")
        .attr("y", -MARGIN.left + 14).attr("x", -h / 2)
        .attr("text-anchor", "middle").attr("fill", axisColor)
        .style("font-size", "11px").text(yLabel);
    }
  }

  // Tooltip compartido por todos los gráficos
  function tooltip() {
    let tip = document.getElementById("chart-tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "chart-tooltip";
      tip.className = "chart-tooltip";
      tip.hidden = true;
      document.body.appendChild(tip);
    }
    return tip;
  }

  // Coloca el tooltip junto al cursor, sin salirse de la ventana
  function placeTip(tip, event) {
    tip.hidden = false;
    const ancho = tip.offsetWidth || 200;
    const x = event.pageX + 14 + ancho > window.innerWidth + window.scrollX
      ? event.pageX - ancho - 14
      : event.pageX + 14;
    tip.style.left = x + "px";
    tip.style.top = (event.pageY - 10) + "px";
  }

  // Dibuja la leyenda con círculos, como indica la guía
  function legend(g, entradas) {
    const l = g.append("g").attr("transform", "translate(4,4)");
    entradas.forEach(function (e, i) {
      const fila = l.append("g").attr("transform", `translate(0,${i * 16})`);
      fila.append("circle").attr("r", 4).attr("cx", 4).attr("cy", -4).attr("fill", e.color);
      fila.append("text").attr("x", 14).attr("fill", token("--color-text-muted"))
        .style("font-size", "12px").text(e.label);
    });
  }

  /* ── Series temporales ──────────────────────────────────────────────── */
  function line(container, series, opts) {
    opts = opts || {};
    if (!series.length) return;

    const { g, w, h } = canvas(container, opts.height || 280);
    const tip = tooltip();

    const todos = series.flatMap(s => s.points);
    if (!todos.length) return;

    const x = d3.scaleTime().domain(d3.extent(todos, p => p.date)).range([0, w]);
    const y = d3.scaleLinear()
      .domain([0, d3.max(todos, p => p.value) * 1.05 || 1]).range([h, 0]).nice();

    axes(g, x, y, w, h, opts.yLabel, true);

    const gen = d3.line().x(p => x(p.date)).y(p => y(p.value)).curve(d3.curveMonotoneX);

    series.forEach(function (s, i) {
      g.append("path").datum(s.points).attr("d", gen).attr("fill", "none")
        .attr("stroke", s.color || seriesColor(i))
        .attr("stroke-width", s.dashed ? 2.5 : 2)
        .attr("stroke-dasharray", s.dashed ? "8 4" : null);
    });

    if (series.length > 1) {
      legend(g, series.map((s, i) => ({ label: s.label, color: s.color || seriesColor(i) })));
    }

    // Línea guía que sigue al cursor
    const guia = g.append("line").attr("y1", 0).attr("y2", h)
      .attr("stroke", token("--color-text-muted"))
      .attr("stroke-dasharray", "3 3").attr("opacity", 0);

    g.append("rect").attr("width", w).attr("height", h).attr("fill", "transparent")
      .on("mousemove", function (event) {
        const [mx] = d3.pointer(event);
        const fecha = x.invert(mx);
        const base = series[0].points;
        const i = d3.bisector(p => p.date).center(base, fecha);
        if (i < 0 || i >= base.length) return;

        const punto = base[i];
        guia.attr("x1", x(punto.date)).attr("x2", x(punto.date)).attr("opacity", 1);

        const filas = series.map(function (s, k) {
          const p = s.points[i];
          if (!p) return "";
          return `<div class="tip-row"><span class="tip-dot" style="background:${s.color || seriesColor(k)}"></span>` +
                 `<span class="tip-name">${s.label}</span>` +
                 `<span class="tip-value">${fmt(p.value)}</span></div>`;
        }).join("");

        tip.innerHTML = `<div class="tip-title">${punto.date.toLocaleDateString("es-PE")}</div>${filas}`;
        placeTip(tip, event);
      })
      .on("mouseleave", function () { tip.hidden = true; guia.attr("opacity", 0); });
  }

  /* ── Área apilada ───────────────────────────────────────────────────── */
  function area(container, rows, keys, opts) {
    opts = opts || {};
    if (!rows.length || !keys.length) return;

    const { g, w, h } = canvas(container, opts.height || 320);
    const tip = tooltip();

    const x = d3.scaleTime().domain(d3.extent(rows, d => d.date)).range([0, w]);
    const apilado = d3.stack().keys(keys)(rows);
    const y = d3.scaleLinear()
      .domain([0, d3.max(apilado[apilado.length - 1], d => d[1]) * 1.05 || 1])
      .range([h, 0]).nice();

    axes(g, x, y, w, h, opts.yLabel, true);

    const gen = d3.area().x(d => x(d.data.date)).y0(d => y(d[0])).y1(d => y(d[1]))
      .curve(d3.curveMonotoneX);

    g.selectAll(".layer").data(apilado).join("path").attr("class", "layer")
      .attr("d", gen).attr("fill", (d, i) => seriesColor(i))
      // La guía fija 0.6 de opacidad para el área apilada
      .attr("fill-opacity", 0.6)
      .attr("stroke", (d, i) => seriesColor(i)).attr("stroke-width", 1);

    const guia = g.append("line").attr("y1", 0).attr("y2", h)
      .attr("stroke", token("--color-text-muted"))
      .attr("stroke-dasharray", "3 3").attr("opacity", 0);

    g.append("rect").attr("width", w).attr("height", h).attr("fill", "transparent")
      .on("mousemove", function (event) {
        const [mx] = d3.pointer(event);
        const i = d3.bisector(d => d.date).center(rows, x.invert(mx));
        const punto = rows[i];
        if (!punto) return;

        guia.attr("x1", x(punto.date)).attr("x2", x(punto.date)).attr("opacity", 1);

        const filas = keys.map((k, idx) => ({ k, v: punto[k] || 0, c: seriesColor(idx) }))
          .filter(r => r.v > 0.01).sort((a, b) => b.v - a.v)
          .map(r => `<div class="tip-row"><span class="tip-dot" style="background:${r.c}"></span>` +
                    `<span class="tip-name">${r.k}</span>` +
                    `<span class="tip-value">${fmt(r.v)}</span></div>`).join("");

        tip.innerHTML = `<div class="tip-title">${punto.date.toLocaleDateString("es-PE")}</div>${filas}`;
        placeTip(tip, event);
      })
      .on("mouseleave", function () { tip.hidden = true; guia.attr("opacity", 0); });
  }

  /* ── Barras ─────────────────────────────────────────────────────────── */
  function bars(container, rows, opts) {
    opts = opts || {};
    if (!rows.length) return;

    const margen = { top: 16, right: 16, bottom: 60, left: 60 };
    const { g, w, h } = canvas(container, opts.height || 300, margen);
    const tip = tooltip();

    const x = d3.scaleBand().domain(rows.map(r => r.label)).range([0, w]).padding(0.25);
    const y = d3.scaleLinear()
      .domain([0, d3.max(rows, r => r.value) * 1.05 || 1]).range([h, 0]).nice();

    axes(g, x, y, w, h, opts.yLabel, false);

    // Con muchas categorías las etiquetas se giran para que quepan
    if (rows.length > 6) {
      g.selectAll("g").filter(function () {
        return d3.select(this).attr("transform") === `translate(0,${h})`;
      }).selectAll("text")
        .attr("transform", "rotate(-35)").attr("text-anchor", "end")
        .attr("dx", "-0.5em").attr("dy", "0.3em");
    }

    g.selectAll(".bar").data(rows).join("rect").attr("class", "bar")
      .attr("x", r => x(r.label)).attr("y", r => y(r.value))
      .attr("width", x.bandwidth()).attr("height", r => h - y(r.value))
      .attr("rx", 3)
      .attr("fill", (r, i) => r.color || seriesColor(i))
      .on("mousemove", function (event, r) {
        tip.innerHTML = `<div class="tip-title">${r.label}</div>` +
          `<div class="tip-row"><span class="tip-value">${fmt(r.value)}</span></div>`;
        placeTip(tip, event);
      })
      .on("mouseleave", function () { tip.hidden = true; });
  }

  /* ── Anillo ─────────────────────────────────────────────────────────── */
  function donut(container, rows, opts) {
    opts = opts || {};
    if (!rows.length) return;

    const alto = opts.height || 260;
    const ancho = container.clientWidth || 360;
    container.replaceChildren();

    const svg = d3.select(container).append("svg")
      .attr("width", ancho).attr("height", alto)
      .attr("viewBox", `0 0 ${ancho} ${alto}`);

    const radio = Math.min(ancho / 2, alto) / 2 - 8;
    const g = svg.append("g").attr("transform", `translate(${radio + 16},${alto / 2})`);
    const tip = tooltip();

    const total = d3.sum(rows, r => r.value) || 1;
    const arcos = d3.pie().value(r => r.value).sort(null)(rows);
    const arco = d3.arc().innerRadius(radio * 0.6).outerRadius(radio);

    g.selectAll("path").data(arcos).join("path")
      .attr("d", arco).attr("fill", (d, i) => rows[i].color || seriesColor(i))
      .attr("stroke", token("--color-surface")).attr("stroke-width", 2)
      .on("mousemove", function (event, d) {
        const pct = (d.data.value / total * 100).toFixed(1);
        tip.innerHTML = `<div class="tip-title">${d.data.label}</div>` +
          `<div class="tip-row"><span class="tip-value">${fmt(d.data.value)} (${pct} %)</span></div>`;
        placeTip(tip, event);
      })
      .on("mouseleave", function () { tip.hidden = true; });

    // Total en el centro del anillo
    g.append("text").attr("text-anchor", "middle").attr("dy", "-0.2em")
      .attr("fill", token("--color-text")).style("font-size", "20px")
      .style("font-weight", "700").text(fmt(total, 0));

    g.append("text").attr("text-anchor", "middle").attr("dy", "1.4em")
      .attr("fill", token("--color-text-muted")).style("font-size", "11px")
      .text(opts.totalLabel || "Total");

    // Leyenda a la derecha
    const l = svg.append("g").attr("transform", `translate(${radio * 2 + 40},24)`);
    rows.forEach(function (r, i) {
      const fila = l.append("g").attr("transform", `translate(0,${i * 18})`);
      fila.append("circle").attr("r", 4).attr("cx", 4).attr("fill", r.color || seriesColor(i));
      fila.append("text").attr("x", 14).attr("dy", "0.32em")
        .attr("fill", token("--color-text-muted")).style("font-size", "12px")
        .text(`${r.label} · ${(r.value / total * 100).toFixed(0)} %`);
    });
  }

  /* ── Miniatura para las tarjetas KPI ────────────────────────────────── */
  function sparkline(container, valores, opts) {
    opts = opts || {};
    if (!valores || valores.length < 2) return;

    const ancho = container.clientWidth || 120;
    const alto = opts.height || 32;
    container.replaceChildren();

    const svg = d3.select(container).append("svg")
      .attr("width", ancho).attr("height", alto)
      .attr("viewBox", `0 0 ${ancho} ${alto}`);

    const x = d3.scaleLinear().domain([0, valores.length - 1]).range([1, ancho - 1]);
    const y = d3.scaleLinear().domain(d3.extent(valores)).range([alto - 2, 2]);

    // El color indica la tendencia: sube o baja respecto del primer valor
    const sube = valores[valores.length - 1] >= valores[0];
    const color = opts.color || token(sube ? "--color-success" : "--color-danger");

    svg.append("path")
      .datum(valores)
      .attr("d", d3.line().x((v, i) => x(i)).y(v => y(v)).curve(d3.curveMonotoneX))
      .attr("fill", "none").attr("stroke", color).attr("stroke-width", 1.5);
  }

  /* ── Grafo de fuerzas ───────────────────────────────────────────────── */
  /* Reemplaza a Cytoscape. Recibe {nodes:[{id,label,group,size}],
     links:[{source,target,weight}]} y lo dispone con simulación de fuerzas. */
  function graph(container, data, opts) {
    opts = opts || {};
    if (!data.nodes || !data.nodes.length) return;

    const ancho = container.clientWidth || 800;
    const alto = opts.height || 560;
    container.replaceChildren();

    const svg = d3.select(container).append("svg")
      .attr("width", ancho).attr("height", alto)
      .attr("viewBox", `0 0 ${ancho} ${alto}`);

    svg.append("rect").attr("width", ancho).attr("height", alto)
      .attr("fill", token("--color-bg")).attr("rx", 8);

    const g = svg.append("g");
    const tip = tooltip();

    // Un color por grupo, desde la paleta de tokens
    const grupos = [...new Set(data.nodes.map(n => n.group))];
    const color = n => seriesColor(grupos.indexOf(n.group));

    // Copiamos los enlaces: la simulación los muta al resolverlos
    const links = data.links.map(l => Object.assign({}, l));
    const nodes = data.nodes.map(n => Object.assign({}, n));

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(n => n.id).distance(90).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-260))
      .force("center", d3.forceCenter(ancho / 2, alto / 2))
      .force("collide", d3.forceCollide().radius(n => (n.size || 8) + 6));

    // Precalculamos la disposición de forma síncrona antes de pintar. Así el
    // grafo aparece ya ordenado en vez de reacomodándose, y no depende de
    // requestAnimationFrame, que el navegador congela en pestañas de fondo.
    const pasos = Math.min(300, Math.ceil(Math.log(sim.alphaMin()) / Math.log(1 - sim.alphaDecay())));
    for (let i = 0; i < pasos; i++) sim.tick();
    sim.alpha(0);

    const linea = g.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", token("--color-border"))
      .attr("stroke-width", l => Math.max(1, Math.min(4, l.weight || 1)))
      .attr("stroke-opacity", 0.5);

    const nodo = g.append("g").selectAll("circle").data(nodes).join("circle")
      .attr("r", n => n.size || 8)
      .attr("fill", color)
      .attr("fill-opacity", 0.85)
      .attr("stroke", token("--color-surface"))
      .attr("stroke-width", 1.5)
      .style("cursor", "pointer")
      .on("mousemove", function (event, n) {
        d3.select(this).attr("stroke", token("--color-primary")).attr("stroke-width", 2.5);
        const vecinos = links.filter(l =>
          (l.source.id || l.source) === n.id || (l.target.id || l.target) === n.id).length;
        tip.innerHTML = `<div class="tip-title">${n.label}</div>` +
          `<div class="tip-row"><span class="tip-name">Grupo</span><span class="tip-value">${n.group}</span></div>` +
          `<div class="tip-row"><span class="tip-name">Relaciones</span><span class="tip-value">${vecinos}</span></div>`;
        placeTip(tip, event);
      })
      .on("mouseleave", function () {
        d3.select(this).attr("stroke", token("--color-surface")).attr("stroke-width", 1.5);
        tip.hidden = true;
      })
      .call(d3.drag()
        .on("start", function (event, n) {
          if (!event.active) sim.alphaTarget(0.3).restart();
          n.fx = n.x; n.fy = n.y;
        })
        .on("drag", function (event, n) { n.fx = event.x; n.fy = event.y; })
        .on("end", function (event, n) {
          if (!event.active) sim.alphaTarget(0);
          n.fx = null; n.fy = null;
        }));

    // Etiquetas solo de los nodos grandes: con muchos, el texto satura
    const etiqueta = g.append("g").selectAll("text")
      .data(nodes.filter(n => (n.size || 8) >= (opts.labelFrom || 12)))
      .join("text")
      .attr("fill", token("--color-text-muted"))
      .style("font-size", "11px").style("pointer-events", "none")
      .attr("text-anchor", "middle").attr("dy", -14)
      .text(n => n.label);

    // Coloca los elementos según las posiciones actuales de la simulación
    function colocar() {
      linea.attr("x1", l => l.source.x).attr("y1", l => l.source.y)
        .attr("x2", l => l.target.x).attr("y2", l => l.target.y);
      nodo.attr("cx", n => n.x).attr("cy", n => n.y);
      etiqueta.attr("x", n => n.x).attr("y", n => n.y);
    }

    // Pintamos la disposición ya calculada
    colocar();

    // Y seguimos actualizando mientras el usuario arrastre un nodo
    sim.on("tick", colocar);

    // Preparamos el zoom antes de encuadrar, para poder fijar la vista inicial
    const zoom = d3.zoom().scaleExtent([0.1, 6]).on("zoom", function (event) {
      g.attr("transform", event.transform);
    });

    svg.call(zoom);

    // Encuadramos: con muchos nodos la simulación los reparte más allá del
    // lienzo, así que ajustamos la vista al contenido en vez de recortarlo.
    const margen = 30;
    const minX = d3.min(nodes, n => n.x - (n.size || 8));
    const maxX = d3.max(nodes, n => n.x + (n.size || 8));
    const minY = d3.min(nodes, n => n.y - (n.size || 8));
    const maxY = d3.max(nodes, n => n.y + (n.size || 8));

    // Solo encuadramos si el contenido tiene extensión real
    if (maxX > minX && maxY > minY) {
      // Elegimos la escala que hace caber lo más ancho, sin ampliar de más
      const escala = Math.min(
        (ancho - margen * 2) / (maxX - minX),
        (alto - margen * 2) / (maxY - minY),
        2,
      );

      // Centramos el contenido en el lienzo
      const tx = (ancho - (minX + maxX) * escala) / 2;
      const ty = (alto - (minY + maxY) * escala) / 2;

      // Aplicamos la vista inicial
      svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(escala));
    }

    // Leyenda de grupos
    const l = svg.append("g").attr("transform", "translate(16,16)");
    grupos.forEach(function (gr, i) {
      const fila = l.append("g").attr("transform", `translate(0,${i * 18})`);
      fila.append("circle").attr("r", 5).attr("cx", 5).attr("fill", seriesColor(i));
      fila.append("text").attr("x", 16).attr("dy", "0.32em")
        .attr("fill", token("--color-text-muted")).style("font-size", "12px").text(gr);
    });

    // Devolvemos la simulación para poder detenerla al redibujar
    return sim;
  }

  // Exponemos la librería
  window.oigCharts = { line, area, bars, donut, sparkline, graph, token, seriesColor, fmt };
})();
