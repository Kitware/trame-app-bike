import os
from pathlib import Path
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from trame.assets.local import to_url
from trame.decorators import TrameApp, change
from trame.widgets import vuetify3, trame

from trame.widgets import vtklocal
from trame.widgets import vtk as vtk_widgets

from vtkmodules.vtkCommonColor import vtkColorSeries, vtkNamedColors
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLUnstructuredGridReader
from vtkmodules.vtkFiltersSources import vtkLineSource
from vtkmodules.vtkFiltersFlowPaths import vtkStreamTracer
from vtkmodules.vtkFiltersCore import vtkTubeFilter
from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkRenderingCore import (
    vtkRenderer,
    vtkRenderWindow,
    vtkRenderWindowInteractor,
    vtkPolyDataMapper,
    vtkActor,
)

# VTK factory initialization
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleSwitch  # noqa
import vtkmodules.vtkRenderingOpenGL2  # noqa

WASM = int(os.environ.get("VTK_USE_WASM", 0))

IMAGE = str((Path(__file__).parent / "data/seeds.jpg").resolve())
BIKE = str((Path(__file__).parent / "data/bike.vtp").resolve())
TUNNEL = str((Path(__file__).parent / "data/tunnel.vtu").resolve())

K_RANGE = [0.0, 15.6]


def MakeLUT(color_scheme=0):
    """
    Make a lookup table.
    :param color_scheme: Select the type of lookup table.
    :return: The lookup table.
    """
    colors = vtkNamedColors()
    if color_scheme == 1:
        # A lookup table of 256 colours ranging from
        #  deep blue (water) to yellow-white (mountain top)
        #  is used to color map this figure.
        lut = vtkLookupTable()
        lut.SetHueRange(0.7, 0)
        lut.SetSaturationRange(1.0, 0)
        lut.SetValueRange(0.5, 1.0)
    elif color_scheme == 2:
        # Make the lookup table with a preset number of colours.
        colorSeries = vtkColorSeries()
        colorSeries.SetNumberOfColors(8)
        colorSeries.SetColorSchemeName("Hawaii")
        colorSeries.SetColor(0, colors.GetColor3ub("turquoise_blue"))
        colorSeries.SetColor(1, colors.GetColor3ub("sea_green_medium"))
        colorSeries.SetColor(2, colors.GetColor3ub("sap_green"))
        colorSeries.SetColor(3, colors.GetColor3ub("green_dark"))
        colorSeries.SetColor(4, colors.GetColor3ub("tan"))
        colorSeries.SetColor(5, colors.GetColor3ub("beige"))
        colorSeries.SetColor(6, colors.GetColor3ub("light_beige"))
        colorSeries.SetColor(7, colors.GetColor3ub("bisque"))
        lut = vtkLookupTable()
        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        lut.SetNanColor(1, 0, 0, 1)
    else:
        # Make the lookup using a Brewer palette.
        colorSeries = vtkColorSeries()
        colorSeries.SetNumberOfColors(8)
        colorSeriesEnum = colorSeries.BREWER_DIVERGING_BROWN_BLUE_GREEN_8
        colorSeries.SetColorScheme(colorSeriesEnum)
        lut = vtkLookupTable()
        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        lut.SetNanColor(1, 0, 0, 1)
    return lut


@TrameApp()
class CFDApp:
    def __init__(self, server=None):
        self.server = get_server(server, client_type="vue3")
        self.render_window, self.seed, self.mapper = self._setup_vtk()
        self.ui = self._ui()
        self.ctrl.view_update()

    @property
    def state(self):
        return self.server.state

    @property
    def ctrl(self):
        return self.server.controller

    def _setup_vtk(self):
        resolution = 50
        point1 = [-0.4, 0, 0.05]
        point2 = [-0.4, 0, 1.5]
        self.state.seed = dict(p1=point1, p2=point2, resolution=resolution)

        renderer = vtkRenderer()
        renderWindow = vtkRenderWindow()
        renderWindow.AddRenderer(renderer)
        if not WASM:
            renderWindow.OffScreenRenderingOn()

        renderWindowInteractor = vtkRenderWindowInteractor()
        renderWindowInteractor.SetRenderWindow(renderWindow)
        renderWindowInteractor.GetInteractorStyle().SetCurrentStyleToTrackballCamera()

        bikeReader = vtkXMLPolyDataReader()
        bikeReader.SetFileName(BIKE)

        tunnelReader = vtkXMLUnstructuredGridReader()
        tunnelReader.SetFileName(TUNNEL)

        lineSeed = vtkLineSource()
        lineSeed.SetPoint1(*point1)
        lineSeed.SetPoint2(*point2)
        lineSeed.SetResolution(resolution)

        streamTracer = vtkStreamTracer()
        streamTracer.SetInputConnection(tunnelReader.GetOutputPort())
        streamTracer.SetSourceConnection(lineSeed.GetOutputPort())
        streamTracer.SetIntegrationDirectionToForward()
        streamTracer.SetIntegratorTypeToRungeKutta45()
        streamTracer.SetMaximumPropagation(3)
        streamTracer.SetIntegrationStepUnit(2)
        streamTracer.SetInitialIntegrationStep(0.2)
        streamTracer.SetMinimumIntegrationStep(0.01)
        streamTracer.SetMaximumIntegrationStep(0.5)
        streamTracer.SetMaximumError(0.000001)
        streamTracer.SetMaximumNumberOfSteps(2000)
        streamTracer.SetTerminalSpeed(0.00000000001)

        tubeFilter = vtkTubeFilter()
        tubeFilter.SetInputConnection(streamTracer.GetOutputPort())
        tubeFilter.SetRadius(0.01)
        tubeFilter.SetNumberOfSides(6)
        tubeFilter.CappingOn()
        tubeFilter.Update()

        bike_mapper = vtkPolyDataMapper()
        bike_actor = vtkActor()
        bike_mapper.SetInputConnection(bikeReader.GetOutputPort())
        bike_actor.SetMapper(bike_mapper)
        renderer.AddActor(bike_actor)

        stream_mapper = vtkPolyDataMapper()
        stream_actor = vtkActor()
        stream_mapper.SetInputConnection(tubeFilter.GetOutputPort())
        stream_actor.SetMapper(stream_mapper)
        renderer.AddActor(stream_actor)

        lut = MakeLUT(2)

        stream_mapper.SetLookupTable(lut)
        stream_mapper.SetColorModeToMapScalars()
        stream_mapper.SetScalarModeToUsePointData()
        stream_mapper.SetArrayName("k")
        stream_mapper.SetScalarRange(K_RANGE)

        renderWindow.Render()
        renderer.ResetCamera()
        renderer.SetBackground(0.4, 0.4, 0.4)

        return renderWindow, lineSeed, stream_mapper

    def _ui(self):
        with SinglePageWithDrawerLayout(self.server, full_height=True) as layout:
            layout.title.set_text("CFD demo")
            with layout.toolbar:
                vuetify3.VSpacer()
                with vuetify3.VBtnToggle(
                    v_model=("color_preset", 0),
                    density="compact",
                    rounded=True,
                ):
                    vuetify3.VBtn("C1", value=0)
                    vuetify3.VBtn("C2", value=1)
                    vuetify3.VBtn("C3", value=2)
                vuetify3.VSpacer()
                vuetify3.VBtn(icon="mdi-crop-free", click=self.ctrl.view_reset_camera)

            with layout.drawer:
                trame.LineSeed(
                    image=to_url(IMAGE),
                    point_1=("p1", [-0.399, 0, 0]),
                    point_2=("p2", [-0.399, 0, 1.25]),
                    bounds=("[-0.399, 1.80, -1.12, 1.11, -0.43, 1.79]",),
                    update_seed="seed = $event",
                    n_sliders=0,
                )
                vuetify3.VSlider(
                    v_model=("resolution", 50),
                    min=5,
                    max=100,
                    step=5,
                    density="compact",
                )

            with layout.content:
                with vuetify3.VContainer(classes="fill-height pa-0 ma-0", fluid=True):
                    if WASM:
                        view = vtklocal.LocalView(
                            self.render_window,
                            cache_size=100000000,
                            eager_sync=True,
                        )
                    else:
                        view = vtk_widgets.VtkRemoteView(
                            self.render_window, interactive_ratio=1
                        )
                    self.ctrl.view_update = view.update
                    self.ctrl.view_reset_camera = view.reset_camera

            return layout

    @change("seed", "resolution")
    def update_seed_line(self, seed, resolution, **_):
        p1 = seed.get("p1")
        p2 = seed.get("p2")
        self.seed.SetPoint1(*p1)
        self.seed.SetPoint2(*p2)
        self.seed.SetResolution(resolution)
        self.ctrl.view_update()

    @change("color_preset")
    def update_lut(self, color_preset, **_):
        lut = MakeLUT(int(color_preset))
        self.mapper.SetLookupTable(lut)
        self.ctrl.view_update()


def main():
    app = CFDApp()
    app.server.start()


if __name__ == "__main__":
    main()
