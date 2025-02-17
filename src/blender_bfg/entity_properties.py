import bpy
from bpy.props import (
    StringProperty,
    PointerProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    BoolProperty,
)
from bpy.types import Panel, PropertyGroup, Operator
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass
class Choice:
    value: str
    description: str


@dataclass
class Attribute:
    name: str
    type: str
    description: str
    default: Optional[str]
    choices: Optional[List[Choice]] = None


@dataclass
class EntityClass:
    class_type: str
    base: Optional[str]
    color: Optional[str]
    size: Optional[str]
    model: Optional[Dict[str, Any]]
    classname: str
    description: str
    attributes: List[Attribute]


class FGDParser:
    def __init__(self, content: str):
        self.content = content
        self.position = 0
        self.length = len(content)
        self.last_attribute = None  # Track last parsed attribute for choices

    def parse(self) -> List[EntityClass]:
        entities = []
        while self.position < self.length:
            self.consume_whitespace()
            if self.position >= self.length:
                break

            # Skip comments
            if self.content[self.position :].startswith("//"):
                self.skip_line()
                continue

            if self.content[self.position] == "@":
                entity = self.parse_entity()
                if entity:
                    entities.append(entity)
            else:
                self.position += 1

        return entities

    def skip_line(self):
        while self.position < self.length and self.content[self.position] != "\n":
            self.position += 1
        self.position += 1

    def consume_whitespace(self):
        while self.position < self.length and self.content[self.position].isspace():
            self.position += 1

    def parse_entity(self) -> Optional[EntityClass]:
        # Skip @
        self.position += 1

        # Parse class type (PointClass, BaseClass, etc)
        class_type = self.parse_identifier().lower()

        # Parse parameters
        color = None
        size = None
        base = None
        model = None

        self.consume_whitespace()
        while self.position < self.length and self.content[self.position] != "=":
            if self.content[self.position :].startswith("color"):
                self.position += 5  # Skip "color"
                color = self.parse_parentheses()
            elif self.content[self.position :].startswith("size"):
                self.position += 4  # Skip "size"
                size = self.parse_parentheses()
            elif self.content[self.position :].startswith("base"):
                self.position += 4  # Skip "base"
                base = self.parse_parentheses()
            elif self.content[self.position :].startswith("model"):
                self.position += 5  # Skip "model"
                model_str = self.parse_model_parameter()
                try:
                    # Handle JSON-like model parameter
                    model = json.loads(model_str.replace("'", '"'))
                except json.JSONDecodeError:
                    model = {"path": model_str}
                except Exception as e:
                    print(f"Warning: Failed to parse model parameter: {e}")
                    model = {"path": model_str}
            else:
                # Skip until we find a space or equals sign
                while (
                    self.position < self.length
                    and not self.content[self.position].isspace()
                    and self.content[self.position] != "="
                ):
                    self.position += 1
                self.consume_whitespace()

        # Skip =
        self.position += 1
        self.consume_whitespace()

        # Parse classname
        classname = self.parse_identifier()

        # Parse description
        self.consume_whitespace()
        if self.content[self.position] == ":":
            self.position += 1
            self.consume_whitespace()
            description = self.parse_string()
        else:
            description = ""

        # Parse attributes
        attributes = []
        self.consume_whitespace()
        if self.position < self.length and self.content[self.position] == "[":
            self.position += 1  # Skip [
            while self.position < self.length:
                self.consume_whitespace()

                # Check for end of attributes
                if self.position >= self.length or self.content[self.position] == "]":
                    break

                # Skip empty lines and comments
                if self.content[self.position] == "\n":
                    self.position += 1
                    continue
                if self.content[self.position :].startswith("//"):
                    self.skip_line()
                    continue

                attribute = self.parse_attribute()
                if attribute:
                    attributes.append(attribute)
                else:
                    # If attribute parsing fails, skip to next line to avoid infinite loop
                    self.skip_to_next_line()

            if self.position < self.length and self.content[self.position] == "]":
                self.position += 1  # Skip ]

        return EntityClass(
            class_type=class_type,
            base=base,
            color=color,
            size=size,
            model=model,
            classname=classname,
            description=description,
            attributes=attributes,
        )

    def parse_attribute(self) -> Optional[Attribute]:
        # Get the start position for debugging
        start_pos = self.position

        # Skip empty lines
        self.consume_whitespace()
        if self.position >= self.length:
            return None

        # Skip if we're looking at a number (probably part of a choices block)
        if self.content[self.position].isdigit():
            self.skip_to_next_line()
            return None

        name = self.parse_identifier()
        if not name:  # Skip empty lines
            return None

        self.consume_whitespace()

        # Check for choices block
        if name == "choices":
            if self.content[self.position] == "=":
                choices = self.parse_choices()
                # Store choices in the last parsed attribute
                if self.last_attribute is not None:
                    self.last_attribute.choices = choices
                return None

        # Parse type in parentheses
        attr_type = self.parse_parentheses()
        if not attr_type:
            # Only print warning if this isn't part of a choices block
            if not name[0].isdigit():
                print(
                    f"Warning: Failed to parse type for attribute near: {self.content[start_pos : start_pos + 50]}..."
                )
            return None

        self.consume_whitespace()
        description = ""
        default = None

        # Parse description and default value
        if self.position < self.length and self.content[self.position] == ":":
            self.position += 1
            self.consume_whitespace()
            description = self.parse_string()

            self.consume_whitespace()
            if self.position < self.length and self.content[self.position] == ":":
                self.position += 1
                self.consume_whitespace()
                if self.content[self.position] == '"':
                    default = self.parse_string()
                elif (
                    self.content[self.position].isdigit()
                    or self.content[self.position] == "-"
                ):
                    default = self.parse_number()

        attr = Attribute(
            name=name,
            type=attr_type,
            description=description,
            default=default,
            choices=None,
        )
        self.last_attribute = attr  # Store reference to last parsed attribute
        return attr

    def parse_number(self) -> str:
        start = self.position
        while self.position < self.length and (
            self.content[self.position].isdigit() or self.content[self.position] in ".-"
        ):
            self.position += 1
        return self.content[start : self.position]

    def parse_identifier(self) -> str:
        """Parse an identifier which may include dots (e.g., 'damage_zone.head')"""
        self.consume_whitespace()
        start = self.position

        # Allow alphanumeric, underscore, and dot in identifiers
        while self.position < self.length and (
            self.content[self.position].isalnum()
            or self.content[self.position] in ["_", "."]
        ):
            self.position += 1

        return self.content[start : self.position]

    def parse_parentheses(self) -> Optional[str]:
        self.consume_whitespace()
        if self.position >= self.length or self.content[self.position] != "(":
            return None

        self.position += 1  # Skip (
        start = self.position

        # Find closing parenthesis, but don't get stuck
        max_iterations = 1000  # Safety limit
        iterations = 0
        parentheses_count = 1

        while (
            self.position < self.length
            and parentheses_count > 0
            and iterations < max_iterations
        ):
            char = self.content[self.position]
            if char == "(":
                parentheses_count += 1
            elif char == ")":
                parentheses_count -= 1
            self.position += 1
            iterations += 1

        if parentheses_count > 0 or iterations >= max_iterations:
            print(
                f"Warning: Possible parsing error near: {self.content[start : start + 50]}..."
            )
            return None

        return self.content[start : self.position - 1].strip()

    def parse_string(self) -> str:
        self.consume_whitespace()
        if self.position >= self.length or self.content[self.position] != '"':
            return ""

        self.position += 1  # Skip opening quote
        start = self.position

        # Add safety limit here too
        max_iterations = 1000
        iterations = 0

        while (
            self.position < self.length
            and self.content[self.position] != '"'
            and iterations < max_iterations
        ):
            self.position += 1
            iterations += 1

        if iterations >= max_iterations:
            print(
                f"Warning: Possible parsing error in string near: {self.content[start : start + 50]}..."
            )
            return ""

        result = self.content[start : self.position].strip()
        self.position += 1  # Skip closing quote
        return result

    def parse_model_parameter(self) -> str:
        """Parse a model parameter which may be a simple path or JSON-like object"""
        self.consume_whitespace()
        if self.position >= self.length:
            return ""

        if self.content[self.position] != "(":
            return ""

        self.position += 1  # Skip (
        start = self.position

        # Handle nested braces for JSON-like syntax
        brace_count = 0
        paren_count = 1

        while self.position < self.length:
            char = self.content[self.position]

            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
            elif char == "(" and brace_count == 0:
                paren_count += 1
            elif char == ")" and brace_count == 0:
                paren_count -= 1
                if paren_count == 0:
                    break

            self.position += 1

        result = self.content[start : self.position].strip()
        self.position += 1  # Skip closing parenthesis
        return result

    def skip_to_next_line(self):
        """Skip to the start of the next line"""
        while self.position < self.length and self.content[self.position] != "\n":
            self.position += 1
        self.position += 1  # Skip the newline

    def parse_choices(self) -> List[Choice]:
        """Parse a choices block into a list of Choice objects"""
        choices = []

        # Skip the equals sign and find opening bracket
        self.position += 1
        self.consume_whitespace()

        if self.content[self.position] != "[":
            return choices

        self.position += 1  # Skip [

        while self.position < self.length:
            self.consume_whitespace()

            # Check for end of choices
            if self.content[self.position] == "]":
                self.position += 1
                break

            # Skip comments
            if self.content[self.position :].startswith("//"):
                self.skip_line()
                continue

            # Parse choice value (number)
            value = ""
            while self.position < self.length and (
                self.content[self.position].isdigit()
                or self.content[self.position] == "-"
            ):
                value += self.content[self.position]
                self.position += 1

            if not value:  # Skip if no value found
                self.skip_to_next_line()
                continue

            self.consume_whitespace()

            # Skip colon
            if self.content[self.position] == ":":
                self.position += 1
                self.consume_whitespace()

                # Parse description
                if self.content[self.position] == '"':
                    description = self.parse_string()
                    choices.append(Choice(value=value.strip(), description=description))
                else:
                    self.skip_to_next_line()
            else:
                self.skip_to_next_line()

        return choices


def parse_fgd_file(filename: str) -> List[dict]:
    with open(filename, "r") as f:
        content = f.read()

    parser = FGDParser(content)
    entities = parser.parse()

    # Convert to dictionary format
    return [asdict(entity) for entity in entities]


# Global variable to store parsed entities
ENTITY_CLASSES = []


def update_entity_type(self, context):
    update_entity_properties(self, context)


def update_entity_properties(self, context):
    obj = context.active_object
    if not obj:
        return

    # Clear existing entity-related custom properties
    for prop in list(obj.keys()):
        if prop != "entity_props":
            del obj[prop]

    # If no entity type is selected, we're done
    if self.entity_classname == "none":
        return

    # Set the classname
    obj["classname"] = self.entity_classname

    # Find the entity class definition
    entity_class = next(
        (e for e in ENTITY_CLASSES if e["classname"] == self.entity_classname), None
    )
    if not entity_class:
        return

    # Update custom properties for each attribute
    for attr in entity_class["attributes"]:
        if attr["name"].startswith("_"):
            continue

        prop_name = f"prop_{attr['name']}"
        if hasattr(self, prop_name):
            value = getattr(self, prop_name)
            if value is not None and value != "":
                obj[f"{attr['name']}"] = value


class EntityPropertyGroup(PropertyGroup):
    entity_classname: EnumProperty(
        name="Entity Type",
        description="Select the entity type",
        items=[("none", "None", "No entity type selected")],
        default="none",
        update=update_entity_type,
    )

    last_fgd_path: StringProperty(
        name="Last FGD Path", description="Path to the last loaded FGD file", default=""
    )

    # Dynamic properties will be added here


class OBJECT_PT_entity_properties(Panel):
    bl_label = "Entity Properties"
    bl_idname = "OBJECT_PT_entity_properties"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        # Add Load FGD button at the top of the panel
        row = layout.row()
        last_fgd = context.scene.entity_props.last_fgd_path
        if last_fgd and ENTITY_CLASSES:  # Only show filename if we have entities loaded
            button_text = f"FGD: {os.path.basename(last_fgd)}"
        else:
            button_text = "Load FGD File"
        row.operator("object.load_fgd", text=button_text, icon="IMPORT")

        if not obj:
            layout.label(text="No object selected")
            return

        props = obj.entity_props

        # Draw entity type selector
        layout.prop(props, "entity_classname")

        # Draw dynamic properties if an entity is selected
        if props.entity_classname != "none":
            entity_class = next(
                (e for e in ENTITY_CLASSES if e["classname"] == props.entity_classname),
                None,
            )
            if entity_class:
                # Add description before the box
                if entity_class["description"]:
                    layout.label(text=entity_class["description"])

                box = layout.box()
                box.label(text=f"Properties for {entity_class['classname']}")

                for attr in entity_class["attributes"]:
                    # Skip internal properties
                    if attr["name"].startswith("_"):
                        continue

                    prop_name = f"prop_{attr['name']}"
                    if hasattr(props, prop_name):
                        box.prop(
                            props, prop_name, text=attr["name"] or attr["description"]
                        )


class OBJECT_PT_entity_toolbar(Panel):
    bl_label = "BlenderBFG"
    bl_idname = "OBJECT_PT_entity_toolbar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderBFG"

    def draw(self, context):
        layout = self.layout

        # Add Load FGD button at the top
        row = layout.row()
        last_fgd = context.scene.entity_props.last_fgd_path
        if last_fgd and ENTITY_CLASSES:
            button_text = f"FGD: {os.path.basename(last_fgd)}"
        else:
            button_text = "Load FGD File"
        row.operator("object.load_fgd", text=button_text, icon="IMPORT")

        # Add Bootstrap Level button (disabled if no FGD loaded)
        row = layout.row()
        row.operator("object.bootstrap_level", icon="SCENE_DATA")
        row.enabled = bool(ENTITY_CLASSES)  # Disable if no entities are loaded
        if not ENTITY_CLASSES:
            row.operator("object.load_fgd", text="Load FGD to enable", icon="ERROR")


class OBJECT_OT_load_fgd(Operator):
    bl_idname = "object.load_fgd"
    bl_label = "Load FGD File"
    bl_description = "Load an FGD file to populate entity properties"

    filepath: StringProperty(
        subtype="FILE_PATH",
    )

    def execute(self, context):
        global ENTITY_CLASSES
        try:
            ENTITY_CLASSES = parse_fgd_file(self.filepath)
            if not ENTITY_CLASSES:  # If no entities were loaded
                self.report({"ERROR"}, "No entities found in FGD file")
                context.scene.entity_props.last_fgd_path = ""  # Clear the path
                return {"CANCELLED"}

            # Store the filepath only if we successfully loaded entities
            context.scene.entity_props.last_fgd_path = self.filepath
            self.update_entity_enum()
            self.create_dynamic_properties()
            return {"FINISHED"}
        except FileNotFoundError:
            self.report({"ERROR"}, f"FGD file not found: {self.filepath}")
            context.scene.entity_props.last_fgd_path = ""  # Clear the path on error
            return {"CANCELLED"}
        except PermissionError:
            self.report({"ERROR"}, f"Permission denied accessing FGD file: {self.filepath}")
            context.scene.entity_props.last_fgd_path = ""
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Failed to load FGD file: {str(e)}")
            context.scene.entity_props.last_fgd_path = ""  # Clear the path on error
            return {"CANCELLED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def update_entity_enum(self):
        # Update the enum property with loaded entities
        items = [("none", "None", "No entity type selected")]
        items.extend(
            [
                (
                    entity["classname"],
                    entity["classname"],
                    entity["description"] or entity["classname"],
                )
                for entity in ENTITY_CLASSES
            ]
        )

        EntityPropertyGroup.entity_classname = EnumProperty(
            name="Entity Type",
            description="Select the entity type",
            items=items,
            default="none",
            update=update_entity_type,
        )

    def create_dynamic_properties(self):
        # Remove existing dynamic properties
        for key in list(EntityPropertyGroup.__annotations__.keys()):
            if key.startswith("prop_"):
                delattr(EntityPropertyGroup, key)

        # Create new properties for each attribute in all entities
        for entity in ENTITY_CLASSES:
            for attr in entity["attributes"]:
                if attr["name"].startswith("_"):
                    continue

                prop_name = f"prop_{attr['name']}"
                if prop_name not in EntityPropertyGroup.__annotations__:
                    prop = self.create_property_from_attribute(attr)
                    setattr(EntityPropertyGroup, prop_name, prop)

    def create_property_from_attribute(self, attr):
        attr_type = attr["type"].lower()

        if attr["choices"]:
            # Create enum property for choices
            items = [
                (c["value"], c["value"], c["description"]) for c in attr["choices"]
            ]
            return EnumProperty(
                name=attr["name"],
                description=attr["description"] or "",
                items=items,
                default=attr["default"] if attr["default"] else items[0][0],
            )

        if "integer" in attr_type:
            return IntProperty(
                name=attr["name"],
                description=attr["description"] or "",
                default=int(attr["default"]) if attr["default"] else 0,
                update=update_entity_properties,
            )

        if "float" in attr_type or "decimal" in attr_type:
            return FloatProperty(
                name=attr["name"],
                description=attr["description"] or "",
                default=float(attr["default"]) if attr["default"] else 0.0,
                update=update_entity_properties,
            )

        if "boolean" in attr_type:
            return BoolProperty(
                name=attr["name"],
                description=attr["description"] or "",
                default=bool(attr["default"]) if attr["default"] else False,
                update=update_entity_properties,
            )

        # Default to string property
        return StringProperty(
            name=attr["name"],
            description=attr["description"] or "",
            default=attr["default"] if attr["default"] else "",
            update=update_entity_properties,
        )


class OBJECT_OT_bootstrap_level(Operator):
    bl_idname = "object.bootstrap_level"
    bl_label = "Bootstrap Level"
    bl_description = "Set up a basic level with worldspawn, light, and player start"
    bl_options = {"REGISTER", "UNDO"}

    # Heavily inspired by D-Meat's Blender mapping standards
    # https://modwiki.dhewm3.org/RBDoom3BFG-Blender-Mapping
    def execute(self, context):
        # Delete all objects and collections
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

        for collection in bpy.data.collections:
            bpy.data.collections.remove(collection)

        # Create main collections with colors
        collections = {
            "Lights": (1.0, 1.0, 0.0, 1.0),  # Yellow
            "Movers": (0.0, 0.5, 1.0, 1.0),  # Blue
            "Point Entities": None,  # Parent collection, no color
            "Static Geometry": None,
            "Worldspawn": None,
        }

        # Create subcollections for Point Entities
        point_entity_subs = {
            "Weapons": (1.0, 0.5, 0.0, 1.0),  # Orange
            "Items": (1.0, 0.5, 0.0, 1.0),  # Orange
            "Monsters": (0.7, 0.0, 1.0, 1.0),  # Purple
            "Player Spawns": (0.0, 1.0, 0.0, 1.0),  # Green
        }

        # Create main collections
        for name, color in collections.items():
            coll = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(coll)
            if color:
                coll.color_tag = self.closest_color_tag(color)

        # Create Point Entities subcollections
        point_entities_coll = bpy.data.collections["Point Entities"]
        for name, color in point_entity_subs.items():
            sub_coll = bpy.data.collections.new(name)
            point_entities_coll.children.link(sub_coll)
            if color:
                sub_coll.color_tag = self.closest_color_tag(color)

        # Set scene units to None
        context.scene.unit_settings.system = "NONE"

        # Setup grid
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.clip_start = 1
                        space.clip_end = 25000
                        # Set grid settings
                        space.overlay.grid_scale = 1  # 1 unit grid
                        space.overlay.grid_subdivisions = 10  # 10 subdivisions
                        space.overlay.grid_lines = 100  # Show 100x100 grid lines
                        # Ensure grid is visible
                        space.overlay.show_floor = True
                        space.overlay.show_axis_x = True
                        space.overlay.show_axis_y = True
                        space.overlay.show_ortho_grid = True

        # Create worldspawn environment cube
        bpy.ops.mesh.primitive_cube_add(size=1024, location=(0, 0, 0))
        env_cube = context.active_object
        env_cube.name = "worldspawn.env"

        # Move to Worldspawn collection
        self.move_to_collection(env_cube, "Worldspawn")

        # Flip normals
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.flip_normals()
        bpy.ops.object.mode_set(mode="OBJECT")

        # Set material (assuming material exists)
        mat_name = "textures/skies/sunset_in_the_chalk_quarry"
        if mat_name not in bpy.data.materials:
            mat = bpy.data.materials.new(name=mat_name)
        else:
            mat = bpy.data.materials[mat_name]
        env_cube.data.materials.append(mat)

        # Create floor plane
        bpy.ops.mesh.primitive_plane_add(size=1000, location=(0, 0, 0))
        floor = context.active_object
        floor.name = "BSP.brush"

        # Move to Worldspawn collection
        self.move_to_collection(floor, "Worldspawn")

        # Set material
        mat_name = "textures/base_wall/snpanel2rust"
        if mat_name not in bpy.data.materials:
            mat = bpy.data.materials.new(name=mat_name)
        else:
            mat = bpy.data.materials[mat_name]
        floor.data.materials.append(mat)

        # Create worldspawn empty
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
        worldspawn = context.active_object
        worldspawn.name = "worldspawn"

        # Move to Worldspawn collection
        self.move_to_collection(worldspawn, "Worldspawn")

        # Set entity type to worldspawn
        if any(e["classname"] == "worldspawn" for e in ENTITY_CLASSES):
            worldspawn.entity_props.entity_classname = "worldspawn"
            update_entity_properties(worldspawn.entity_props, context)

        # Create light
        bpy.ops.object.light_add(type="POINT", location=(0, 0, 50))
        light = context.active_object
        light.name = "light"

        # Move to Lights collection
        self.move_to_collection(light, "Lights")

        # Set entity type to light
        if any(e["classname"] == "light" for e in ENTITY_CLASSES):
            light.entity_props.entity_classname = "light"
            update_entity_properties(light.entity_props, context)

        # Create player start
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 32))
        start = context.active_object
        start.name = "info_player_start"
        start.scale = (16, 16, 32)  # Scale to get 32x32x64 size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # Move to Player Spawns collection
        self.move_to_collection(start, "Point Entities/Player Spawns")

        # Add transparent green material
        mat = bpy.data.materials.new(name="info_player_start_material")
        mat.use_nodes = True
        mat.blend_method = "BLEND"  # Enable transparency
        nodes = mat.node_tree.nodes
        nodes.clear()

        # Create nodes for transparent green material
        node_principled = nodes.new("ShaderNodeBsdfPrincipled")
        node_principled.inputs["Base Color"].default_value = (0, 1, 0, 0.3)
        node_principled.inputs["Alpha"].default_value = 0.3

        node_output = nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(
            node_principled.outputs["BSDF"], node_output.inputs["Surface"]
        )

        # Assign material to player start
        start.data.materials.clear()
        start.data.materials.append(mat)

        # Set entity type to info_player_start
        if any(e["classname"] == "info_player_start" for e in ENTITY_CLASSES):
            start.entity_props.entity_classname = "info_player_start"
            update_entity_properties(start.entity_props, context)

        return {"FINISHED"}

    def move_to_collection(self, obj, collection_path):
        """Move an object to a specific collection, removing it from all others"""
        # Remove from all current collections
        for coll in obj.users_collection:
            coll.objects.unlink(obj)

        # Add to new collection
        collection_names = collection_path.split("/")
        target_collection = bpy.data.collections[collection_names[0]]

        # Navigate through nested collections if path contains multiple levels
        for name in collection_names[1:]:
            target_collection = target_collection.children[name]

        target_collection.objects.link(obj)

    def closest_color_tag(self, color):
        """Convert RGB color to closest available collection color tag"""
        # Blender's available color tags (COLOR_01 = red, COLOR_02 = orange, etc)
        color_tags = {
            "NONE": (0.0, 0.0, 0.0),
            "COLOR_01": (1.0, 0.0, 0.0),  # Red
            "COLOR_02": (1.0, 0.5, 0.0),  # Orange
            "COLOR_03": (1.0, 1.0, 0.0),  # Yellow
            "COLOR_04": (0.0, 1.0, 0.0),  # Green
            "COLOR_05": (0.0, 0.0, 1.0),  # Blue
            "COLOR_06": (0.7, 0.0, 1.0),  # Violet
            "COLOR_07": (1.0, 0.5, 1.0),  # Pink
            "COLOR_08": (0.5, 0.5, 0.5),  # Gray
        }

        # Find closest color by RGB distance
        min_distance = float("inf")
        closest_tag = "NONE"

        for tag, tag_color in color_tags.items():
            distance = sum((c1 - c2) ** 2 for c1, c2 in zip(color[:3], tag_color))
            if distance < min_distance:
                min_distance = distance
                closest_tag = tag

        return closest_tag


classes = (
    EntityPropertyGroup,
    OBJECT_PT_entity_properties,
    OBJECT_PT_entity_toolbar,
    OBJECT_OT_load_fgd,
    OBJECT_OT_bootstrap_level,
)


def menu_func(self, context):
    self.layout.operator(OBJECT_OT_load_fgd.bl_idname)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register the property group for both Object and Scene
    bpy.types.Object.entity_props = PointerProperty(type=EntityPropertyGroup)
    bpy.types.Scene.entity_props = PointerProperty(type=EntityPropertyGroup)

    # Add the menu item
    bpy.types.VIEW3D_MT_object.append(menu_func)


def unregister():
    # Remove the menu item
    bpy.types.VIEW3D_MT_object.remove(menu_func)

    # Unregister the property groups
    del bpy.types.Object.entity_props
    del bpy.types.Scene.entity_props

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
