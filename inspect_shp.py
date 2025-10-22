import geopandas as gpd

print("=== ESTADOS ===")
gdf_estados = gpd.read_file("data/Estados/Estados.shp")
print(gdf_estados.columns)
print(gdf_estados.head())

print("\n=== MUNICIPIOS ===")
gdf_municipios = gpd.read_file("data/Municipios/Municipios.shp")
print(gdf_municipios.columns)
print(gdf_municipios.head())
