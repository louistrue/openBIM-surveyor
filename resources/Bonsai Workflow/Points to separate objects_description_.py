import bpy
import csv
import os

# Sökväg till din CSV-fil
csv_path = r"C:\Users\Benny\OneDrive\Qgis Projekt\Olstorp_Emil\Local_crs.csv"

# Skapa (eller återanvänd) en collection för importen
collection_name = "Imported_Individual_Points"
if collection_name not in bpy.data.collections:
    new_collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(new_collection)
else:
    new_collection = bpy.data.collections[collection_name]

# Läs CSV och skapa objekt per punkt
with open(csv_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        try:
            x = float(row['x'])
            y = float(row['y'])
            z = float(row['z'])
            point_id = int(row['Id'])
            description = row['description']
            code = row['code']
        except (ValueError, KeyError) as e:
            print(f"Hoppar över rad pga fel: {e}")
            continue

        # Skapa mesh för en enskild punkt
        mesh = bpy.data.meshes.new(name=f"Point_{point_id}_Mesh")
        mesh.from_pydata([(x, y, z)], [], [])
        mesh.update()

        # Lägg till attribut
        mesh.attributes.new(name="Id", type='INT', domain='POINT')
        mesh.attributes.new(name="description", type='STRING', domain='POINT')
        mesh.attributes.new(name="code", type='STRING', domain='POINT')

        mesh.attributes["Id"].data[0].value = point_id
        mesh.attributes["description"].data[0].value = description.encode('utf-8')
        mesh.attributes["code"].data[0].value = code.encode('utf-8')

        # Skapa objekt och länka till collection
        obj_name = description.strip() or f"Point_{point_id}"
        obj = bpy.data.objects.new(obj_name, mesh)

        new_collection.objects.link(obj)

print("Alla punkter har importerats som separata objekt.")
