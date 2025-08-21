# Small helper script
# exports objects from the blender file into individual .glb files stored in appropriate folders
# These collections are expected to exist in the .blend file
# fantom_base - base shape
# fantom_scaled_up - scaled up shape (maximum scaling up)
# fandom_scaled_down - scaled down shape (maximum scalind down)
# fantom_weight_up - weight increased (max)
# fantom_weight_down - weight decreased (min)

import bpy

# replace this with the correct path...
filepath_base = "/home/Luka/Work/fantom/FantomWizard/CreateFantomModule/Resources/Data/2ts"

for collection in bpy.data.collections:
  for obj in collection.objects:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    objectname = obj.name.split(".")[0] # get only the first part of the name because the copies have .001 appended.

    filepath = filepath_base + "/" + collection.name + "/" + objectname + ".glb"
        
    kwargs = {
      "export_normals": False,
      "export_materials": "NONE",
      "export_vertex_color": "NONE",
      "export_animations": False,
      "export_skins": False,
      "export_morph": False,
      "export_nla_strips": False,
      "export_yup": False,
      "use_selection": True,
      "check_existing": False,
      "filepath": filepath
    }
    bpy.ops.export_scene.gltf(**kwargs)