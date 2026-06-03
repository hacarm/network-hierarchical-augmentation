# -*- coding: utf-8 -*-
"""
Network-Based Hierarchical Feature Augmentation — QGIS Plugin v2
Reference: Hacar, Altafini & Cutini (2024). ISPRS IJGI 13(12), 456.
           https://doi.org/10.3390/ijgi13120456
"""


def classFactory(iface):
    from .plugin import NetworkAugmentationPlugin
    return NetworkAugmentationPlugin(iface)
