# -*- coding: utf-8 -*-
import os
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
from .algorithm import NetworkFeatureAugmentation


class NetworkAugmentationProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(NetworkFeatureAugmentation())

    def id(self):
        return 'networkaugmentation'

    def name(self):
        return 'Network Augmentation'

    def longName(self):
        return 'Network-Based Hierarchical Feature Augmentation'

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), 'icon.svg'))
