from enum import Enum, unique

# Added to fix gdal 3.3.0 error
from osgeo import gdal

# import gempy as gp
import numpy as np

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------


def to_id_order(item):
    return (item.id, item.order)


def to_name_order(item):
    return (item.name, item.order)


def take_first(item):
    return item[0]


def take_second(item):
    return item[1]


def next_order_size(list, **kwargs):
    return len(list)


def create_id_generator(prefix):
    count = 1
    while True:
        yield f"{prefix}_{count}"
        count += 1


ID_GENERATORS = {}
for key in ["stack", "surf"]:
    ID_GENERATORS[key] = create_id_generator(key)

# -----------------------------------------------------------------------------
# Helper classes
# -----------------------------------------------------------------------------


class Grid:
    def __init__(self):
        self.extent = [0, 100, 0, 100, 0, 100]
        self.resolution = [10, 10, 10]

    @property
    def html(self):
        return {
            "extent": self.extent,
            "resolution": self.resolution,
        }


class AbstractSortedList:
    def __init__(self, prefix, klass, parent=None):
        self._parent = parent
        self._id_generator = ID_GENERATORS[prefix]
        self._klass = klass
        self._ids = []
        self._data = {}
        self._active_id = None

    def __getitem__(self, id):
        if id in self._data:
            return self._data[id]

    @property
    def selected_id(self):
        return self._active_id

    @selected_id.setter
    def selected_id(self, value):
        self._active_id = value

    # @property
    # def selected(self):
    #     if self._active_id in self._data:
    #         return self._data[self._active_id]

    # @selected.setter
    # def selected(self, value):
    #     self._active_id = None
    #     for id in self._data:
    #         if self._data[id] == value:
    #             self._active_id = id
    #             break

    @property
    def names(self):
        results = []
        for id in self._ids:
            item = self._data[id]
            results.append(item.name)
        return results

    @property
    def ids(self):
        return self._ids

    @property
    def html(self):
        results = []
        for id in self._ids:
            item = self._data[id]
            out = {"id": id}
            out.update(item.html)
            results.append(out)

        results.reverse()

        return results

    def _insert_new_id(self, id):
        self._ids.append(id)

    def add(self, name, **kwargs):
        id = next(self._id_generator)
        self._data[id] = self._klass(name, parent=self._parent, **kwargs)
        self._insert_new_id(id)
        self._active_id = id
        return id

    def remove(self, id):
        if self._data.pop(id, None):
            self._ids.remove(id)
            if self._active_id == id:
                self._active_id = None
            return True

        return False

    def up(self, id):
        l = self._ids
        index = l.index(id)
        if len(l) > index + 1:
            l[index], l[index + 1] = l[index + 1], l[index]
            return True

        return False

    def down(self, id):
        l = self._ids
        index = l.index(id)
        if index > 0:
            l[index], l[index - 1] = l[index - 1], l[index]
            return True

        return False


class Surface:
    def __init__(self, name, parent=None, **kwargs):
        self.name = name
        self.points = []
        self.orientations = []
        self.stack = parent

    @property
    def html(self):
        return {
            "name": self.name,
            "feature": self.stack.feature.value,
            "stackname": self.stack.name,
        }


class Surfaces(AbstractSortedList):
    def __init__(self, parent):
        super().__init__("surf", Surface, parent)

    @property
    def surface(self):
        return self[self.selected_id]


@unique
class Feature(Enum):
    EROSION = "Erosion"
    FAULT = "Fault"
    ONLAP = "OnLap"


class Stack:
    def __init__(self, name, feature=Feature.EROSION, **kwargs):
        self.name = name
        self.surfaces = Surfaces(self)

        if isinstance(feature, Feature):
            self.feature = feature
        else:
            self.feature = Feature(feature)

    @property
    def html(self):
        return {
            "name": self.name,
            "feature": self.feature.value,
        }


class Stacks(AbstractSortedList):
    def __init__(self):
        super().__init__("stack", Stack)
        self.add("basement", feature=Feature.EROSION)

    @property
    def stack(self):
        return self[self.selected_id]


# -----------------------------------------------------------------------------
# Main class
# -----------------------------------------------------------------------------


class SubSurfaceModeler:
    def __init__(self, app):
        self._app = app

        # state
        self._grid = Grid()
        self._stacks = Stacks()

        # gempy model
        # self._model = gp.create_model('conceptual_modeler')
        # self._model.add_surfaces('basement')
        # gp.map_stack_to_surfaces(self.geo_model, mapstacks, remove_unused_series=True)
        # self.geo_model.reorder_features(orderStacks)
        # self.geo_model.set_bottom_relation(self.stacks[i]['name'], self.stacks[i-1]['feature'])

        # Update app with our shared state
        # app.state.update(INITIAL_STATE)

        # Expend shared state in app
        app.state.update(self.state)

    @property
    def state(self):
        return {
            "features": [a.value for a in Feature],
            "grid": self._grid.html,
            "activeStackId": self._stacks.selected_id,
            "stacks": self._stacks.html,
            "surfaces": self._stacks.stack.surfaces.html if self._stacks.stack else [],
            "activeSurfaceId": self._stacks.stack.surfaces.selected_id
            if self._stacks.stack
            else None,
        }

    def dirty(self, *args):
        state = self.state
        for name in args:
            self._app.set(name, state[name], force=True)

    # -----------------------------------------------------
    # Grid
    # -----------------------------------------------------

    def update_grid(self, extent, resolution):
        self._grid.extent = extent
        self._grid.resolution = resolution
        # update gempy
        self.dirty("grid")

    # -----------------------------------------------------
    # Stack
    # -----------------------------------------------------

    @property
    def stack(self):
        return self._stacks

    def stack_add(self, **kwargs):
        id = self._stacks.add(**kwargs)
        self.dirty("activeStackId", "stacks")

    def stack_remove(self, id):
        if self._stacks.remove(id):
            self.dirty("activeStackId", "stacks")

    def stack_select(self, id):
        self._stacks.selected_id = id
        self.dirty("surfaces", "activeSurfaceId")

    def stack_move(self, direction):
        if direction == "up":
            self._stacks.up(self._stacks.selected_id)
        else:
            self._stacks.down(self._stacks.selected_id)
        self.dirty("stacks")

    # -----------------------------------------------------
    # Surface
    # -----------------------------------------------------

    def surface_add(self, **kwargs):
        stack = self._stacks.stack
        if stack:
            id = stack.surfaces.add(**kwargs)
            self.dirty("activeSurfaceId", "surfaces")

    def surface_remove(self, id):
        stack = self._stacks.stack
        if stack and stack.surfaces.remove(id):
            self.dirty("activeSurfaceId", "surfaces")

    def surface_select(self, id):
        stack = self._stacks.stack
        if stack:
            stack.surfaces.selected_id = id

    def surface_move(self, direction):
        stack = self._stacks.stack
        if stack:
            surfaces = stack.surfaces
            if direction == "up":
                surfaces.up(surfaces.selected_id)
            else:
                surfaces.down(surfaces.selected_id)
            self.dirty("surfaces")
