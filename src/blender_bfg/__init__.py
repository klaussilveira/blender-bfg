from . import entity_properties

bl_info = {
    "name": "BlenderBFG",
    "author": "Klaus Silveira",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderBFG",
    "description": "Add FGD entity properties to objects",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

def register():
    entity_properties.register()

def unregister():
    entity_properties.unregister()

if __name__ == "__main__":
    register()
