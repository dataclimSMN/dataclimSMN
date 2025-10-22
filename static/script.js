// Inicialización del mapa
const map = L.map("map").setView([19.4978, -96.9379], 7); // Veracruz centrado

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

// Referencias a elementos del DOM
const estadoSelect = document.getElementById("estadoSelect");
const municipioSelect = document.getElementById("municipioSelect");
const estacionSelect = document.getElementById("estacionSelect");
const statusSelect = document.getElementById("statusSelect");
const dataSelect = document.getElementById("dataSelect");
const btnBuscar = document.getElementById("btnBuscar");
const btnDescargar = document.getElementById("btnDescargar");
const estacionInfo = document.getElementById("estacionInfo");

// Estadísticas
const totalEstaciones = document.getElementById("totalEstaciones");
const estacionesOperativas = document.getElementById("estacionesOperativas");
const estacionesInoperativas = document.getElementById("estacionesInoperativas");
const municipiosCubiertos = document.getElementById("municipiosCubiertos");

// Marcadores activos
let markers = [];
// Capas GeoJSON activas
let layerEstados;
let layerMunicipios;

// ---------------- API ----------------
async function obtenerEstados() {
  const res = await fetch("/api/estados");
  if (!res.ok) throw new Error("Error al obtener estados");
  return await res.json();
}

async function obtenerEstaciones(estado) {
  const url = estado && estado !== "TODOS"
    ? `/api/estaciones?estado=${encodeURIComponent(estado)}`
    : "/api/estaciones";
  const res = await fetch(url);
  if (!res.ok) throw new Error("Error al obtener estaciones");
  return await res.json();
}

// ---------------- Evento: cambio de estado ----------------
estadoSelect.addEventListener("change", async function () {
  const estado = estadoSelect.value;

  // 🔹 Reiniciar selects dependientes
  municipioSelect.innerHTML = '<option value="">Seleccionar municipio</option>';
  estacionSelect.innerHTML = '<option value="">Seleccionar estación</option>';
  dataSelect.value = "";
  dataSelect.disabled = true;

  // 🔹 Deshabilitar combos según el estado
  municipioSelect.disabled = !estado;
  estacionSelect.disabled = true;

  // Si no se seleccionó ningún estado, salir
  if (!estado) return;

  try {
    const datos = await obtenerEstaciones(estado);
    const estaciones = datos.estaciones;

    // Obtener municipios únicos del estado seleccionado
    const municipios = [...new Set(estaciones.map((e) => e.municipio))].sort();

    // Agregar opción por defecto y opción "TODOS"
    municipioSelect.innerHTML = '<option value="">Seleccionar municipio</option>';
    municipioSelect.innerHTML += '<option value="TODOS">TODOS</option>';

    municipios.forEach((mun) => {
      if (mun && mun.trim() !== "") {
        const opt = document.createElement("option");
        opt.value = mun.toLowerCase();
        opt.textContent = mun;
        municipioSelect.appendChild(opt);
      }
    });
  } catch (err) {
    console.error("❌ Error al cargar municipios:", err);
    alert("Hubo un error al obtener municipios del estado seleccionado.");
  }
});


// ---------------- Evento: cambio de municipio ----------------
municipioSelect.addEventListener("change", async function () {
  const estado = estadoSelect.value;
  const municipio = municipioSelect.value;

  // 🔹 Reiniciar selects dependientes
  estacionSelect.innerHTML = '<option value="">Seleccionar estación</option>';
  dataSelect.value = "";
  dataSelect.disabled = true;

  // Si no hay municipio seleccionado, deshabilitar y salir
  if (!municipio) {
    estacionSelect.disabled = true;
    return;
  }

  try {
    const datos = await obtenerEstaciones(estado);
    let estaciones = datos.estaciones;

    // Filtrar por municipio si no es "TODOS"
    if (municipio !== "TODOS") {
      estaciones = estaciones.filter(
        (e) => e.municipio.toLowerCase() === municipio
      );
    }

    // 🔹 Cargar estaciones disponibles
    estacionSelect.innerHTML = '<option value="">Seleccionar estación</option>';
    estacionSelect.innerHTML += '<option value="TODAS">TODAS</option>';

    estaciones.forEach((est) => {
      if (est && est.clave) {
        const opt = document.createElement("option");
        opt.value = est.clave;
        opt.textContent = `${est.clave} - ${est.nombre}`;
        estacionSelect.appendChild(opt);
      }
    });

    // Habilitar el select de estaciones
    estacionSelect.disabled = false;
  } catch (err) {
    console.error("❌ Error al cargar estaciones:", err);
    alert("Hubo un error al obtener las estaciones del municipio seleccionado.");
  }
});

// ---------------- Evento: cambio de estación ----------------
estacionSelect.addEventListener("change", function () {
  // Solo habilitar tipo de dato si hay estación seleccionada
  const tieneEstacion = estacionSelect.value && estacionSelect.value !== "";
  dataSelect.disabled = !tieneEstacion;
});


// ---------------- Buscar estaciones ----------------
btnBuscar.addEventListener("click", async function () {
  const estado = estadoSelect.value || "";
  const municipio = municipioSelect.value || "";
  const estacionId = estacionSelect.value || "";
  const dataType = dataSelect.value || "";
  const status = statusSelect.value || "";

  // 🔍 Validaciones previas
  if (!estado || estado === "") {
    alert("Por favor selecciona un estado.");
    return;
  }

  if (!municipio || municipio === "") {
    alert("Selecciona un municipio o 'TODOS' antes de continuar.");
    return;
  }

  if (!estacionId || estacionId === "") {
    alert("Selecciona una estación o la opción 'TODAS' antes de continuar.");
    return;
  }

  // ⚠️ Nueva validación: el usuario debe elegir un tipo de dato
  if (!dataType || dataType === "") {
    alert("Selecciona un tipo de dato antes de continuar.");
    return;
  }

  try {
    const datos = await obtenerEstaciones(estado);
    let estaciones = datos.estaciones;

    // Filtrar por municipio
    if (municipio && municipio !== "TODOS") {
      estaciones = estaciones.filter(
        (e) => e.municipio.toLowerCase() === municipio
      );
    }

    // Filtrar por estación
    if (estacionId && estacionId !== "TODAS") {
      estaciones = estaciones.filter((e) => e.clave === estacionId);
    }

    // Filtrar por situación
    if (status && status !== "TODAS") {
      estaciones = estaciones.filter((e) => e.situacion === status);
    }

    // 🚫 Si no hay resultados
    if (estaciones.length === 0) {
      alert("No se encontraron estaciones para los filtros seleccionados.");
      estacionInfo.innerHTML =
        "<p class='text-center text-muted'>No se encontraron estaciones</p>";
      markers.forEach((m) => map.removeLayer(m));
      markers = [];
      return;
    }

    // ✅ Mostrar resultados
    mostrarEnMapa(estaciones);
    actualizarEstadisticas(estaciones);
    actualizarInfoEstacion(estaciones[0]);

    // ⚙️ Nuevo: pintar polígonos según selección
    console.log("[BUSCAR] Pintando polígonos:", { estado, municipio });
    await cargarGeoJSON(estado, municipio);

  } catch (err) {
    console.error(err);
    alert("Hubo un error al obtener estaciones.");
  }
});

// ---------------- Mostrar estaciones en el mapa ----------------
function mostrarEnMapa(estaciones) {
  markers.forEach((m) => map.removeLayer(m));
  markers = [];

  if (estaciones.length === 0) return;

  const coords = [];

  estaciones.forEach((estacion) => {
    const icon = L.icon({
      iconUrl:
        estacion.situacion === "OPERANDO"
          ? "https://maps.google.com/mapfiles/ms/icons/green-dot.png"
          : "https://maps.google.com/mapfiles/ms/icons/red-dot.png",
      iconSize: [32, 32],
      iconAnchor: [16, 32],
      popupAnchor: [0, -32],
    });

    const marker = L.marker([estacion.lat, estacion.lon], { icon }).addTo(map);
    marker.bindPopup(`
        <b>${estacion.nombre}</b><br>
        Clave: ${estacion.clave}<br>
        Municipio: ${estacion.municipio}<br>
        Situación: ${estacion.situacion}<br>
    `);

    marker.on("click", () => {
      actualizarInfoEstacion(estacion);
    });

    markers.push(marker);
    coords.push([estacion.lat, estacion.lon]);
  });

  if (coords.length > 0) {
    map.fitBounds(coords);
  }
}

/// ---------------- Actualizar información y estadísticas ----------------
function actualizarInfoEstacion(estacion) {
  // 🧩 Detectar qué tipos de datos tiene disponibles
  const tiposDisponibles = [];
  if (estacion.diarios) tiposDisponibles.push(" Diarios");
  if (estacion.mensuales) tiposDisponibles.push(" Mensuales");
  if (estacion.normales_1961_1990) tiposDisponibles.push(" Normales 1961-1990");
  if (estacion.normales_1971_2000) tiposDisponibles.push(" Normales 1971-2000");
  if (estacion.normales_1981_2010) tiposDisponibles.push(" Normales 1981-2010");
  if (estacion.normales_1991_2020) tiposDisponibles.push(" Normales 1991-2020");
  if (estacion.extremos) tiposDisponibles.push(" Extremos");

  // 🧩 Convertir a lista visual
  const listaTipos = tiposDisponibles.length > 0
    ? `<ul>${tiposDisponibles.map(t => `<li>${t}</li>`).join("")}</ul>`
    : "<p class='text-muted'>No tiene datos disponibles.</p>";

  estacionInfo.innerHTML = `
      <h6>${estacion.nombre}</h6>
      <p><strong>Clave:</strong> ${estacion.clave}</p>
      <p><strong>Estado:</strong> ${estacion.estado}</p>
      <p><strong>Municipio:</strong> ${estacion.municipio}</p>
      <p><strong>Situación:</strong> 
        <span class="badge ${estacion.situacion === "OPERANDO" ? "bg-success" : "bg-danger"}">
          ${estacion.situacion}
        </span>
      </p>
      <p><strong>Organismo de cuenca:</strong> ${estacion.organismo || "-"}</p>
      <p><strong>Cuenca:</strong> ${estacion.cuenca || "-"}</p>
      <p><strong>Latitud:</strong> ${estacion.lat}°</p>
      <p><strong>Longitud:</strong> ${estacion.lon}°</p>
      <p><strong>Altitud:</strong> ${estacion.alt} msnm</p>
      <p><strong>Fecha histórica:</strong> ${estacion.inicio}</p>
      <p><strong>Fecha más reciente:</strong> ${estacion.mas_reciente}</p>
      <hr>
      <p><strong>Tipos de datos disponibles:</strong></p>
      ${listaTipos}
  `;
}

function actualizarEstadisticas(estaciones) {
  totalEstaciones.textContent = estaciones.length;
  estacionesOperativas.textContent = estaciones.filter(
    (e) => e.situacion === "OPERANDO"
  ).length;
  estacionesInoperativas.textContent = estaciones.filter(
    (e) => e.situacion !== "OPERANDO"
  ).length;
  municipiosCubiertos.textContent = new Set(estaciones.map((e) => e.municipio))
    .size;

  btnDescargar.disabled = estaciones.length === 0;
}

// ... aquí tus funciones del mapa y del GeoJSON ...

// ---------------- Descargar CSV/ZIP ----------------

btnDescargar.addEventListener("click", async function () {

  
  const estado = estadoSelect.value || "ESTADOS_TODOS";
  const municipio = municipioSelect.value || "MUNICIPIOS_TODOS";
  const estacionId = estacionSelect.value || "ESTACIONES_TODAS";
  const dataType = dataSelect.value || "TODOS";
  const status = statusSelect.value || "";

  let url = `/api/descargar_csv?data=${encodeURIComponent(dataType)}`;

  if (estado && estado !== "TODOS" && estado !== "ESTADOS_TODOS") {
    url += `&estado=${encodeURIComponent(estado)}`;
  }
  if (municipio && municipio !== "TODOS" && municipio !== "MUNICIPIOS_TODOS") {
    url += `&municipio=${encodeURIComponent(municipio)}`;
  }
  if (estacionId && estacionId !== "TODAS" && estacionId !== "ESTACIONES_TODAS") {
    url += `&clave=${encodeURIComponent(estacionId)}`;
  }
  if (status && status !== "TODAS") {
    url += `&situacion=${encodeURIComponent(status)}`;
  }

  console.log("📥 URL generada:", url);

  try {
    btnDescargar.disabled = true;
    btnDescargar.innerHTML = '<i class="bi bi-download"></i> Descargando...';

    const response = await fetch(url);

    // 🧠 NUEVO: manejar caso 404 del backend (sin datos disponibles)
    if (response.status === 404) {
      const msg = await response.json();
      alert(msg.error || "No se encontraron estaciones con datos del tipo seleccionado.");
      return;
    }

    if (!response.ok) throw new Error("Error al descargar archivo");

    const blob = await response.blob();

    // Nombre dinámico del archivo
    let filename = "estaciones.csv";
    const disposition = response.headers.get("Content-Disposition");
    if (disposition && disposition.includes("filename=")) {
      filename = disposition.split("filename=")[1].replace(/"/g, "");
    } else if (response.headers.get("Content-Type").includes("application/zip")) {
      filename = "estaciones.zip";
    }

    // Descargar archivo
    const urlBlob = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = urlBlob;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(urlBlob);

    // Toast de éxito
    const toastExito = new bootstrap.Toast(document.getElementById('toastDescarga'), { delay: 3000 });
    toastExito.show();

  } catch (err) {
    console.error(err);
    const toastError = new bootstrap.Toast(document.getElementById('toastError'), { delay: 5000 });
    toastError.show();
  } finally {
    btnDescargar.disabled = false;
    btnDescargar.innerHTML = '<i class="bi bi-download"></i> Descargar';
  }
});

// ---------------- Inicializar toasts al cargar la página ----------------
document.addEventListener("DOMContentLoaded", function() {
  cargarEstados();
  const toastElements = document.querySelectorAll('.toast');
  toastElements.forEach(toastElement => new bootstrap.Toast(toastElement));
});


// ---------------- Inicializar ----------------
document.addEventListener("DOMContentLoaded", function() {
  cargarEstados();
  const toastElements = document.querySelectorAll('.toast');
  toastElements.forEach(t => new bootstrap.Toast(t));
});

async function cargarEstados() {
  try {
    const datos = await obtenerEstados();
    datos.estados.forEach((estado) => {
      const opt = document.createElement("option");
      opt.value = estado;
      opt.textContent = estado;
      estadoSelect.appendChild(opt);
    });
  } catch (err) {
    console.error(err);
    alert("Error al cargar estados.");
  }
}

// ---------------- Cargar capas dinámicas GeoJSON ----------------
async function cargarGeoJSON(estado, municipio) {
  const e = estado || "TODOS";
  const m = municipio ?? ""; // null-safe

  // Limpiar capas anteriores
  if (layerEstados) { map.removeLayer(layerEstados); layerEstados = null; }
  if (layerMunicipios) { map.removeLayer(layerMunicipios); layerMunicipios = null; }

  try {
    // -------- ESTADO --------
    let urlE = "/api/estados_geojson";
    if (e && e !== "TODOS") urlE += `?estado=${encodeURIComponent(e)}`;
    console.log("[GeoJSON] Fetch estado:", urlE);

    const resE = await fetch(urlE);
    if (!resE.ok) throw new Error(`Estados ${resE.status}`);
    const dataE = await resE.json();

    if (dataE.features && dataE.features.length > 0) {
      layerEstados = L.geoJSON(dataE, {
        style: { color: "blue", weight: 5, fillOpacity: 0.07 },
        onEachFeature: (f, l) => {
          const nombre = f.properties?.NOMGEO || "(sin nombre)";
          l.bindPopup(`<b>${nombre}</b> `);
        },
      }).addTo(map);
    }

    // -------- MUNICIPIOS --------
    // ⚠️ Solo si el usuario seleccionó un municipio o TODOS
    if (m && m.trim() !== "" && m.toUpperCase() !== "NINGUNO") {
      if (m.toUpperCase() === "TODOS") {
        // Caso 1: todos los municipios del estado
        let urlM = `/api/municipios_geojson?estado=${encodeURIComponent(e)}`;
        console.log("[GeoJSON] Fetch todos los municipios:", urlM);

        const resM = await fetch(urlM);
        if (!resM.ok) throw new Error(`Municipios ${resM.status}`);
        const dataM = await resM.json();

        if (dataM.features && dataM.features.length > 0) {
          layerMunicipios = L.geoJSON(dataM, {
            style: { color: "yellow", weight: 2, fillOpacity: 0.08 },
            onEachFeature: (f, l) => {
              const nombre = f.properties?.NOMGEO || "(sin nombre)";
              l.bindPopup(`<b>${nombre}</b> `);
            },
          }).addTo(map);
        }
      } else {
        // Caso 2: municipio específico
        let urlM = `/api/municipios_geojson?estado=${encodeURIComponent(e)}&municipio=${encodeURIComponent(m)}`;
        console.log("[GeoJSON] Fetch municipio específico:", urlM);

        const resM = await fetch(urlM);
        if (!resM.ok) throw new Error(`Municipio ${resM.status}`);
        const dataM = await resM.json();

        if (dataM.features && dataM.features.length > 0) {
          layerMunicipios = L.geoJSON(dataM, {
            style: { color: "yellow", weight: 4, fillOpacity: 0.2 },
            onEachFeature: (f, l) => {
              const nombre = f.properties?.NOMGEO || "(sin nombre)";
              l.bindPopup(`<b>${nombre}</b> `);
            },
          }).addTo(map);
        }
      }
    } else {
      console.log("[GeoJSON] Municipio vacío, no se pintan municipios.");
    }

    // -------- Ajustar vista --------
    if (layerMunicipios) {
      map.fitBounds(layerMunicipios.getBounds());
    } else if (layerEstados) {
      map.fitBounds(layerEstados.getBounds());
    }

  } catch (err) {
    console.warn("[GeoJSON] Error al cargar capas:", err);
  }
}

document.addEventListener("DOMContentLoaded", function () {
  console.log("✅ Script cargado correctamente");

  const form = document.getElementById("sugerenciaForm");
  const resultado = document.getElementById("resultadoSugerencia");

  console.log("🔍 Formulario encontrado:", form);
  console.log("🔍 Elemento resultado encontrado:", resultado);

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      console.log("🎯 Formulario enviado - evento capturado");

      const nombre = document.getElementById("nombreSugerencia").value.trim();
      const mensaje = document.getElementById("mensajeSugerencia").value.trim();

      console.log("📝 Datos capturados:", { nombre, mensaje });

      if (!nombre || !mensaje) {
        console.log("⚠️ Campos incompletos");
        resultado.innerHTML = `<p class="text-danger">Por favor completa todos los campos.</p>`;
        return;
      }

      resultado.innerHTML = `<p class="text-info">Enviando sugerencia...</p>`;
      console.log("🔄 Iniciando fetch...");

      try {
        const baseURL = window.location.origin;
        const res = await fetch(`${baseURL}/api/enviar_sugerencia`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nombre, mensaje }),
        });

        console.log("📨 Respuesta recibida - Status:", res.status);
        
        const data = await res.json();
        console.log("📊 Datos de respuesta:", data);

        if (res.ok) {
          resultado.innerHTML = `<p class="text-success">✅ ¡Gracias por tu sugerencia! Se ha enviado correctamente.</p>`;
          form.reset();
        } else {
          resultado.innerHTML = `<p class="text-danger">❌ Error: ${data.detail || "No se pudo enviar el mensaje."}</p>`;
        }
      } catch (err) {
        console.error("💥 Error en fetch:", err);
        resultado.innerHTML = `<p class="text-danger">❌ Ocurrió un error al enviar la sugerencia: ${err.message}</p>`;
      }
    });
  } else {
    console.warn("⚠️ No se encontró el formulario de sugerencias en el DOM.");
  }
});