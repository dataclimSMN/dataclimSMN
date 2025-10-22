from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import xml.etree.ElementTree as ET
import requests
import csv
import io
import zipfile
import re
import geopandas as gpd
from shapely.geometry import mapping
import numpy as np
import pandas as pd
import json
from fastapi import Request
from datetime import datetime
from pathlib import Path

app = FastAPI(title="API de Estaciones Climatológicas - ITSM")


# -------- CONFIGURAR STATIC --------
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def serve_home():
    return FileResponse("static/index.html")


KML_FILE = "data/doc.kml"

# ---------------------- PARSE KML ----------------------
def parse_kml():
    estaciones = []
    tree = ET.parse(KML_FILE)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    placemarks = root.findall(".//kml:Placemark", ns)
    for placemark in placemarks:
        ext_data = placemark.find(".//kml:ExtendedData/kml:SchemaData", ns)
        if ext_data is None:
            continue

        datos = {}
        for data in ext_data.findall("kml:SimpleData", ns):
            datos[data.attrib["name"]] = data.text

        if datos.get("ESTADO"):
            estaciones.append({
                "clave": datos.get("CLAVE"),
                "nombre": datos.get("NOMBRE"),
                "estado": datos.get("ESTADO"),
                "municipio": datos.get("MUNICIPIO"),
                "organismo": datos.get("ORG_CUENCA"),
                "cuenca": datos.get("CUENCA"),
                "tipo_est": datos.get("TIPO_EST"),
                "inicio": datos.get("INICIO"),
                "mas_reciente": datos.get("MAS_RECIENTE"),
                "lat": datos.get("LATITUD"),
                "lon": datos.get("LONGITUD"),
                "alt": datos.get("ALTITUD"),
                "diarios": datos.get("DIARIOS"),
                "mensuales": datos.get("MENSUALES"),
                "normales_1961_1990": datos.get("NORMALES_1961_1990"),
                "normales_1971_2000": datos.get("NORMALES_1971_2000"),
                "normales_1981_2010": datos.get("NORMALES_1981_2010"),
                "normales_1991_2020": datos.get("NORMALES_1991_2020"),
                "extremos": datos.get("EXTREMOS"),
                "situacion": datos.get("SITUACION")
            })
    return estaciones

ESTACIONES = parse_kml()

@app.get("/api/estados")
def get_estados():
    estados = set()
    for e in ESTACIONES:
        if e["estado"]:
            estados.add(e["estado"].strip().upper())
    return {"estados": sorted(estados)}

@app.get("/api/estaciones")
def get_estaciones(
    estado: str = Query(None),
    municipio: str = Query(None),
    clave: str = Query(None)
):
    filtradas = ESTACIONES
    if estado:
        filtradas = [e for e in filtradas if e["estado"] and e["estado"].lower() == estado.lower()]
    if municipio:
        filtradas = [e for e in filtradas if e["municipio"] and e["municipio"].lower() == municipio.lower()]
    if clave:
        filtradas = [e for e in filtradas if e["clave"] == clave]

    return {"total": len(filtradas), "estaciones": filtradas}

# ---------------------- PARSER PARA MENSUALES ----------------------
def extract_metadata(lines):
    meta_order = [
        ("ESTADÍSTICA MENSUAL", ""),
        ("EMISIÓN", ""),
        ("ESTACIÓN", ""),
        ("NOMBRE", ""),
        ("ESTADO", ""),
        ("MUNICIPIO", ""),
        ("SITUACIÓN", ""),
        ("CVE-OMM", ""),
        ("LATITUD", ""),
        ("LONGITUD", ""),
        ("ALTITUD", ""),
    ]
    header_zone = lines[:120]

    def find_value(key):
        for ln in header_zone:
            s = ln.strip()
            if s.startswith(key):
                return s.split(":", 1)[-1].strip()
        return ""

    out = []
    for key, default in meta_order:
        if key == "ESTADÍSTICA MENSUAL":
            out.append([key, ""])
        else:
            out.append([key, find_value(key) or default])
    return out

def header_spans(header_line):
    h = header_line.expandtabs(8).rstrip("\n")
    matches = list(re.finditer(r"\S+", h))
    labels = [m.group(0) for m in matches]
    starts = [m.start() for m in matches]
    return labels, starts

def slice_by_spans(line, starts, ncols):
    s = line.expandtabs(8).rstrip("\n")
    if len(s) < (starts[-1] + 1):
        s = s + " " * ((starts[-1] + 1) - len(s))
    cols = []
    for i in range(ncols):
        start = starts[i]
        end = starts[i + 1] if i + 1 < ncols else None
        piece = s[start:end].strip()
        cols.append(piece)
    return cols

def parse_mensual_txt(lines):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # --- Metadatos ---
    for k, v in extract_metadata(lines):
        writer.writerow([k, v])
    writer.writerow([])

    # --- Tablas ---
    i = 0
    n = len(lines)

    def prev_nonempty(idx):
        j = idx - 1
        while j >= 0:
            if lines[j].strip():
                return lines[j].strip()
            j -= 1
        return ""

    while i < n:
        line = lines[i].strip()
        if line.startswith("AÑO"):
            title = prev_nonempty(i)
            skip_titles = {
                "COMISIÓN NACIONAL DEL AGUA",
                "COORDINACIÓN GENERAL DEL SERVICIO METEOROLÓGICO NACIONAL",
                "BASE DE DATOS CLIMATOLÓGICA NACIONAL",
                "ESTADÍSTICA MENSUAL",
            }
            if title not in skip_titles and ":" not in title:
                writer.writerow([title, ""])

            header = lines[i].rstrip("\n")
            labels, starts = header_spans(header)
            writer.writerow(labels)
            i += 1

            while i < n:
                cur = lines[i]
                cur_strip = cur.strip()
                if not cur_strip or cur_strip.startswith("AÑO"):
                    break
                data_cols = slice_by_spans(cur, starts, len(starts))
                writer.writerow(data_cols)
                i += 1

            writer.writerow([])
            continue
        i += 1

    return buffer.getvalue()

# ---------------------- PARSER PARA NORMALES ----------------------
DELIM = re.compile(r"\t+|\s{2,}")  # separador: tabs o 2+ espacios

def parse_normales_txt(lines, periodo="1961-1990"):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # --- Metadatos ---
    header_zone = lines[:60]

    def find_value(key):
        for ln in header_zone:
            s = ln.strip()
            if s.upper().startswith(key):
                return s.split(":", 1)[-1].strip()
        return ""

    writer.writerow([f"NORMAL CLIMATOLÓGICA {periodo}", ""])
    for key in ["EMISIÓN", "ESTACIÓN", "NOMBRE", "ESTADO", "MUNICIPIO",
                "SITUACIÓN", "CVE-OMM", "LATITUD", "LONGITUD", "ALTITUD"]:
        writer.writerow([key, find_value(key)])
    writer.writerow([])

    # --- Tablas ---
    n = len(lines)
    i = 0

    def prev_nonempty(idx):
        j = idx - 1
        while j >= 0:
            if lines[j].strip():
                return lines[j].strip()
            j -= 1
        return ""

    while i < n:
        line = lines[i].strip()
        if line.startswith("MESES"):
            title = prev_nonempty(i)
            if title and ":" not in title and not title.startswith("NORMAL CLIMATOLÓGICA"):
                writer.writerow([title, ""])

            headers = DELIM.split(line.strip())
            headers = ["VARIABLE"] + headers[1:]
            writer.writerow(headers)
            i += 1

            while i < n:
                cur = lines[i].strip()
                if not cur or cur.startswith("MESES"):
                    break
                parts = DELIM.split(cur)
                if parts:
                    writer.writerow(parts)
                i += 1

            writer.writerow([])
            continue
        i += 1

    return buffer.getvalue()

# ---------------------- PARSER PARA EXTREMOS ----------------------
def parse_extremos_txt_fixed(lines):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # --- Metadatos ---
    header_zone = lines[:60]

    def find_value(key):
        for ln in header_zone:
            s = ln.strip()
            if s.upper().startswith(key):
                return s.split(":", 1)[-1].strip()
        return ""

    writer.writerow(["VALORES EXTREMOS", ""])
    for key in ["EMISIÓN", "ESTACIÓN", "NOMBRE", "ESTADO", "MUNICIPIO",
                "SITUACIÓN", "CVE-OMM", "LATITUD", "LONGITUD", "ALTITUD"]:
        writer.writerow([key, find_value(key)])
    writer.writerow([])

    # --- Tablas ---
    n = len(lines)
    i = 0

    expected_headers = [
        "MES", "Año Inicio", "Año Final", "Núm Años",
        "Valor Máx.", "Fecha Máx.", "Se ha Rep.",
        "Valor Mín.", "Fecha Mín.", "Se ha Rep.",
        "Valor Medio", "Desv Estándar"
    ]

    while i < n:
        line = lines[i].strip()
        # Detectar inicio de sección
        if line.upper().startswith(("TEMPERATURA MÁXIMA", "TEMPERATURA MÍNIMA", "PRECIPITACIÓN", "EVAPORACIÓN")):
            writer.writerow([line, ""])
            i += 1
            continue

        # Detectar encabezado de tabla (línea que empieza con MES)
        if line.startswith("MES"):
            # saltamos 2 filas de encabezado en el TXT y ponemos las esperadas
            writer.writerow(expected_headers)
            i += 2
            # Escribir filas hasta línea en blanco o nueva sección
            while i < n and lines[i].strip() and not lines[i].upper().startswith(("TEMPERATURA", "PRECIPITACIÓN", "EVAPORACIÓN")):
                parts = re.split(r"\s{2,}|\t+", lines[i].strip())
                writer.writerow(parts)
                i += 1
            writer.writerow([])
            continue

        i += 1

    return buffer.getvalue() 

# ---------------------- PARSER PARA DIARIOS ----------------------
def parse_diarios_txt(lines, est):
    """
    Convierte un TXT diario del SMN en CSV estructurado.
    Extrae metadatos (emisión, coordenadas, etc.) y detecta encabezados FECHA y unidades.
    """
    emision = ""
    for l in lines[:60]:
        # Buscar línea tipo "EMISIÓN : 19/09/2025"
        m = re.search(r'EMISI[ÓO]N\s*:?\s*(\d{2}/\d{2}/\d{4})', l, flags=re.IGNORECASE)
        if m:
            emision = m.group(1)
            break

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer, delimiter=",")

    # ---- Metadatos ----
    writer.writerow(["REGISTRO DIARIO HISTÓRICO", ""])
    writer.writerow(["EMISIÓN", emision])
    writer.writerow(["ESTACIÓN", est.get("clave", "") or ""])
    writer.writerow(["NOMBRE", (est.get("nombre", "") or "").strip()])
    writer.writerow(["ESTADO", est.get("estado", "") or ""])
    writer.writerow(["MUNICIPIO", est.get("municipio", "") or ""])
    writer.writerow(["SITUACIÓN", est.get("situacion", "") or ""])
    writer.writerow(["CVE-OMM", ""])
    writer.writerow(["LATITUD", f"{est.get('lat','') or ''} °".strip()])
    writer.writerow(["LONGITUD", f"{est.get('lon','') or ''} °".strip()])
    writer.writerow(["ALTITUD", f"{est.get('alt','') or ''} msnm".strip()])
    writer.writerow([])
    # ---- Fin metadatos ----

    # ---- Procesar datos tabulares ----
    i = 0
    wrote_header = False
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        # Detectar encabezado "FECHA ..."
        if not wrote_header and re.match(r'^\s*FECHA\b', line, flags=re.IGNORECASE):
            header_cols = re.findall(r'\S+', lines[i])

            # Detectar unidades en la siguiente línea (si existen)
            units = []
            if i + 1 < len(lines):
                units = re.findall(r'\(([^)]*)\)', lines[i + 1])

            header_final = []
            for idx, col in enumerate(header_cols):
                if idx == 0 and col.upper().startswith("FECHA"):
                    header_final.append(col)
                else:
                    unit_idx = idx - 1
                    unit = units[unit_idx].strip() if unit_idx < len(units) else ""
                    header_final.append(col if not unit else f"{col} ({unit})")

            writer.writerow(header_final)
            wrote_header = True
            i += 2 if units else 1
            continue

        # Escribir filas con datos
        if wrote_header and line != "":
            writer.writerow(re.findall(r'\S+', lines[i]))

        i += 1

    return csv_buffer.getvalue()


# ----------------------- GeoJSON -----------------------
BASE_DIR = Path(__file__).resolve().parent

gdf_estados = gpd.read_file(BASE_DIR / "data" / "Estados" / "Estados.shp")
gdf_municipios = gpd.read_file(BASE_DIR / "data" / "Municipios" / "Municipios.shp")
# ---------------------- GEOJSON ESTADOS ----------------------
@app.get("/api/estados_geojson")
def get_estados_geojson(estado: str = Query("TODOS")):
    print(f"[DEBUG] /api/estados_geojson → estado recibido: {estado}")

    if estado and estado.upper() != "TODOS":
        subset = gdf_estados[gdf_estados["NOMGEO"].str.upper().str.contains(estado.upper())]
        print(f"[DEBUG] Estados filtrados: {len(subset)}")
    else:
        subset = gdf_estados
        print(f"[DEBUG] Todos los estados: {len(subset)}")

    # 🔁 Reproyectar a EPSG:4326
    subset = subset.to_crs(epsg=4326)

    return JSONResponse(content=json.loads(subset.to_json()))



# ---------------------- GEOJSON MUNICIPIOS ----------------------
@app.get("/api/municipios_geojson")
def get_municipios_geojson(
    estado: str = Query("TODOS"),
    municipio: str = Query("TODOS")
):
    print(f"[DEBUG] /api/municipios_geojson → estado: {estado}, municipio: {municipio}")

    subset = gdf_municipios

    if estado and estado.upper() != "TODOS":
        match = gdf_estados[gdf_estados["NOMGEO"].str.upper().str.contains(estado.upper())]
        if not match.empty:
            cve_ent = match.iloc[0]["CVE_ENT"]
            subset = subset[subset["CVE_ENT"] == cve_ent]
            print(f"[DEBUG] Filtrado por estado {estado} → código {cve_ent}, municipios: {len(subset)}")
        else:
            print(f"[DEBUG] Estado {estado} no encontrado en shapefile")
            subset = subset.iloc[0:0]

    if municipio and municipio.upper() != "TODOS":
        subset = subset[subset["NOMGEO"].str.upper().str.contains(municipio.upper())]
        print(f"[DEBUG] Municipios después de filtrar municipio: {len(subset)}")

    # 🔁 Reproyectar a EPSG:4326
    subset = subset.to_crs(epsg=4326)

    print(f"[DEBUG] Municipios devueltos OK: {len(subset)}")
    return JSONResponse(content=json.loads(subset.to_json()))


# ----------------------- DEBUG EXTRA -----------------------
@app.get("/api/debug_estados")
def debug_estados():
    estados = sorted(gdf_estados["NOMGEO"].unique().tolist())
    print(f"[DEBUG] Total estados en shapefile: {len(estados)}")
    return {"total": len(estados), "estados": estados}

@app.get("/api/debug_municipios_all")
def debug_municipios_all():
    municipios = sorted(gdf_municipios["NOMGEO"].unique().tolist())
    print(f"[DEBUG] Total municipios en shapefile: {len(municipios)}")
    return {"total": len(municipios), "ejemplo": municipios[:50]}

@app.get("/api/debug_municipios_por_estado")
def debug_municipios_por_estado():
    counts = gdf_municipios.groupby("CVE_ENT")["NOMGEO"].count().to_dict()
    return counts
@app.get("/api/debug_total_municipios")
def debug_total_municipios():
    return {"total": int(gdf_municipios.shape[0])}

# ---------------------- DESCARGA CSV/ZIP ----------------------
@app.get("/api/descargar_csv")
def descargar_csv(
    estado: str = Query(None),
    municipio: str = Query(None),
    clave: str = Query(None),
    data: str = Query("DIARIOS"),
    situacion: str = Query(None)
):
    estaciones = ESTACIONES
    if estado and estado != "TODOS":
        estaciones = [e for e in estaciones if e["estado"] and e["estado"].lower() == estado.lower()]
    if municipio and municipio != "TODOS":
        estaciones = [e for e in estaciones if e["municipio"] and e["municipio"].lower() == municipio.lower()]
    if clave and clave != "TODAS":
        estaciones = [e for e in estaciones if e["clave"] == clave]
    if situacion and situacion.upper() != "TODAS":
        estaciones = [e for e in estaciones if e["situacion"] and e["situacion"].upper() == situacion.upper()]

    if not estaciones:
        return JSONResponse(content={"error": "No se encontraron estaciones"}, status_code=404)

    tipos = ["diarios", "mensuales", "normales_1961_1990",
             "normales_1971_2000", "normales_1981_2010", "normales_1991_2020",
             "extremos"]
    data_keys = tipos if data.upper() == "TODOS" else [data.lower()]

    archivos = []
    estaciones_validas = []  # para guardar solo las que tengan datos del tipo solicitado

    for est in estaciones:
        tiene_dato = False  # bandera para ver si la estación tiene al menos un tipo válido

        for tipo in data_keys:
            url = est.get(tipo)
            if not url or url.strip() == "":
                # No tiene este tipo de dato → saltar
                continue

            # Intentar obtener el archivo remoto
            try:
                resp = requests.get(url, timeout=30)
            except Exception as ex:
                print(f"[WARN] Error al acceder a URL {url}: {ex}")
                continue

            if resp.status_code != 200 or not resp.text.strip():
                print(f"[WARN] Archivo no disponible para {est.get('clave')} tipo {tipo}")
                continue

            lines = resp.text.splitlines()
            if len(lines) < 5:
                print(f"[WARN] Archivo vacío o incorrecto en {url}")
                continue

            # Si llegamos aquí, la estación sí tiene datos de ese tipo
            tiene_dato = True

            # Parsear según tipo
            if tipo == "mensuales":
                csv_content = parse_mensual_txt(lines)
            elif tipo.startswith("normales"):
                periodo = tipo.split("_")[-1]
                csv_content = parse_normales_txt(lines, periodo)
            elif tipo == "extremos":
                csv_content = parse_extremos_txt_fixed(lines)
            elif tipo == "diarios":
                csv_content = parse_diarios_txt(lines, est)
            else:
                # fallback: guardar texto crudo como CSV simple
                csv_content = "\n".join(lines)

            archivos.append((
                f"{(est.get('municipio') or 'MUNICIPIO').replace(' ', '_')}_{est.get('clave')}_{tipo}.csv",
                csv_content
            ))

        if tiene_dato:
            estaciones_validas.append(est)

    # Si ninguna estación tuvo datos válidos
    if not estaciones_validas or not archivos:
        return JSONResponse(
            content={"error": "No se encontro el tipo de dato solicitado."},
            status_code=404
        )




    zip_name_parts = []
    zip_name_parts.append((estado or "ESTADOS_TODOS").replace(" ", "_").upper())
    zip_name_parts.append((municipio or "MUNICIPIOS_TODOS").replace(" ", "_").upper())
    zip_name_parts.append((clave or "ESTACIONES_TODAS").replace(" ", "_").upper())
    zip_name_parts.append(data.upper())
    base_filename = "_".join(zip_name_parts)

    if len(archivos) == 1:
        filename, content = archivos[0]
        csv_filename = base_filename + ".csv"
        return StreamingResponse(
            iter([content.encode("utf-8-sig")]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={csv_filename}"}
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in archivos:
            zf.writestr(filename, content.encode("utf-8-sig"))

    zip_buffer.seek(0)
    zip_filename = base_filename + ".zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )