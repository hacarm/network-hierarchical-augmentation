# -*- coding: utf-8 -*-
"""
Dock panel for Network-Based Hierarchical Feature Augmentation.

Each numeric field in the selected layer is listed in a table.
The user can:
  • Check/uncheck individual fields.
  • Set per-field neighbourhood depth N (QSpinBox).
  • Set per-field aggregation method (QComboBox).
  • Name the output layer.
  • Run the algorithm and track progress inline.
"""

import os

from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QSpinBox, QComboBox, QProgressBar, QTextEdit, QLineEdit,
    QHeaderView, QGroupBox, QSizePolicy, QAbstractItemView,
    QFrame, QSplitter,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QFont, QIcon

from qgis.core import (
    QgsProject,
    QgsMapLayerProxyModel,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputLayerDefinition,
    QgsProcessing,
    QgsWkbTypes,
)
from qgis.gui import QgsMapLayerComboBox

import processing

from .algorithm import AGG_LABELS

# Numeric QVariant types that can be meaningfully aggregated
NUMERIC_VARIANT_TYPES = {
    QVariant.Int, QVariant.UInt,
    QVariant.LongLong, QVariant.ULongLong,
    QVariant.Double,
}

COL_FIELD  = 0
COL_MAXN   = 1
COL_METHOD = 2


# ---------------------------------------------------------------------------
# Custom QgsProcessingFeedback that forwards messages to the panel log
# ---------------------------------------------------------------------------

class PanelFeedback(QgsProcessingFeedback):
    def __init__(self, log_fn, progress_fn):
        super().__init__()
        self._log      = log_fn
        self._progress = progress_fn
        self.progressChanged.connect(lambda p: self._progress(int(p)))

    def pushInfo(self, info):
        self._log(f'ℹ  {info}')

    def reportError(self, error, fatalError=False):
        self._log(f'✖  {error}')

    def pushWarning(self, warning):
        self._log(f'⚠  {warning}')


# ---------------------------------------------------------------------------
# Main dock widget
# ---------------------------------------------------------------------------

class NetworkAugmentationPanel(QDockWidget):

    ALG_ID = 'networkaugmentation:network_hierarchical_augmentation'

    def __init__(self, iface):
        super().__init__('Network Hierarchical Augmentation')
        self.iface = iface
        self.setObjectName('NetworkAugmentationPanel')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(340)

        self._build_ui()
        self._connect_signals()
        self._populate_table()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('panelRoot')
        outer = QVBoxLayout(root)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # ── Layer selector ────────────────────────────────────────────
        grp_input = QGroupBox('Input Layer')
        lay_input = QHBoxLayout(grp_input)
        lay_input.setContentsMargins(6, 4, 6, 4)
        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.layer_combo.setToolTip('Select a line vector layer')
        lay_input.addWidget(self.layer_combo)
        outer.addWidget(grp_input)

        # ── Field configuration table ─────────────────────────────────
        grp_fields = QGroupBox('Field Configuration')
        lay_fields = QVBoxLayout(grp_fields)
        lay_fields.setContentsMargins(6, 4, 6, 4)
        lay_fields.setSpacing(4)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Field', 'Max N', 'Aggregation'])
        self.table.horizontalHeader().setSectionResizeMode(COL_FIELD,  QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_MAXN,   QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_METHOD, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(140)
        lay_fields.addWidget(self.table)

        # Select-all / clear buttons
        btn_row = QHBoxLayout()
        self.btn_all   = QPushButton('☑  Select All')
        self.btn_none  = QPushButton('☐  Clear All')
        self.btn_all.setFixedHeight(24)
        self.btn_none.setFixedHeight(24)
        btn_row.addWidget(self.btn_all)
        btn_row.addWidget(self.btn_none)
        btn_row.addStretch()
        lay_fields.addLayout(btn_row)

        outer.addWidget(grp_fields)

        # ── Output ───────────────────────────────────────────────────
        grp_out = QGroupBox('Output')
        lay_out = QHBoxLayout(grp_out)
        lay_out.setContentsMargins(6, 4, 6, 4)
        lay_out.addWidget(QLabel('Layer name:'))
        self.output_name = QLineEdit('Augmented_Network')
        self.output_name.setToolTip(
            'Name for the output in-memory layer.\n'
            'The layer is added to the current QGIS project automatically.'
        )
        lay_out.addWidget(self.output_name)
        outer.addWidget(grp_out)

        # ── Run button + progress ─────────────────────────────────────
        self.run_btn = QPushButton('▶   Run Augmentation')
        self.run_btn.setFixedHeight(32)
        font = self.run_btn.font()
        font.setBold(True)
        self.run_btn.setFont(font)
        outer.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        outer.addWidget(self.progress_bar)

        # ── Log ───────────────────────────────────────────────────────
        grp_log = QGroupBox('Log')
        lay_log = QVBoxLayout(grp_log)
        lay_log.setContentsMargins(6, 4, 6, 4)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(80)
        self.log_box.setMaximumHeight(160)
        mono = QFont('Monospace')
        mono.setStyleHint(QFont.TypeWriter)
        mono.setPointSize(8)
        self.log_box.setFont(mono)
        lay_log.addWidget(self.log_box)

        btn_clear_log = QPushButton('Clear log')
        btn_clear_log.setFixedHeight(22)
        btn_clear_log.clicked.connect(self.log_box.clear)
        lay_log.addWidget(btn_clear_log)
        outer.addWidget(grp_log)

        outer.addStretch()
        self.setWidget(root)

    # --------------------------------------------------------- Signals ------

    def _connect_signals(self):
        self.layer_combo.layerChanged.connect(self._populate_table)
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._clear_all)
        self.run_btn.clicked.connect(self._run)

    # ---------------------------------------------------------- Table -------

    def _populate_table(self):
        """Fill the table with numeric fields of the currently selected layer."""
        self.table.setRowCount(0)
        layer = self.layer_combo.currentLayer()
        if layer is None:
            return

        for field in layer.fields():
            if field.type() not in NUMERIC_VARIANT_TYPES:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Col 0 — checkbox + field name
            item = QTableWidgetItem(field.name())
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Unchecked)
            item.setToolTip(field.name())
            self.table.setItem(row, COL_FIELD, item)

            # Col 1 — Max N spinbox
            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setValue(3)
            spin.setToolTip('Maximum neighbourhood depth for this field')
            spin.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row, COL_MAXN, spin)

            # Col 2 — Aggregation combobox
            combo = QComboBox()
            for method in AGG_LABELS:
                combo.addItem(method)
            combo.setCurrentIndex(0)   # mean
            combo.setToolTip(
                'mean   — average value\n'
                'sum    — total\n'
                'min    — smallest value\n'
                'max    — largest value\n'
                'median — middle value\n'
                'std    — standard deviation\n'
                '\nL1_Count … LN_Count columns are\n'
                'always generated automatically.'
            )
            self.table.setCellWidget(row, COL_METHOD, combo)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(COL_FIELD, QHeaderView.Stretch)

    def _select_all(self):
        for row in range(self.table.rowCount()):
            self.table.item(row, COL_FIELD).setCheckState(Qt.Checked)

    def _clear_all(self):
        for row in range(self.table.rowCount()):
            self.table.item(row, COL_FIELD).setCheckState(Qt.Unchecked)

    # ----------------------------------------------------------- Helpers ----

    def _get_checked_fields(self):
        """Return list of (field_name, max_n, method) for checked rows."""
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_FIELD)
            if item and item.checkState() == Qt.Checked:
                fname  = item.text()
                max_n  = self.table.cellWidget(row, COL_MAXN).value()
                method = self.table.cellWidget(row, COL_METHOD).currentText()
                result.append((fname, max_n, method))
        return result

    def _append_log(self, text):
        self.log_box.append(text)
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_progress(self, value):
        self.progress_bar.setValue(value)

    # ---------------------------------------------------------------- Run ---

    def _run(self):
        from qgis.PyQt.QtWidgets import QApplication

        layer = self.layer_combo.currentLayer()
        if layer is None:
            self._append_log('✖  No layer selected.')
            return

        checked = self._get_checked_fields()
        if not checked:
            self._append_log('✖  No fields checked — please check at least one field.')
            return

        field_names = [f[0] for f in checked]

        # Build PER_FIELD_CONFIG string: "field:N:method,…"
        per_field_config = ','.join(f'{f}:{n}:{m}' for f, n, m in checked)

        output_name = self.output_name.text().strip() or 'Augmented_Network'

        # Disable button during run
        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_box.clear()
        self._append_log(f'▶  Starting augmentation on layer: {layer.name()}')
        self._append_log(f'   Fields: {", ".join(field_names)}')
        self._append_log(f'   Config: {per_field_config}')
        QApplication.processEvents()

        try:
            context  = QgsProcessingContext()
            feedback = PanelFeedback(
                log_fn=self._append_log,
                progress_fn=lambda p: (
                    self._set_progress(p),
                    QApplication.processEvents(),
                ),
            )

            params = {
                'INPUT':            layer,
                'FIELDS':           field_names,
                'MAX_N':            3,          # fallback (overridden by PER_FIELD_CONFIG)
                'AGG_METHOD':       0,          # fallback (overridden by PER_FIELD_CONFIG)
                'PER_FIELD_CONFIG': per_field_config,
                'OUTPUT':           'TEMPORARY_OUTPUT',
            }

            result = processing.run(self.ALG_ID, params, context=context, feedback=feedback)

            # With TEMPORARY_OUTPUT, result['OUTPUT'] is already the QgsVectorLayer.
            # context.getMapLayer() expects a string ID — never pass the layer object to it.
            output_layer = result['OUTPUT']
            if isinstance(output_layer, str):
                # Fallback: result is a layer ID string — retrieve from context
                output_layer = context.getMapLayer(output_layer)

            if output_layer is not None and output_layer.isValid():
                output_layer.setName(output_name)
                QgsProject.instance().addMapLayer(output_layer)
                self._append_log(f'✔  Done! Layer "{output_name}" added to the project.')
            else:
                self._append_log('⚠  Run completed but output layer could not be loaded.')

        except Exception as exc:
            self._append_log(f'✖  Error: {exc}')

        finally:
            self.progress_bar.setValue(100)
            self.run_btn.setEnabled(True)
            QApplication.processEvents()
