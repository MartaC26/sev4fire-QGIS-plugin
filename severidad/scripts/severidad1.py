# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Severidad
                                 A QGIS plugin
 This plugin calculates the severity of a fire
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-06-13
        git sha              : $Format:%H$
        copyright            : (C) 2024 by Marta Cumplido
        email                : uo302257@uniovi.es
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog
from qgis.core import (
    QgsApplication, QgsProject, Qgis, QgsRasterLayer, QgsVectorLayer,
    QgsGeometry, QgsRaster, QgsPointXY, QgsFeature, QgsField, QgsFields,
    QgsVectorFileWriter, QgsWkbTypes, QgsCoordinateTransform,
    QgsVectorDataProvider, QgsRendererCategory, QgsFillSymbol,
    QgsCategorizedSymbolRenderer
)
import processing
from osgeo import gdal
import numpy as np
import os
from pathlib import Path
import matplotlib.pyplot as plt

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .severidad_dialog import SeveridadDialog
import os.path


class Severidad:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Severidad_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&sev4fire')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Severidad', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):

        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToRasterMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/severidad/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Calculate the Severity'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginRasterMenu(
                self.tr(u'&sev4fire'),
                action)
            self.iface.removeToolBarIcon(action)

    def select_vector_output_file(self):
        filename, _filter = QFileDialog.getSaveFileName(
            self.dlg, "Select vector output file ","", '*.shp')
        if filename:
            self.dlg.lineEdit_v.setText(filename)
            # Llamar a la función para copiar los archivos asociados al Shapefile
            self.copy_shapefile_associated_files(filename)
            # Guardar la ruta completa del archivo en una variable de instancia
            self.output_polygon_path = filename

    def select_graphic_output_file(self):
        filename, _filter = QFileDialog.getSaveFileName(
            self.dlg, "Select graphic output file ","", '*.png')
        if filename:
            self.dlg.lineEdit_g.setText(filename)
            # Guardar la ruta completa del archivo en una variable de instancia
            self.graf = filename

    def copy_shapefile_associated_files(self, filename):
        temp_dir = "C:/Incendio/"
        base_name = os.path.splitext(os.path.basename(filename))[0]
        destination_dir = os.path.dirname(filename)

        # Lista de extensiones de archivos asociados al Shapefile
        extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.qix']

        for ext in extensions:
            src = os.path.join(temp_dir, base_name + ext)
            dst = os.path.join(destination_dir, base_name + ext)

            if os.path.exists(src):
                shutil.copy(src, dst)

    def run(self):
        """Run method that performs all the real work"""
        dir_datos = "C:/Incendio/"

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = SeveridadDialog()
            self.dlg.pushButton_v.clicked.connect(self.select_vector_output_file)
            self.dlg.pushButton_g.clicked.connect(self.select_graphic_output_file)

        # Fetch the currently loaded layers
        layers = QgsProject.instance().layerTreeRoot().children()
        # Clear the contents of the comboBox from previous runs
        self.dlg.comboBox_CP.clear()
        self.dlg.comboBox_8APre.clear()
        self.dlg.comboBox_8APost.clear()
        self.dlg.comboBox_12Pre.clear()
        self.dlg.comboBox_12Post.clear()
        self.dlg.comboBox_3Pre.clear()
        self.dlg.comboBox_3Post.clear()
        self.dlg.comboBox_CMPre.clear()
        self.dlg.comboBox_CMPost.clear()
        # Populate the comboBox with names of all the loaded layers
        self.dlg.comboBox_CP.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_8APre.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_8APost.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_12Pre.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_12Post.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_3Pre.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_3Post.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_CMPre.addItems([layer.name() for layer in layers])
        self.dlg.comboBox_CMPost.addItems([layer.name() for layer in layers])

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()

        #CAPAS DE ENTRADA
        # Bandas pre y post incendio
        banda_8A_pre = str(self.dlg.comboBox_8APre.currentText())
        banda_12_pre = str(self.dlg.comboBox_12Pre.currentText())
        banda_8A_post = str(self.dlg.comboBox_8APost.currentText())
        banda_12_post = str(self.dlg.comboBox_12Post.currentText())

        banda_8A_pre = f"{banda_8A_pre}.jp2"
        banda_12_pre = f"{banda_12_pre}.jp2"
        banda_8A_post = f"{banda_8A_post}.jp2"
        banda_12_post = f"{banda_12_post}.jp2"

        banda_8A_pre = os.path.join(dir_datos, banda_8A_pre)
        banda_12_pre = os.path.join(dir_datos, banda_12_pre)
        banda_8A_post = os.path.join(dir_datos, banda_8A_post)
        banda_12_post = os.path.join(dir_datos, banda_12_post)

        banda3_pre = os.path.join(dir_datos,str(self.dlg.comboBox_3Pre.currentText()))
        banda3_post = os.path.join(dir_datos,str(self.dlg.comboBox_3Post.currentText()))

        banda3_pre = f"{banda3_pre}.jp2"
        banda3_post = f"{banda3_post}.jp2"

        banda3_pre = os.path.join(dir_datos, banda3_pre)
        banda3_post = os.path.join(dir_datos, banda3_post)

        #Mascara de nubes
        nubes_pre = os.path.join(dir_datos,str(self.dlg.comboBox_CMPre.currentText()))
        nubes_post = os.path.join(dir_datos,str(self.dlg.comboBox_CMPost.currentText()))

        nubes_pre = f"{nubes_pre}.jp2"
        nubes_post = f"{nubes_post}.jp2"

        nubes_pre = os.path.join(dir_datos, nubes_pre)
        nubes_post = os.path.join(dir_datos, nubes_post)

        #Punto central del incendio
        punto = os.path.join(dir_datos,str(self.dlg.comboBox_CP.currentText()))

        punto = f"{punto}.shp"

        punto = os.path.join(dir_datos, punto)

        #CAPAS DE SALIDA
        # Rutas de salida para los archivos NBR y dNBR, mascaras y filtrados
        salida_nbr_pre = os.path.join(dir_datos, 'NBR_pre.tif')
        salida_nbr_post = os.path.join(dir_datos, 'NBR_post.tif')
        salida_dnbr = os.path.join(dir_datos, 'dNBR.tif')

        PRE_nubes = os.path.join(dir_datos, 'nubes_pre.tif')
        POST_nubes = os.path.join(dir_datos, 'nubes_post.tif')
        mascara_nubes = os.path.join(dir_datos,'mascara_nubes.tif')
        mascara_agua = os.path.join(dir_datos, 'mascara_agua.tif')
        mascara_nubes_agua = os.path.join(dir_datos, 'mascara_nubes_agua.tif')
        dNBR_filtrado = os.path.join(dir_datos,'dNBR_filtrado.tif')
        dNBR_filtrado_umbral = os.path.join(dir_datos, 'dNBR_filtrado_umbral.tif')
        buffer_incendio = os.path.join(dir_datos, 'Area_Quemada.shp')
        raster_incendio = os.path.join(dir_datos, 'Quemado.tif')
        sev_raster_path = os.path.join(dir_datos, "sev_incendio.tif")
        sieved_raster_path = os.path.join(dir_datos, "sieved_incendio.tif")

        output_polygon_path = self.output_polygon_path
        graf = self.graf

        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.

            #ELIMINAR ARCHIVOS SI EXISTEN
            # Función para eliminar archivos si existen
            def eliminar_archivo(ruta):
                if os.path.exists(ruta):
                    os.remove(ruta)
                    self.iface.messageBar().pushMessage(f"Archivo {ruta} eliminado",
                        level=Qgis.Success, duration=3)
                else:
                    self.iface.messageBar().pushMessage(f"Archivo {ruta} no existe",
                        level=Qgis.Success, duration=3)

            # Eliminar archivos de salida si existen
            eliminar_archivo(salida_nbr_pre)
            eliminar_archivo(salida_nbr_post)
            eliminar_archivo(salida_dnbr)

            eliminar_archivo(PRE_nubes)
            eliminar_archivo(POST_nubes)
            eliminar_archivo(mascara_nubes)
            eliminar_archivo(mascara_agua)
            eliminar_archivo(mascara_nubes_agua)
            eliminar_archivo(dNBR_filtrado)
            eliminar_archivo(dNBR_filtrado_umbral)
            eliminar_archivo(sev_raster_path)
            eliminar_archivo(sieved_raster_path)
            eliminar_archivo(output_polygon_path)
            eliminar_archivo(graf)

            # Eliminar archivos de salida si ya existen
            if os.path.exists(buffer_incendio):
                os.remove(buffer_incendio)
                # También hay que eliminar los archivos auxiliares generados por shapefiles
                for ext in ['.shx', '.dbf', '.prj', '.cpg']:
                    aux_file = buffer_incendio.replace('.shp', ext)
                    if os.path.exists(aux_file):
                        os.remove(aux_file)

            if os.path.exists(raster_incendio):
                os.remove(raster_incendio)

            ################## CREACIÓN DEL dNBR #######################
            # Función para leer una banda usando GDAL
            def leer_banda(ruta):
                dataset = gdal.Open(ruta)
                if dataset is None:
                    raise Exception(f"No se pudo abrir el archivo {ruta}")

                banda = dataset.GetRasterBand(1)
                array = banda.ReadAsArray().astype(np.float32)
                return array, dataset

            print(f"Banda 8A pre: {banda_8A_pre}")
            print(f"Banda 12 pre: {banda_12_pre}")
            print(f"Banda 8A post: {banda_8A_post}")
            print(f"Banda 12 post: {banda_12_post}")

            # Leer bandas pre incendio
            b8A_pre, dataset_b8A_pre = leer_banda(banda_8A_pre)
            b12_pre, dataset_b12_pre = leer_banda(banda_12_pre)

            # Leer bandas post incendio
            b8A_post, dataset_b8A_post = leer_banda(banda_8A_post)
            b12_post, dataset_b12_post = leer_banda(banda_12_post)

            # Calcular NBR
            def calcular_nbr(b8A, b12):
                nbr = (b8A - b12) / (b8A + b12)
                return nbr

            nbr_pre = calcular_nbr(b8A_pre, b12_pre)
            nbr_post = calcular_nbr(b8A_post, b12_post)

            # Calcular dNBR
            dnbr = nbr_pre - nbr_post

            # Guardar resultado en un archivo TIFF
            def guardar_raster(ruta, array, referencia):
                [cols, rows] = array.shape
                driver = gdal.GetDriverByName('GTiff')
                out_raster = driver.Create(ruta, rows, cols, 1, gdal.GDT_Float32)
                out_raster.SetGeoTransform(referencia.GetGeoTransform())
                out_raster.SetProjection(referencia.GetProjection())
                outband = out_raster.GetRasterBand(1)
                outband.WriteArray(array)
                outband.FlushCache()

            # Referencia para la geotransformación y proyección
            referencia = gdal.Open(banda_8A_pre)

            # Guardar NBR y dNBR
            guardar_raster(salida_nbr_pre, nbr_pre, referencia)
            guardar_raster(salida_nbr_post, nbr_post, referencia)
            guardar_raster(salida_dnbr, dnbr, referencia)

            ################# MODIFICACIONES AL dNBR ########################

            # Leer mascaras de nubes pre y post incendio
            nubes_pre, dataset_nubes_pre = leer_banda(nubes_pre)
            nubes_post, dataset_nubes_post = leer_banda(nubes_post)

            # Aplicar filtro a las mascaras
            mascara_pre = np.where(nubes_pre >= 10, 1, 0)
            mascara_post = np.where(nubes_post >= 10, 1, 0)

            # Guardar las mascaras pre y post incendio
            guardar_raster(PRE_nubes, mascara_pre, referencia)
            guardar_raster(POST_nubes, mascara_post, referencia)

            # Sumar las imágenes filtradas
            nubes_suma = np.maximum(mascara_pre, mascara_post)

            # Guardar imagen de suma en archivo TIFF
            guardar_raster(mascara_nubes, nubes_suma, referencia)

            ############################################################################

            # Calcular NDWI
            def calcular_ndwi(b3, b8A):
                ndwi = (b3 - b8A) / (b3 + b8A)
                return ndwi

            # Leer bandas pre incendio
            b8A_pre, dataset_b8A_pre = leer_banda(banda_8A_pre)
            b3_pre, dataset_b3_pre = leer_banda(banda3_pre)

            # Leer bandas post incendio
            b8A_post, dataset_b8A_post = leer_banda(banda_8A_post)
            b3_post, dataset_b3_post = leer_banda(banda3_post)

            ndwi_pre = calcular_ndwi(b3_pre, b8A_pre)
            ndwi_post = calcular_ndwi(b3_post, b8A_post)

            # Aplicar filtro a las imágenes de NDWI
            ndwi_pre_filtrado = np.where(ndwi_pre >= 0, 1, 0)
            ndwi_post_filtrado = np.where(ndwi_post >= 0, 1, 0)

            # Sumar las imágenes filtradas
            ndwi_suma = np.maximum(ndwi_pre_filtrado, ndwi_post_filtrado)

            # Guardar la máscara de agua en un archivo TIFF
            guardar_raster(mascara_agua, ndwi_suma, referencia)

            # Combinar las máscaras de nubes y agua
            def combinar_mascaras(mascara_nubes_ruta, mascara_agua_ruta, salida):
                nubes_array, nubes_ds = leer_banda(mascara_nubes_ruta)
                agua_array, agua_ds = leer_banda(mascara_agua_ruta)

                if nubes_array is None or agua_array is None:
                    self.iface.messageBar().pushMessage(f"Error al leer una o más máscaras: {mascara_nubes_ruta}, {mascara_agua_ruta}",
                        level=Qgis.Success, duration=3)
                    return

                mascara_combinada = np.maximum(nubes_array, agua_array)
                # mascara_combinada = np.where((nubes_array == 1) | (agua_array == 1), 1, 0)

                # Guardar la máscara combinada en un archivo TIFF
                guardar_raster(salida, mascara_combinada, nubes_ds)
                self.iface.messageBar().pushMessage(f"Máscara combinada de nubes y agua creada con éxito.",
                        level=Qgis.Success, duration=3)

            # Crear máscara combinada de nubes y agua
            combinar_mascaras(mascara_nubes, mascara_agua, mascara_nubes_agua)

            ############################################################

            # Aplicar máscara de nubes y agua al dNBR
            def aplicar_mascara(dnbr_ruta, mascara_ruta, salida):
                dnbr_array, dnbr_ds = leer_banda(dnbr_ruta)
                mascara_array, _ = leer_banda(mascara_ruta)

                if dnbr_array is None or mascara_array is None:
                    self.iface.messageBar().pushMessage(f"Error al leer dNBR o máscara: {dnbr_ruta}, {mascara_ruta}",
                        level=Qgis.Success, duration=3)
                    return

                # Aplicar la máscara
                dnbr_mascara_aplicada = np.where(mascara_array == 0, dnbr_array, -9999)

                # Guardar el resultado en un archivo TIFF
                guardar_raster(salida, dnbr_mascara_aplicada, dnbr_ds)
                self.iface.messageBar().pushMessage(f"Máscara de nubes y agua aplicada al dNBR con éxito.",
                        level=Qgis.Success, duration=3)

            # Aplicar máscara de nubes y agua al dNBR
            aplicar_mascara(salida_dnbr, mascara_nubes_agua, dNBR_filtrado)

            ############################################################

            # Aplicar umbral al dNBR filtrado
            def aplicar_umbral(dnbr_ruta, salida, umbral=0.1):
                dnbr_array, dnbr_ds = leer_banda(dnbr_ruta)

                if dnbr_array is None:
                    self.iface.messageBar().pushMessage(f"Error al leer el dNBR filtrado: {dnbr_ruta}",
                        level=Qgis.Success, duration=3)
                    return

                # Aplicar el umbral
                dnbr_umbral_aplicado = np.where(dnbr_array > umbral, dnbr_array, -9999)

                # Guardar el resultado en un archivo TIFF
                guardar_raster(salida, dnbr_umbral_aplicado, dnbr_ds)
                self.iface.messageBar().pushMessage(f"Umbral aplicado al dNBR con éxito.",
                        level=Qgis.Success, duration=3)

            # Aplicar umbral al dNBR filtrado
            aplicar_umbral(dNBR_filtrado, dNBR_filtrado_umbral)

            ############################### CREAR BUFFER #############################

            # Cargar la imagen dNBR
            dNBR_layer = QgsRasterLayer(dNBR_filtrado_umbral, 'dNBR_filtrado_umbral')
            if not dNBR_layer.isValid():
                 raise Exception('Error: la capa dNBR no es válida')

            # Cargar el punto central
            point_layer = QgsVectorLayer(punto, 'Center Point', 'ogr')
            if not point_layer.isValid():
                raise Exception('Error: la capa de puntos no es válida')

            # Obtener el punto central
            center_point = None
            for feature in point_layer.getFeatures():
                center_point = feature.geometry().asPoint()
                break  # Solo esperamos un punto central

            if center_point is None:
                raise Exception('Error: no se encontró ningún punto en la capa de puntos.')

            # Transformar el punto al CRS de la capa dNBR si es necesario
            transform = QgsCoordinateTransform(point_layer.crs(), dNBR_layer.crs(), QgsProject.instance())
            center_point = transform.transform(center_point)

            # Obtener el CRS de proyecto
            project_crs = QgsProject.instance().crs().authid()

            # Crear una nueva capa temporal para los buffers
            buffer_layer = QgsVectorLayer('Polygon?crs=' + project_crs, 'Buffers', 'memory')
            buffer_provider = buffer_layer.dataProvider()
            buffer_provider.addAttributes([QgsField('id', QVariant.Int)])
            buffer_layer.updateFields()

            # Calcular el área quemada en hectáreas (consideramos el valor dNBR >= 0.1 como quemado)
            burned_area_result = processing.run("gdal:rastercalculator", {
                'INPUT_A': dNBR_filtrado_umbral,
                'BAND_A': 1,
                'FORMULA': 'A >= 0.27',
                'NO_DATA': -9999,
                'RTYPE': 5,  # Byte
                'OPTIONS': '',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })

            burned_area_layer = QgsRasterLayer(burned_area_result['OUTPUT'], 'Burned Area')
            if not burned_area_layer.isValid():
                raise Exception('Error: la capa de área quemada no es válida')

            # Convertir el raster de área quemada a vector
            burned_area_vector = processing.run("gdal:polygonize", {
                'INPUT': burned_area_result['OUTPUT'],
                'BAND': 1,
                'FIELD': 'DN',
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })

            burned_area_vector_layer = QgsVectorLayer(burned_area_vector['OUTPUT'], 'Burned Area Vector', 'ogr')
            if not burned_area_vector_layer.isValid():
                raise Exception('Error: la capa vectorial de área quemada no es válida')

            # Calcular el área total en hectáreas
            total_burned_area_ha = 0
            for feature in burned_area_vector_layer.getFeatures():
                if feature['DN'] == 1:  # Suponemos que el valor de píxel quemado es 1
                    geom = feature.geometry()
                    area_ha = geom.area() / 10000  # convertir de m² a ha
                    total_burned_area_ha += area_ha

            self.iface.messageBar().pushMessage(f"Área total quemada: {total_burned_area_ha:.2f} ha",
                        level=Qgis.Success, duration=3)

            #Hay que saber adaptar la longitud de los buffer
            buffer_distance = 1000  # 1 km inicial
            buffer_increment = 2000  # Incremento de 2 km
            buffer_id = 1
            covered_area = False

            while not covered_area:
                # Crear un buffer
                buffer_geom = QgsGeometry.fromPointXY(QgsPointXY(center_point)).buffer(buffer_distance, 50)

                # Crear una característica para el buffer
                buffer_feature = QgsFeature()
                buffer_feature.setGeometry(buffer_geom)
                buffer_feature.setAttributes([buffer_id])
                buffer_provider.addFeatures([buffer_feature])
                buffer_layer.updateExtents()

                # Verificar el área del buffer en hectáreas
                buffer_area_ha = buffer_geom.area() / 10000  # Convertir de m² a ha

                self.iface.messageBar().pushMessage(f"Área del buffer actual: {buffer_area_ha:.2f} ha",
                        level=Qgis.Success, duration=3)

                # Si el área del buffer es mayor o igual al área quemada, detener
                if buffer_area_ha >= total_burned_area_ha:
                    covered_area = True
                else:
                    buffer_distance += buffer_increment
                    buffer_id += 1
                    buffer_layer.dataProvider().deleteFeatures([f.id() for f in buffer_layer.getFeatures()])

            # Guardar la última capa de buffer como shapefile
            _writer = QgsVectorFileWriter.writeAsVectorFormat(buffer_layer, buffer_incendio, 'utf-8', buffer_layer.crs(), 'ESRI Shapefile')
            if _writer == QgsVectorFileWriter.NoError:
                self.iface.messageBar().pushMessage(f"Se ha guardado la zona de influencia final en: {buffer_incendio}",
                        level=Qgis.Success, duration=3)

            # Guardar la imagen dNBR recortada final usando el último buffer
            processing.run("gdal:cliprasterbymasklayer", {
                'INPUT': dNBR_filtrado_umbral,
                'MASK': buffer_layer,
                'SOURCE_CRS': dNBR_layer.crs().authid(),
                'TARGET_CRS': dNBR_layer.crs().authid(),
                'NODATA': None,
                'ALPHA_BAND': False,
                'CROP_TO_CUTLINE': True,
                'KEEP_RESOLUTION': True,
                'OPTIONS': '',
                'DATA_TYPE': 0,
                'OUTPUT': raster_incendio
            })

            #Añadimos la capa al proyecto
            final_raster_layer = QgsRasterLayer(raster_incendio, 'Quemado')

            ############################## RASTER2SHP ###############################

            # Obtener la geometría del punto central
            central_feature = next(point_layer.getFeatures())
            central_point = central_feature.geometry().asPoint()

            # Obtener el valor del dNBR en el punto central
            ident = final_raster_layer.dataProvider().identify(central_point, QgsRaster.IdentifyFormatValue)
            if ident.isValid():
                central_value = ident.results()[1]
                self.iface.messageBar().pushMessage(f"Valor dNBR en el punto central: {central_value}",
                        level=Qgis.Success, duration=3)

            # Definir la fórmula para la calculadora raster
            formula = (
                '(A >= 0.1) * (A < 0.27) * 1 + '
                '(A >= 0.27) * (A < 0.44) * 2 + '
                '(A >= 0.44) * (A < 0.66) * 3 + '
                '(A >= 0.66) * 4'
            )

            # Crear una capa raster donde los valores sean los rangos y el resto 0
            processing.run("gdal:rastercalculator", {
                'INPUT_A': final_raster_layer,
                'BAND_A': 1,
                'FORMULA': formula,
                'NO_DATA': 0,
                'RTYPE': 5,  # Float32
                'OUTPUT': sev_raster_path
            })

            # Cargar la capa raster generada
            sev_raster_layer = QgsRasterLayer(sev_raster_path, "sev_incendio")
            if not sev_raster_layer.isValid():
                self.iface.messageBar().pushMessage(f"El raster de severidad no es válido",
                        level=Qgis.Success, duration=3)

            processing.run("gdal:sieve", {
                'INPUT': sev_raster_path,
                'THRESHOLD': 5,  # Tamaño mínimo de los píxeles en las regiones a mantener
                'EIGHT_CONNECTEDNESS': True,
                'OUTPUT': sieved_raster_path
            })

            processing.run("gdal:polygonize", {
                'INPUT': sieved_raster_path,
                'BAND': 1,
                'FIELD': 'DN',
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'OUTPUT': output_polygon_path
            })

            # Cargar el shapefile de polígonos generado
            polygon_layer = QgsVectorLayer(output_polygon_path, "Incendio", "ogr")

            if not polygon_layer.isValid():
                self.iface.messageBar().pushMessage(f"La capa de polígonos no es válida",
                        level=Qgis.Success, duration=3)

            # Añadir los campos de hectáreas y severidad a la capa de polígonos
            dp = polygon_layer.dataProvider()
            caps = dp.capabilities()
            capstring = dp.capabilitiesString()

            res = False
            if caps&QgsVectorDataProvider.AddAttributes:
                res = dp.addAttributes([QgsField('Severidad',QVariant.String,len=20),QgsField('Hectareas',QVariant.Double)])

            polygon_layer.updateFields()

            # Definir la función para obtener el texto de severidad
            def obtener_texto_severidad(valor):
                if valor == 1:
                    return "Baja"
                elif valor == 2:
                    return "Moderada Baja"
                elif valor == 3:
                    return "Moderada Alta"
                elif valor == 4:
                    return "Alta"
                else:
                    return "Desconocida"

            # Obtener los índices de los campos recién añadidos
            index2 = polygon_layer.fields().indexFromName('Severidad')
            index3 = polygon_layer.fields().indexFromName('Hectareas')

            # Comenzar la edicion de la capa
            polygon_layer.startEditing()
            for feature in polygon_layer.getFeatures():
                # Calcular el área y convertirla en hectáreas
                area = feature.geometry().area()
                hectarea = area/10000
                polygon_layer.changeAttributeValue(feature.id(),index3,hectarea)

                # Obtener el valor de DN y calcular la severidad
                dn_value = feature["DN"]
                severidad_texto = obtener_texto_severidad(int(dn_value))
                polygon_layer.changeAttributeValue(feature.id(),index2,severidad_texto)
            polygon_layer.commitChanges()

            error, error_message = QgsVectorFileWriter.writeAsVectorFormat(polygon_layer, output_polygon_path, "UTF-8", polygon_layer.crs(), "ESRI Shapefile")

            #CAMBIAR LA SIMBOLOGÍA
            unique_values = polygon_layer.uniqueValues(index2) #va al campo y coge los valores únicos
            categories = [] #lista que se irá rellenando
            for unique_value in unique_values:
                polygon_layer_style = {}
                if unique_value == 'Alta':
                    polygon_layer_style['color']='255,0,0'

                elif unique_value == 'Moderada Alta':
                    polygon_layer_style['color']='255,128,0'

                elif unique_value == 'Moderada Baja':
                    polygon_layer_style['color']='255,255,0'

                elif unique_value == 'Baja':
                    polygon_layer_style['color']='124,252,0'

                else:
                    polygon_layer_style['color']='50,205,50'

                cat = QgsRendererCategory(unique_value, QgsFillSymbol.createSimple(polygon_layer_style),unique_value)
                categories.append(cat)

            renderer = QgsCategorizedSymbolRenderer('Severidad',categories)

            if renderer is not None:
                polygon_layer.setRenderer(renderer)
                polygon_layer.triggerRepaint()
                self.iface.messageBar().pushMessage("Éxito", "Simbología actualizada correctamente", level=Qgis.Info)

            else:
                self.iface.messageBar().pushMessage("Error", "No se pudo crear el renderer", level=Qgis.Critical)

            error, error_message = QgsVectorFileWriter.writeAsVectorFormat(polygon_layer, output_polygon_path, "UTF-8", polygon_layer.crs(), "ESRI Shapefile")
            if error != QgsVectorFileWriter.NoError:
                self.iface.messageBar().pushMessage("Error", f"No se pudo guardar la capa: {error_message}", level=Qgis.Critical)
            else:
                self.iface.messageBar().pushMessage("Éxito", "Capa guardada correctamente", level=Qgis.Info)

            ######################### GRAFICO #################################

            # Diccionario para almacenar la suma de hectáreas por severidad
            severidad_hectareas = {}

            # Índices de los campos
            index_sev = polygon_layer.fields().indexFromName('Severidad')
            index_hec = polygon_layer.fields().indexFromName('Hectareas')

            # Iteramos sobre los elementos de la capa para sumar las hectáreas por severidad
            for feature in polygon_layer.getFeatures():
                severidad = feature[index_sev]
                hectareas = feature[index_hec]
                if severidad in severidad_hectareas:
                    severidad_hectareas[severidad] += hectareas
                else:
                    severidad_hectareas[severidad] = hectareas

            # Datos para el gráfico
            x = list(severidad_hectareas.keys())
            y = list(severidad_hectareas.values())

            # Crear el gráfico de barras
            plt.figure()

            for i, severidad in enumerate(x):
                if severidad == 'Baja':
                    color = 'green'
                elif severidad == 'Moderada Baja':
                    color = 'yellow'
                elif severidad == 'Moderada Alta':
                    color = 'orange'
                elif severidad == 'Alta':
                    color = 'red'
                else:
                    color = 'blue'  # Si hay alguna severidad no especificada, usar color azul

                plt.bar(severidad, y[i], color=color)

            plt.title('Hectáreas totales clasificadas por severidad del incendio')
            plt.xlabel('Severidad')
            plt.ylabel('Hectáreas')
            plt.grid(True)

            # Guardar el gráfico como una imagen
            plt.savefig(graf)
            plt.close()

            #Para abrirlo directamente en qgis
            # Crear una capa raster desde la imagen del gráfico
            img_raster = QgsRasterLayer(graf, 'Gráfico de Severidad')

            ########################### FIN #################################
            output_polygon_path = self.output_polygon_path
            graf = self.graf

            polygon_layer = QgsVectorLayer(output_polygon_path,"Incendio Clasificado","ogr")
            img_raster = QgsRasterLayer(graf,"Gráfico de Severidad","gdal")

            QgsProject.instance().addMapLayer(polygon_layer)
            QgsProject.instance().addMapLayer(img_raster)

            self.iface.messageBar().pushMessage(
                "Success", f"Capas añadidas al proyecto", level=Qgis.Success, duration=3)

            pass