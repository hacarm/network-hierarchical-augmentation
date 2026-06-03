# -*- coding: utf-8 -*-
import os
from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .provider import NetworkAugmentationProvider


class NetworkAugmentationPlugin:
    """Main plugin class — registers the Processing provider and the dock panel."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.panel = None
        self.toggle_action = None

    # ------------------------------------------------------------------
    def initProcessing(self):
        self.provider = NetworkAugmentationProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

        # Create the dock panel
        from .panel import NetworkAugmentationPanel
        self.panel = NetworkAugmentationPanel(self.iface)
        self.iface.addDockWidget(0x2, self.panel)   # 0x2 = Qt.LeftDockWidgetArea
        self.panel.hide()

        # Toolbar / menu action to toggle the panel
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.svg')
        self.toggle_action = QAction(
            QIcon(icon_path),
            'Network Hierarchical Augmentation',
            self.iface.mainWindow(),
        )
        self.toggle_action.setCheckable(True)
        self.toggle_action.setChecked(False)
        self.toggle_action.setToolTip('Open the Network Hierarchical Augmentation panel')
        self.toggle_action.triggered.connect(self._toggle_panel)
        self.panel.visibilityChanged.connect(self.toggle_action.setChecked)

        self.iface.addToolBarIcon(self.toggle_action)
        self.iface.addPluginToMenu('&Network Augmentation', self.toggle_action)

    # ------------------------------------------------------------------
    def _toggle_panel(self, checked):
        if checked:
            self.panel.show()
            self.panel.raise_()
        else:
            self.panel.hide()

    # ------------------------------------------------------------------
    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
        if self.panel:
            self.iface.removeDockWidget(self.panel)
            self.panel.deleteLater()
            self.panel = None
        if self.toggle_action:
            self.iface.removeToolBarIcon(self.toggle_action)
            self.iface.removePluginMenu('&Network Augmentation', self.toggle_action)
            self.toggle_action.deleteLater()
            self.toggle_action = None
