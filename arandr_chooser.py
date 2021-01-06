#!/usr/bin/env python
import os
import screenlayout
import screenlayout.xrandr
import screenlayout.widget
import subprocess

config_path = "~/.screenlayout"
scripts = [os.path.expanduser(config_path) + "/" + s for s in os.listdir(os.path.expanduser(config_path)) if s.endswith(".sh")]


import gi
gi.require_version("Gtk", "3.0")
gi.require_version('PangoCairo', '1.0')
from gi.repository import GObject, Gtk, Pango, PangoCairo, Gdk, GLib


class MyARandRWidget(Gtk.DrawingArea):
    __gsignals__ = {
        # 'expose-event':'override', # FIXME: still needed?
        'changed': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, window, factor=8, display=None, force_version=False):
        super(MyARandRWidget, self).__init__()

        self.window = window
        self._factor = factor

        factor = 10

        c = 1024
        self.set_size_request(
            c // self.factor, c // self.factor
        )  # best guess for now

        self._xrandr = screenlayout.xrandr.XRandR(display=display, force_version=force_version)
        self.connect('draw', self.do_expose_event)

    # #################### widget features ####################

    def _set_factor(self, fac):
        self._factor = fac
        self._update_size_request()
        self._force_repaint()

    factor = property(lambda self: self._factor, _set_factor)

    def _update_size_request(self):
        # TODO: fix this to check adjacence etc
        outputs = self._xrandr.configuration.outputs.values()
        max_height = sum(output.mode.height for output in outputs if output.active)
        max_width = sum(output.mode.width for output in outputs if output.active)
        xdim = min(self._xrandr.state.virtual.max[0], max_width)
        ydim = min(self._xrandr.state.virtual.max[1], max_height)
        self.set_size_request(xdim // self.factor, ydim // self.factor)

    # #################### loading ####################

    def _xrandr_was_reloaded(self):
        self.sequence = sorted(self._xrandr.outputs)

        self._update_size_request()
        if self.window:
            self._force_repaint()
        self.emit('changed')

    def load_from_file(self, file):
        data = open(file).read()
        template = self._xrandr.load_from_string(data)
        self._xrandr_was_reloaded()
        return template

    # #################### painting ####################

    def do_expose_event(self, _event, context):
        context.save()
        context.rectangle(
            0, 0,
            self._xrandr.state.virtual.max[0] // self.factor,
            self._xrandr.state.virtual.max[1] // self.factor
        )
        context.clip()

        # clear
        context.set_source_rgb(0, 0, 0)
        context.rectangle(0, 0, *self.window.get_size())
        context.fill()

        context.scale(1 / self.factor, 1 / self.factor)
        context.set_line_width(self.factor * 1.5)

        self._draw(self._xrandr, context)
        context.restore()


    def _draw(self, xrandr, context):  # pylint: disable=too-many-locals
        cfg = xrandr.configuration
        state = xrandr.state

        context.set_source_rgb(0.25, 0.25, 0.25)
        context.rectangle(0, 0, *state.virtual.max)
        context.fill()

        context.set_source_rgb(0.5, 0.5, 0.5)
        context.rectangle(0, 0, *cfg.virtual)
        context.fill()

        for output_name in self.sequence:
            output = cfg.outputs[output_name]
            if not output.active:
                continue

            rect = (output.tentative_position if hasattr(
                output, 'tentative_position') else output.position) + tuple(output.size)
            center = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2

            # paint rectangle
            context.set_source_rgba(1, 1, 1, 0.7)
            context.rectangle(*rect)
            context.fill()
            context.set_source_rgb(0, 0, 0)
            context.rectangle(*rect)
            context.stroke()

            # set up for text
            context.save()
            textwidth = rect[3 if output.rotation.is_odd else 2]
            widthperchar = textwidth / len(output_name)
            # i think this looks nice and won't overflow even for wide fonts
            textheight = int(widthperchar * 0.8)

            newdescr = Pango.FontDescription("sans")
            newdescr.set_size(textheight * Pango.SCALE)

            # create text
            output_name_markup = GLib.markup_escape_text(output_name)
            layout = PangoCairo.create_layout(context)
            layout.set_font_description(newdescr)
            if output.primary:
                output_name_markup = "<u>%s</u>" % output_name_markup

            layout.set_markup(output_name_markup, -1)

            # position text
            layoutsize = layout.get_pixel_size()
            layoutoffset = -layoutsize[0] / 2, -layoutsize[1] / 2
            context.move_to(*center)
            context.rotate(output.rotation.angle)
            context.rel_move_to(*layoutoffset)

            # paint text
            PangoCairo.show_layout(context, layout)
            context.restore()

    def _force_repaint(self):
        # using self.allocation as rect is offset by the menu bar.

        self.queue_draw_area(
            0, 0,
            self._xrandr.state.virtual.max[0] // self.factor,
            self._xrandr.state.virtual.max[1] // self.factor
        )
        # this has the side effect of not painting out of the available
        # region output_name drag and drop


def use_script(script, args):
    print("Applying", script)
    subprocess.run(script)

def create_lambda(script):
    return lambda *args: use_script(script, args)

win = Gtk.Window()
hbox = Gtk.HBox(spacing=10)
win.add(hbox)

for script in scripts:
    arandr = MyARandRWidget(window=win)
    try:
        arandr.load_from_file(script)
    except screenlayout.auxiliary.FileLoadError:
        print("Warning: Problem loading script", script)
        continue

    vbox = Gtk.VBox()
    vbox.pack_start(arandr, expand=True, fill=True, padding=0)
    button = Gtk.Button(label=script)

    button.connect('clicked', create_lambda(script))

    vbox.pack_start(button, expand=False, fill=False, padding=0)

    hbox.pack_start(vbox, expand=True, fill=True, padding=0)

win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
