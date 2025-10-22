import geopandas as gpd

# --- Estados ---
gdf_estados = gpd.read_file("data/Estados/Estados.shp")
gdf_estados.to_file("static/estados.geojson", driver="GeoJSON")

# --- Municipios ---
gdf_municipios = gpd.read_file("data/Municipios/Municipios.shp")
gdf_municipios.to_file("static/municipios.geojson", driver="GeoJSON")

print("✅ Archivos GeoJSON creados en la carpeta static/")
