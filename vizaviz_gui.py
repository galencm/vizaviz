# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

import redis
import argparse
import io
import math
import uuid
from vizaviz import visualize_map
import bindings
from kivy.config import Config
Config.set('graphics', 'width',  1600)
Config.set('graphics', 'height', 800)
from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.graphics.vertex_instructions import Rectangle
from kivy.graphics import Color, Line, Ellipse, InstructionGroup
from kivy.core.text import Label as CoreLabel
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stencilview import StencilView
from kivy.properties import ListProperty, ObjectProperty
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.slider import Slider
from kivy.core.image import Image as CoreImage
from kivy.uix.scatter import Scatter
from kivy.uix.scrollview import ScrollView
from kivy.config import Config
from kivy.uix.scatter import Scatter
#import colour
import pathlib
#vzz-gui
Config.read('config.ini')
kv = """
#:import ScrollEffect  kivy.effects.scroll.ScrollEffect
<ScatterTextWidget>:
    id:image_container
    orientation: 'vertical'
    image_grid:image_grid
    scroller:scroller
    ScrollViewer:
        id:scroller
        zoom_level:0
        width:self.parent.width
        effect_cls:ScrollEffect
        GridLayout:
            id: image_grid
            rows: 1
            size_hint_y: None
            size_hint_x:None
            size:self.parent.size
            spacing: 0, 0
            padding: 0, 0
"""

Builder.load_string(kv)

class StencilBoxLayout(BoxLayout, StencilView):
    pass

class TabbedPanelContainer(TabbedPanel):
    def __init__(self, **kwargs):
        super(TabbedPanelContainer, self).__init__()

class TabItem(TabbedPanelItem):
    def __init__(self, root=None, **kwargs):
        self.root = root
        # use subcontent to handle keybinds for widgets
        # nested somewhere in the tab
        self.sub_content = []
        super(TabItem , self).__init__(**kwargs)

class LoopItem(BoxLayout):
    # expand on focus?
    def __init__(self, loop, app, **kwargs):
        self.loop = loop
        self.app = app
        self.loop_label = Label(text=loop['uuid'])
        self.loop_remove = Button(text= "del", size_hint_x=.2, font_size=20, height=44, size_hint_y=None)
        self.loop_remove.bind(on_press= lambda widget: self.remove_loop(widget))
        # some sort of race condition on update_loops?
        duration = float(self.app.sources[self.loop["filehash"]]["duration"])
        # self.loop_volume = Slider(range=(0, 100), value=v)
        # self.loop_volume.bind(on_touch_up=lambda widget, touch: self.adjust_loop("volume", round(widget.value)))
        # need different widgets for more precise selections / adjustments
        # previously had used colored ascii blocks in terminal which worked
        # well: todo vizavizcli
        #
        # canvas cells at resolution & increment with loop overlaid
        # and keyboard bindings
        # ^ trace loop focus and positions
        # ^ annotation bloom
        self.settings = {}
        # use to set as uneditable in the gui
        # should probably use a whitelist for loop_
        self.whitelist_settings = ["loop_start",
                                   "loop_end",
                                   "loop_volume",
                                   "loop_status"
                                   ]

        self.read_only_settings = ["duration",
                                   "default_increments",
                                   "default_resolutions"
                                   ]
        self.settings_container = BoxLayout(orientation="vertical")
        self.initialize_settings()
        self.update_loop_settings()
        self.add_settings()

        self.loop_image = Image()
        self.loop_image.size_hint_x = None
        super(LoopItem, self).__init__(**kwargs)
        top = BoxLayout(orientation="horizontal", size_hint_y=None)
        top.add_widget(self.loop_remove)
        top.add_widget(self.loop_image)

        self.orientation = "vertical"
        self.add_widget(top)
        self.add_widget(self.settings_container)
        self.loop_source_image()
        self.draw_viewport()

    def add_settings(self):
        for setting_name, setting_value in self.settings.items():
            setting_row = BoxLayout(orientation="horizontal", height=40)
            if "loop_" in setting_name:
                color = (0, 1, 0, 1)
            else:
                color = (1, 1, 1, 1)
            setting_row.add_widget(Label(text=str(setting_name), color=color))
            setting_value_label = Label(text=str(setting_value))
            if (setting_name not in self.read_only_settings and not setting_name.startswith("loop_")) or (setting_name.startswith("loop_") and setting_name in self.whitelist_settings):
                setting_input = TextInput(text=str(setting_value), multiline=False, height=40, size_hint_y=1)
                setting_input.bind(on_text_validate = lambda widget, 
                                                             setting_name=setting_name,
                                                             setting_value_label=setting_value_label: 
                                                             self.adjust_setting(setting_name, widget.text, setting_value_label))
            else:
                setting_input = Label(text=str(setting_value), color=(.5, .5, .5, 1))
            
            setting_row.add_widget(setting_input)

            setting_row.add_widget(setting_value_label)
            self.settings_container.add_widget(setting_row)

    def update_loop_settings(self):
        for k,v in self.loop.items():
            self.settings["loop_{}".format(k)] = v

    def initialize_settings(self):
        # defaults
        self.settings['viewgrid_rows'] = 30
        self.settings['viewgrid_columns'] = 30
        self.settings['viewgrid_opacity'] = 0.75
        self.settings['viewgrid_start_row'] = 0
        self.settings['viewgrid_start_segment'] = 0
        self.settings['viewgrid_start_column'] = 0
        self.settings['viewgrid_scroll_amount'] = 10
        self.settings['columns'] = 4
        self.settings['cell_height'] = 15
        self.settings['cell_width'] = 15
        self.settings['default_resolutions'] = [1, 4, 16, 32, 64, 128, 256, 512]
        self.settings['resolution'] = 4
        self.settings['default_increments'] = [0.001, 0.01, 0.1, 1, 10, 100,1000]
        self.settings['increment'] = 1
        # readonly
        self.settings['duration'] = float(self.app.sources[self.loop["filehash"]]["duration"])

    def loop_source_image(self):
        if self.app.sources:
            try:
                resolution = 1
                image = self.app.sources[self.loop["filehash"]]["resolutions"][resolution]["renders"]["vertical"]
                img = self.loop_image
                # pass use_once to CoreImage
                use_once = io.BytesIO(image.read())
                image.seek(0)
                # store attributes for calculating row / column
                # to create loops
                img.filename = self.app.sources[self.loop["filehash"]]["filename"]
                #img.render = render
                img.resolution = resolution

                img.allow_stretch = True
                img.texture = CoreImage(use_once, ext="jpg").texture
                img.size = img.texture_size
                # important to set to (None, None) for expected behavior
                img.size_hint = (None,None)

            except Exception as ex:
                print(ex)

    def viewgrid_scroll_up(self):
        self.settings['viewgrid_start_segment'] += self.settings['viewgrid_scroll_amount']
        self.draw_viewport()

    def viewgrid_scroll_down(self):
        self.settings['viewgrid_start_segment'] -= self.settings['viewgrid_scroll_amount']
        self.draw_viewport()

    def draw_viewport(self):
        with self.app.detailed.canvas:

            self.app.detailed.canvas.remove_group("viewport")
            self.app.detailed.canvas.remove_group("selection")
            cell_width = int(self.settings["cell_width"])
            cell_height = int(self.settings["cell_height"])
            resolution = int(self.settings["resolution"])
            increment = int(self.settings["increment"])
            viewport_cols = int(self.settings["resolution"] * self.settings["columns"])
            viewport_rows = int(self.settings['viewgrid_rows'])
            # calculate viewport
            # this is all being drawn / redrawn on canvas
            # could also use a scrollview
            # currently incorrect
            viewport_start = self.settings['viewgrid_start_segment']
            viewport_end = self.settings['viewgrid_start_segment'] + (self.settings['viewgrid_rows'] * self.settings["columns"])
            
            # y offset to start above lower containers
            y_offset = 100

            # draw point grid
            self.app.detailed.canvas.remove_group("viewgrid")
            for y in range(0, int(self.settings['viewgrid_rows'] * cell_height), cell_height):
                for x in range(0, int(self.settings['viewgrid_columns'] * cell_width), cell_width):
                    Color(1, 1, 1, self.settings['viewgrid_opacity'])
                    Ellipse(size=(2, 2), pos=(x, y + y_offset), group="viewgrid")

            z = self.app.sources[self.loop["filehash"]]["maps"]["rgb_map"]["resolutions"][resolution]["raw"]#.split(" ")
            z = list(filter(None, z.split(" ")))
            z = [int(s) for s in z]
            # loop
            start = float(self.loop['start'])
            end = float(self.loop['end'])
            duration = end - start
            duration *= resolution
            # 3 for r,g,b
            cell_length = 3
            cell = viewport_start

            z = z[viewport_start * self.settings['viewgrid_columns'] * cell_length : viewport_end * self.settings['viewgrid_columns'] * cell_length]
            for y in range(0, int(viewport_rows * cell_height), cell_height):
                for x in range(0, viewport_cols * cell_width, cell_width):
                    try:
                        r,g,b = [z.pop(0) for idx in range(3)]
                        current_frame = math.ceil(cell / resolution)
                        print(current_frame, start, end, cell)
                        r /= 255
                        g /= 255
                        b /= 255
                        w = cell_width
                        h = cell_height
                        a = 1
                        Color(r,g,b,a)
                        Rectangle(size=(w, h), pos=(x, y + y_offset), group="viewport")
                        if current_frame >= start and current_frame <= end:
                            # Color(1,1,1,1)
                            Rectangle(size=(w, h), pos=(x + (cell_width * viewport_cols) + 20, y + y_offset), group="selection")
                        cell += 1
                    except Exception as ex:
                        # print(ex)
                        pass

    def remove_loop(self, widget):
        loop_key = "vizaviz:{server}:loop:{loop_id}".format(server="foo", loop_id=self.loop['uuid'])
        redis_conn.delete(loop_key)
        self.parent.app.update_loops()

    def adjust_setting(self, attribute, value, value_display_widget=None):
        try:
            print("set {} to {}".format(attribute, value))
            self.settings[attribute] = float(value)
            if value_display_widget:
                value_display_widget.text = str(value)
            if "loop_" in attribute:
                # remove loop_ prefix
                self.adjust_loop(attribute[5:], value)
            self.draw_viewport()
        except:
            pass

    def adjust_loop(self, attribute, value):
        loop_key = "vizaviz:{server}:loop:{loop_id}".format(server="foo", loop_id=self.loop['uuid'])
        # only adjust if key exists...
        # to avoid a new key with only a single attribute
        if redis_conn.hgetall(loop_key):
            redis_conn.hmset(loop_key, { attribute : value})

class LoopContainer(BoxLayout):
    def __init__(self, **kwargs):
        self.app = app
        super(LoopContainer, self).__init__(**kwargs)

    def clear_loops(self):
        for loop in self.children:
            self.remove_widget(loop)
        self.height=0

    def has_loop_by_id(self, loop_id):
        for loop in self.children:
            try:
                if loop.loop['uuid'] == loop_id:
                    return True
                
                return False
            except Exception as ex:
                return False

    def add_loop(self, loop):
        l = LoopItem(loop.copy(), self.app)

        l.height = 800
        #l.size_hint_y = None
        self.add_widget(l)
        self.height += l.height
        self.parent.scroll_to(l)

    def remove_loop(self, loop):
        for l in self.children:
            try:
                if l == loop:
                    self.remove_widget(loop)
            except AttributeError as ex:
                pass

class ScatterTextWidget(BoxLayout):
    text_colour = ObjectProperty([1, 0, 0, 1])

    def __init__(self, **kwargs):
        super(ScatterTextWidget, self).__init__(**kwargs)
        self.image_grid.bind(minimum_height=self.image_grid.setter('height'),
                             minimum_width=self.image_grid.setter('width'))

    def change_label_colour(self, *args):

        colour = [random.random() for i in range(3)] + [1]
        self.text_colour = colour

    def on_touch_up(self, touch):

        if touch.button == 'right':
            p = touch.pos
            o = touch.opos
            # print(o, " -> ",p)
            # print(self.scroller.scroll_y)
            # print(self.scroller.scroll_x)
            s = min(p[0], o[0]), min(p[1], o[1]), abs(p[0] - o[0]), abs(p[1] - o[1])
            w = s[2]
            h = s[3]
            sx = s[0]
            sy = s[1]
            #only lower left to upper right works for clicking...
            #w and h have to both be positive
            if abs(w) > 5 and abs(h) > 5:
                if w < 0 or h < 0:
                    #self.float_layer.add_widget(Selection(pos=(abs(w), abs(h)), on_press=self.foo,size=touch.opos))
                    #self.float_layer.add_widget(Selection(pos=(abs(w), abs(h)),size=touch.opos))
                    ###self.float_layer.add_widget(Selection(pos=(sx,sy),size=(w, h)))
                    pass
                else:
                    #touch.pos  = p
                    #touch.opos = o
                    #min(p[0],o[0]), min(p[1],o[1]), abs(p[0]-o[0]), abs(p[1]-o[1])
                    ###self.float_layer.add_widget(Selection(pos=(sx,sy),size=(w, h)))
                    #self.float_layer.add_widget(Selection(pos=touch.opos, on_press=self.foo,size=(w, h)))
                    pass
        return super(ScatterTextWidget, self).on_touch_up(touch)

class ScrollViewer(ScrollView):

    @property
    def scroll_amount_y(self):
        return 0.2

    @property
    def scroll_amount_x(self):
        return 0.2

    def on_scroll_move(self, touch):
        # works, but laggier drag scrolling
        self.leave_trace()
        return super().on_scroll_move(touch)

    def zoom_in(self):
        self.enlarge()

    def zoom_out(self):
        self.shrink()

    def pan_down(self):
        self.scroll_y -= self.scroll_amount_y
        if self.scroll_y < 0:
            self.scroll_y = 0
        self.leave_trace()

    def pan_up(self):
        self.scroll_y += self.scroll_amount_y
        if self.scroll_y > 1:
            self.scroll_y = 1
        self.leave_trace()

    def pan_right(self):
        self.scroll_x += self.scroll_amount_x
        if self.scroll_x > 1:
            self.scroll_x = 1
        self.leave_trace()

    def pan_left(self):
        self.scroll_x -= self.scroll_amount_x
        if self.scroll_x < 0:
            self.scroll_x = 0
        self.leave_trace()

    def enlarge(self, zoom_amount=2):
        self.zoom_level += zoom_amount
        for child in self.parent.image_grid.children:
            #print(child, child.size)
            child.width *= zoom_amount
            child.height *= zoom_amount
        self.leave_trace()

    def shrink(self, zoom_amount=2):
        self.zoom_level -= zoom_amount
        for child in self.parent.image_grid.children:
            #print(child, child.size)
            child.width /= zoom_amount
            child.height /= zoom_amount
        self.leave_trace()

    def on_touch_down(self, touch):
        #self.dispatch('on_test_event', touch)  # Some event that happens with on_touch_down
        #zoom_amount = 100
        #zoom_amount = 2
        if touch.button == 'left':
            return super().on_touch_down(touch)
        elif touch.button == 'scrollup':
            self.enlarge()
        elif touch.button == 'scrolldown':
            self.shrink()
        # only return on_touch_down for left so that right
        # click + drag can be used to select 
        # regions
        # return super().on_touch_down(touch)

    def leave_trace(self):
        viewport_width, viewport_height = self.viewport_size
        scrollview_height, scrollview_width = self.parent.size
        focus_fov = [
              self.scroll_x * viewport_width,
              self.scroll_y * viewport_height,
              (self.scroll_x * viewport_width) + scrollview_height,
              (self.scroll_y * viewport_height) + scrollview_width,
              ]

        if self.zoom_level == 0:
            zoom_scale = 1
        else:
            zoom_scale = self.zoom_level

        # if negative divide
        if zoom_scale < 0:
            scaled_focus_fov = [coord * zoom_scale for coord in focus_fov]
        else:
            scaled_focus_fov = [coord / zoom_scale for coord in focus_fov]

        scaled_focus_fov = [abs(coord) for coord in scaled_focus_fov]

        # scaled_focus_fov = focus_fov        
        focus_trace = "focus:{name}".format(name=self.app.focus_name)
        # kivy canvas 0,0 is lower left corner
        try:
            map_name, map_page = self.app.map_index[self.app.active_map]
        except Exception as ex:
            print(ex)
            map_name, map_page = None, None
        redis_conn.hmset(focus_trace, {"name" : self.app.focus_name,
                                       "map" : map_name,
                                       "map_page" : map_page, 
                                       "x" : scaled_focus_fov[0],
                                       "y" : scaled_focus_fov[1],
                                       "x2" : scaled_focus_fov[2],
                                       "y2" : scaled_focus_fov[3],
                                       "w" : abs(scaled_focus_fov[0] - scaled_focus_fov[2]),
                                       "h" : abs(scaled_focus_fov[1] - scaled_focus_fov[3])}
                                       )
        redis_conn.expire(focus_trace, 30)
        print("created trace at {}".format(scaled_focus_fov))
        #redis_conn.expire(focus_trace, 20)

    def on_touch_up(self, touch):
        return super().on_touch_up(touch)

def get_resolution(x):
    x = str(x)
    x = x.partition("_")[-1].partition(".")[0]
    return int(x)

def get_hash(x):
    x = str(x)
    x = x.partition("_")[0]
    return x

class VzzGuiApp(App):
    def __init__(self, *args, **kwargs):
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self)
        self._keyboard.bind(on_key_down=self._on_keyboard_down)
        self.sources = {}
        # use to allow switching between maps and their contents
        self.map_index = {}
        self.active_map = None
        self.active_map_position = None
        self.actions = bindings.keybindings()
        if "orientation" in kwargs:
            # switch to make meaning of
            # commandline flags more intuitive
            if kwargs["orientation"] == "vertical":
                self.render_as = "horizontal"
            elif kwargs["orientation"] == "horizontal":
                self.render_as = "vertical"
        else:
            self.render_as = "horizontal"

        if "focus_name" in kwargs:
            self.focus_name = kwargs["focus_name"]
        else:
            self.focus_name = ""

        super(VzzGuiApp, self).__init__()

    def update_loops(self):
        print("updating loops....")
        self.loop_container.clear_loops()
        for key in redis_conn.scan_iter("vizaviz:{server}:loop:*".format(server="*")):
            loop = redis_conn.hgetall(key)
            print(loop)
            # check if loop already added
            try:
                if not self.loop_container.has_loop_by_id(loop['uuid']):
                    self.loop_container.add_loop(loop)
            except KeyError:
                pass

    def update_sources(self):
        print("updating sources...")
        for key in redis_conn.scan_iter("source:*"):
            source = {}
            source_keys = redis_conn.hkeys(key)
            # go key by key instead of hgetall
            # to correctly load binary keys...
            # source = redis_conn.hgetall(key)
            for k in source_keys:
                if "image:" in k:
                    image_bytes = io.BytesIO()
                    image_bytes.write(binary_redis_conn.hget(key, k))
                    image_bytes.seek(0)
                    source.update({k : image_bytes})
                else:
                    source.update({ k : redis_conn.hget(key, k)})
            try:
                s = self.sources[source["filehash"]] = {}
                s["filename"] = source["filename"]
                s["filehash"] = source["filehash"]
                s["duration"] = source["duration"]
                #s["resolutions"] = {}
                s["maps"] = {}
                for k, v in source.items():
                    if "map:" in k:
                        # as int to allow sorting
                        if "image:" in k:
                            # bunch of bytes
                            #map:foo:image:image_name
                            _, map_name, _, image_name = k.split(":")
                            if not map_name in s["maps"]:
                                s["maps"][map_name] = {}
                                s["maps"][map_name]["images"] = {}
                                s["maps"][map_name]["images"][image_name] = v
                                self.map_index[(map_name, image_name)] = (map_name, image_name)
                        elif "resolution:" in k:
                            _, map_name, _, resolution = k.split(":")
                            resolution = int(resolution)
                            #resolution = int(k.partition(":")[-1])
                            raw_map = list(filter(None, v.split(" ")))
                            if not map_name in s["maps"]:
                                s["maps"][map_name] = {}
                                s["maps"][map_name]["resolutions"] = {}
                            s["maps"][map_name]["resolutions"][resolution] = {}
                            s["maps"][map_name]["resolutions"][resolution]["raw"] = v
                            s["maps"][map_name]["resolutions"][resolution]["renders"] = {}
                            # use tuple for lru cache
                            # may not be much of a benefit
                            s["maps"][map_name]["resolutions"][resolution]["renders"]["vertical"] = visualize_map(map_raw=tuple(raw_map),
                                                                                                resolution=int(resolution),
                                                                                                cell_width=1,
                                                                                                return_format="JPEG",
                                                                                                return_image=True)
                            s["maps"][map_name]["resolutions"][resolution]["renders"]["horizontal"] = visualize_map(map_raw=tuple(raw_map),
                                                                                                  resolution=int(resolution),
                                                                                                  columns="auto",
                                                                                                  reverse_image=True,
                                                                                                  return_format="JPEG",
                                                                                                  return_image=True)
            except KeyError:
                pass

    def display_sources(self):
        self.group_container.image_grid.clear_widgets()
        # sort sources
        for source, source_data in sorted(self.sources.items()):
            # sort by resolution
            for resolution, resolution_data in sorted(source_data["maps"]["rgb_map"]["resolutions"].items()):
                for render, image in resolution_data["renders"].items():
                    if render == self.render_as:
                        # pass use_once to CoreImage
                        use_once = io.BytesIO(image.read())
                        image.seek(0)
                        img = ClickableSourceImage(self)
                        # store attributes for calculating row / column
                        # to create loops
                        img.filename = source_data["filename"]
                        img.filehash = source_data["filehash"]
                        img.render = render
                        img.resolution = resolution

                        img.allow_stretch = True
                        img.texture = CoreImage(use_once, ext="jpg").texture
                        img.size = img.texture_size
                        ww, hh= img.size
                        if self.active_map:
                            # always stretch active_maps to rgb_map dimensions
                            try:
                                map_name, map_page = self.map_index[self.active_map]
                                ii = source_data["maps"][map_name]["images"][map_page]
                                uu = io.BytesIO(ii.read())
                                ii.seek(0)
                                img.allow_stretch = True
                                img.keep_ratio = False
                                img.texture = CoreImage(uu, ext="jpg").texture
                                img.width = ww
                                img.height = hh
                            except Exception as ex:
                                print(ex)
                                pass
                        # important to set to (None, None) for expected scaling behavior
                        img.size_hint = (None,None)
                        self.group_container.image_grid.add_widget(img)

    def display_traces(self, trace_key):
        trace = redis_conn.hgetall(trace_key)
        try:
            name = trace['name']
            map_name = trace['map']
            map_page = trace['map_page']

            # use abs for -0.0
            x = abs(float(trace['x']))
            y = abs(float(trace['y']))
            w = abs(float(trace['w']))
            h = abs(float(trace['h']))
            # offsets are incorrect
            # adjustments for zoom in/out incorrect
            # would be useful to send on viewscroll scroll 
            if self.group_container.scroller.zoom_level == 0:
                zoom_scale = 1
            else:
                zoom_scale = self.group_container.scroller.zoom_level

            if zoom_scale < 0:
                x /= zoom_scale
                y /= zoom_scale
                w /= zoom_scale
                h /= zoom_scale
            else:
                x *= zoom_scale
                y *= zoom_scale
                w *= zoom_scale
                h *= zoom_scale

            viewport_width, viewport_height = self.group_container.scroller.viewport_size
            #x_offset = self.group_container.scroller.scroll_x * viewport_width
            y_offset = self.group_container.scroller.scroll_y * viewport_width
            x_offset = 0
            #y_offset = 0
            x = abs(x) - x_offset
            y = abs(y) - y_offset
            w = abs(w)
            h = abs(h)

            with self.group_container.canvas:
                self.group_container.canvas.remove_group(name)
                # Rectangle(pos=(x,y), size=(w, h), group=name)
                trace_caption = "{name} {map_name} {map_page}".format(name=name, map_name=map_name, map_page=map_page)
                caption = CoreLabel(text=trace_caption, font_size=10, color=(1, 1, 1, 1))
                caption.refresh()
                texture = caption.texture
                texture_size = list(texture.size)
                Rectangle(pos=(x,y), texture=texture, size=texture_size, group=name)
                Line(rectangle=(x,y,w,h), fill=(0,0,0,0), width=1, group=name)
                # print("drawing trace at {} {} {} {}".format(x,y,w,h))
        except Exception as ex:
            # key has expired/is empty
            # remove
            name = trace_key.partition("focus:")[-1]
            with self.group_container.canvas:
                self.group_container.canvas.remove_group(name)

    def on_stop(self):
        # stop pubsub thread if window closed with '[x]'
        self.db_event_subscription.thread.stop()

    def build(self):
        self.title = "vizavizgui - {}".format(self.focus_name)
        # root = BoxLayout(orientation="vertical")
        root = TabbedPanel(do_default_tab=False)
        self.root = root
        root.tab_width = 200

        loops_layout = LoopContainer(orientation='vertical',
                                     size_hint_y=None,
                                     size_hint_x=1,
                                     #height=1000,
                                     minimum_height=Window.height)
        loops_scroll = ScrollView(bar_width=20, size_hint_y=None, height=Window.height-40)
        loops_scroll.add_widget(loops_layout)

        loops_detailed = StencilBoxLayout(height=Window.height-40, width=Window.width-40, size_hint=(1,1)) #StencilView()
        self.loop_container = loops_layout
        self.detailed = loops_detailed

        self.group_container = ScatterTextWidget()
        self.group_container.scroller.app = self

        self.update_sources()
        self.display_sources()
        # for first update
        # update loops after sources
        self.update_loops()

        source_files = []
        sorted_source_files = []

        if self.render_as == "vertical":
            self.group_container.image_grid.cols = 1
            self.group_container.image_grid.rows = None

        # if size is set to full window, will cover tabs
        tab_height = 40
        self.group_container.scroller.size = (Window.width, Window.height- tab_height)
        self.group_container.scroller.size_hint = (None, None)

        # add tabs
        tab = TabItem(text="maps",root=root)
        tab.tab_name = "maps"
        tab.add_widget(self.group_container)
        root.add_widget(tab)

        tab = TabItem(text="loops",root=root)
        tab.tab_name = "loops"
        # do check for selected_loop to correctly handle
        # passing keyboard events
        tab.sub_content = [loops_layout]
        t = BoxLayout(orientation="horizontal")
        t.add_widget(loops_detailed)
        t.add_widget(loops_scroll)
        tab.add_widget(t)
        root.add_widget(tab)

        #root.add_widget(loops_scroll)
        root.add_widget(self.group_container)

        self.db_event_subscription = redis_conn.pubsub()
        self.db_event_subscription.psubscribe(**{'__keyspace@0__:*': self.handle_db_events})
        # add thread to pubsub object to 
        # stop() on exit
        self.db_event_subscription.thread = self.db_event_subscription.run_in_thread(sleep_time=0.001)
        return root

    def handle_db_events(self, message):
        # this is being called from a different thread and causing
        # issues?
        # use kivy Clock to schedule once instead of calling directly
        if ":source:" in message["channel"]:
            Clock.schedule_once(lambda dt: self.update_sources())
            Clock.schedule_once(lambda dt: self.display_sources())
        elif ":focus:" in message["channel"]:
            # focus / traces are independent of server
            # since gui may be combining from several servers
            print(message)
            # behavior stills seems problematic
            # speed of callbacks and delays in clock scheduling?
            trace_key = message["channel"].replace("__keyspace@0__:","")
            # self.display_traces(trace_key)
            Clock.schedule_once(lambda dt, trace_key=trace_key: self.display_traces(trace_key))
        elif ":loop:" in message["channel"]:
            print("update?",message)
            # need to change update_loops to update loops instead
            # of clear / recreate from db
            #Clock.schedule_once(lambda dt: self.update_loops())

    def _keyboard_closed(self):
        # do not unbind the keyboard because
        # if keyboard is requested by textinput
        # widget, this keyboard used for app keybinds
        # will be unbound and not rebound after
        # defocusing textinput widget
        #
        # self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        # self._keyboard = None
        pass

    def tab_next(self):
        print(self.root.tab_list)
        for i, c in enumerate(self.root.tab_list):
            if c == self.root.current_tab:
                if i > 0:
                    self.root.switch_to(self.root.tab_list[i - 1], do_scroll=True)
                    break
                else:
                    self.root.switch_to(self.root.tab_list[len(self.root.tab_list) - 1], do_scroll=True)
                    break

    def tab_previous(self):
        for i, c in enumerate(self.root.tab_list):
            if c == self.root.current_tab:
                try:
                    self.root.switch_to(self.root.tab_list[i + 1], do_scroll=True)
                    break
                except IndexError as ex:
                    self.root.switch_to(self.root.tab_list[0], do_scroll=True)
                    break

    def map_next(self):
        # want to cycle through maps forwards or backwards
        #self.active_map = None
        if self.active_map_position is None:
            self.active_map_position = 0
        else:
            self.active_map_position =+1  
        try:
            self.active_map = sorted(self.map_index.keys())[self.active_map_position]
        except:
            self.active_map = None
            self.active_map_position = None
        # if self.render_as == "vertical":
        #     self.render_as = "horizontal"
        #     self.group_container.image_grid.cols = None
        #     self.group_container.image_grid.rows = 1

        # elif self.render_as == "horizontal":
        #     self.render_as = "vertical"
        #     self.group_container.image_grid.cols = 1
        #     self.group_container.image_grid.rows = None
        self.display_sources()

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        for actions in ["app", self.root.current_tab.tab_name]:
            for k, v in self.actions[actions].items():
                if keycode[1] in v[0] and not v[1] and not modifiers:
                    try:
                        getattr(self, "{}".format(k))()
                    except Exception as ex:
                        #print(ex)
                        pass
                    # use .content.children for tabs
                    for c in self.root.current_tab.content.children:
                        try:
                            getattr(c, "{}".format(k))()
                        except Exception as ex:
                            print(ex)

                    for lower_widget in self.root.current_tab.sub_content:
                        for c in lower_widget.children:
                            try:
                                getattr(c, "{}".format(k))()
                            except Exception as ex:
                                print(ex)

                elif keycode[1] in v[0] and modifiers:
                    if len(set(v[1]).intersection(set(modifiers))) == len(modifiers):
                        try:
                            getattr(self, "{}".format(k))()
                        except Exception as ex:
                            # print(ex)
                            pass

                        for c in self.root.current_tab.content.children:
                            try:
                                getattr(c, "{}".format(k))()
                            except Exception as ex:
                                print(ex)

                        for lower_widget in self.root.current_tab.sub_content:
                            for c in lower_widget.children:
                                try:
                                    getattr(c, "{}".format(k))()
                                except Exception as ex:
                                    print(ex)

    def app_exit(self):
        self.db_event_subscription.thread.stop()
        App.get_running_app().stop()

    def create_loop(self, filename, start=0, end=-1, status="active", filehash=None):
        loop = {}
        loop['uuid'] = str(uuid.uuid4())
        loop['filename'] = filename
        loop['status'] = status
        loop['start'] = start
        loop['end'] = end
        if filehash:
            loop['filehash'] = filehash

        redis_conn.hmset("vizaviz:{server}:loop:{loop_id}".format(server="foo", loop_id=loop['uuid']), loop)
        # overlay focus fov zoomfactor, windowx windowy
        # static/dynamic annotations?
        focus_trace = "focus:{name}".format(name=self.focus_name)
        redis_conn.hmset(focus_trace, {"filename":filename, "start":start, "end":end})
        redis_conn.expire(focus_trace, 30)
        # update gui
        self.update_loops()

class ClickableSourceImage(Image):
    def __init__(self, app, **kwargs):
        self.app = app
        super(ClickableSourceImage, self).__init__(**kwargs)

    # def on_touch_down(self, touch):
    #     if touch.button == 'left':
    #         if self.collide_point(touch.pos[0], touch.pos[1]):
    #             pass
    #     return super().on_touch_down(touch)

    def on_touch_up(self, touch):

        if self.render == 'horizontal':
            default_cell_height = 10
            default_cell_width = 10
        elif self.render == 'vertical':
            default_cell_height = 10
            default_cell_width = 1

        if touch.button == 'right':
            p = touch.pos
            o = touch.opos
            s = min(p[0], o[0]), min(p[1], o[1]), abs(p[0] - o[0]), abs(p[1] - o[1])
            w = s[2]
            h = s[3]
            sx = s[0]
            sy = s[1]

            if self.collide_point(touch.pos[0], touch.pos[1]):
                width_scale = self.texture_size[0] / self.norm_image_size[0]
                height_scale = self.texture_size[1] / self.norm_image_size[1]
                width_offset = (self.size[0] - self.norm_image_size[0]) / 2
                print("image: touch", touch.pos, touch.opos)
                print("image:  window pos", self.to_window(*self.pos))
                print(self.texture_size, self.norm_image_size, self.size)
                print(width_scale, height_scale, width_offset)

                if self.render == 'horizontal':
                    starting_row = math.ceil(touch.opos[1] / default_cell_height * height_scale)
                    ending_row = math.ceil(touch.pos[1] / default_cell_height * height_scale)
                    if ending_row == starting_row:
                        ending = -1
                    else:
                        ending = ending_row
                    self.app.create_loop(self.filename, start=starting_row, end=ending, filehash=self.filehash)
                elif self.render == 'vertical':
                    starting_col = math.ceil(touch.opos[0] / (default_cell_width * float(self.resolution)) * width_scale)
                    ending_col = math.ceil(touch.pos[0] / (default_cell_width * float(self.resolution)) * width_scale)
                    # print(starting_col, ending_col)
                    if ending_col == starting_col:
                        ending = -1
                    else:
                        ending = ending_col
                    self.app.create_loop(self.filename, start=starting_col, end=ending, filehash=self.filehash)

        return super().on_touch_up(touch)

if __name__ == "__main__":
    #redis-server config.ini --requirepass foo
    parser = argparse.ArgumentParser()
    parser.add_argument("--orientation", default="vertical")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=6379)
    parser.add_argument("--auth", default="")
    parser.add_argument("--focus-name", default="")

    args = parser.parse_args()

    try:
        r_ip, r_port = args.host, args.port
        redis_conn = redis.StrictRedis(host=r_ip, port=r_port, decode_responses=True)
        binary_redis_conn = redis.StrictRedis(host=r_ip, port=r_port)
    except redis.exceptions.ConnectionError:
        pass

    app = VzzGuiApp(**vars(args))
    app.run()
