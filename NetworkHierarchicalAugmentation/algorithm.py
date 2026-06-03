# -*- coding: utf-8 -*-
"""
Network-Based Hierarchical Feature Augmentation Algorithm  (v2)

New in v2:
  • Per-field neighbourhood depth (N) — each field can have a different max level.
  • Per-field aggregation method — mean | sum | min | max | median | std | count.
  • Global defaults (MAX_N, AGG_METHOD) used when no per-field override is given.
  • Optional PER_FIELD_CONFIG advanced string for programmatic / panel use:
      Format:  fieldname:N:method,fieldname2:N2:method2, …
      Example: length:10:mean,sinuosity:5:max

BFS correctness fixes (from v1):
  • network_ended flag prevents BFS restart after branch exhaustion.
  • Level-major column index matches schema definition order.

Reference:
  Hacar, M.; Altafini, D.; Cutini, V. (2024).
  Network-Based Hierarchical Feature Augmentation for Predicting Road Classes in OSM.
  ISPRS Int. J. Geo-Inf., 13(12), 456.
  https://doi.org/10.3390/ijgi13120456
"""

import collections
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterString,
    QgsProcessingParameterFeatureSink,
    QgsFeature,
    QgsField,
    QgsFeatureSink,
)
from qgis.PyQt.QtCore import QCoreApplication, QVariant


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _mean(v):   return sum(v) / len(v)
def _median(v): return sorted(v)[len(v) // 2]
def _std(v):
    if len(v) < 2:
        return 0.0
    m = sum(v) / len(v)
    return (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5

AGG_LABELS = ['mean', 'sum', 'min', 'max', 'median', 'std']

AGG_FUNCTIONS = {
    'mean':   _mean,
    'sum':    sum,
    'min':    min,
    'max':    max,
    'median': _median,
    'std':    _std,
}


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

class NetworkFeatureAugmentation(QgsProcessingAlgorithm):

    INPUT            = 'INPUT'
    FIELDS           = 'FIELDS'
    MAX_N            = 'MAX_N'
    AGG_METHOD       = 'AGG_METHOD'
    PER_FIELD_CONFIG = 'PER_FIELD_CONFIG'
    OUTPUT           = 'OUTPUT'
    PRECISION        = 5

    # ------------------------------------------------------------------
    # Boilerplate
    # ------------------------------------------------------------------

    def tr(self, s):
        return QCoreApplication.translate('NetworkFeatureAugmentation', s)

    def name(self):
        return 'network_hierarchical_augmentation'

    def displayName(self):
        return self.tr('Network-Based Hierarchical Feature Augmentation')

    def group(self):
        return self.tr('Network Analysis')

    def groupId(self):
        return 'networkanalysis'

    def shortHelpString(self):
        return self.tr(
            '<p>Augments each road segment with aggregated attribute values from BFS '
            'neighbours at hierarchical levels <b>L1 … LN</b>.</p>'
            '<p><b>Per-field settings</b> (via the panel or PER_FIELD_CONFIG string):<br>'
            '&nbsp;&nbsp;<tt>fieldname:N:method, …</tt><br>'
            'e.g. <tt>length:10:mean,sinuosity:5:max</tt></p>'
            '<p>Available methods: <b>mean, sum, min, max, median, std</b></p>'
            '<p><b>L1_Count … LN_Count</b> columns are always added automatically, '
            'recording the number of BFS neighbours at each level '
            '(N = the maximum depth across all selected fields).</p>'
            '<p>Columns that exceed the actual network depth are left <b>NULL</b>.</p>'
            '<p>Reference: Hacar et al. (2024), ISPRS IJGI 13(12), 456. '
            '<a href="https://doi.org/10.3390/ijgi13120456">doi:10.3390/ijgi13120456</a></p>'
        )

    def createInstance(self):
        return NetworkFeatureAugmentation()

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                self.tr('Input Road Network'),
                [QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELDS,
                self.tr('Fields to Augment'),
                parentLayerParameterName=self.INPUT,
                allowMultiple=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_N,
                self.tr('Default Neighbourhood Level (N)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=3,
                minValue=1,
                maxValue=100,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.AGG_METHOD,
                self.tr('Default Aggregation Method'),
                options=AGG_LABELS,
                defaultValue=0,   # mean
            )
        )

        # Advanced: per-field overrides used by the panel and power users
        pfc = QgsProcessingParameterString(
            self.PER_FIELD_CONFIG,
            self.tr('Per-Field Config (advanced) — format: field:N:method, …'),
            optional=True,
            defaultValue='',
        )
        pfc.setFlags(
            pfc.flags() | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(pfc)

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Augmented Layer'),
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_field_config(config_str, target_fields, default_n, default_method):
        """
        Parse PER_FIELD_CONFIG string into {field_name: (max_n, method)}.
        Any field not mentioned in config_str receives the global defaults.
        """
        overrides = {}
        if config_str and config_str.strip():
            for part in config_str.split(','):
                tokens = part.strip().split(':')
                if len(tokens) == 3:
                    fname  = tokens[0].strip()
                    method = tokens[2].strip().lower()
                    try:
                        n = max(1, int(tokens[1].strip()))
                        if method not in AGG_FUNCTIONS:
                            method = default_method
                        overrides[fname] = (n, method)
                    except ValueError:
                        pass
        return {
            f: overrides.get(f, (default_n, default_method))
            for f in target_fields
        }

    # ------------------------------------------------------------------
    # Main processing
    # ------------------------------------------------------------------

    def processAlgorithm(self, parameters, context, feedback):

        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            return {}

        target_fields    = self.parameterAsFields(parameters, self.FIELDS, context)
        default_n        = self.parameterAsInt(parameters, self.MAX_N, context)
        default_method   = AGG_LABELS[self.parameterAsEnum(parameters, self.AGG_METHOD, context)]
        config_str       = self.parameterAsString(parameters, self.PER_FIELD_CONFIG, context)

        if not target_fields:
            feedback.reportError('No fields selected.', fatalError=True)
            return {}

        # Resolve per-field (N, method)
        field_config = self._parse_field_config(
            config_str, target_fields, default_n, default_method
        )

        feedback.pushInfo('Field configuration:')
        for fname, (fn, fm) in field_config.items():
            feedback.pushInfo(f'  {fname}  →  N={fn}, method={fm}')

        # ── 1. Build output schema (field-major order) ─────────────────
        # Each field occupies a consecutive block: L1_f, L2_f, …, LN_f
        output_fields = source.fields()
        col_map   = {}   # (field_name, level_n) → index in augmented_values
        col_index = 0
        for fname in target_fields:
            fn, _ = field_config[fname]
            for n in range(1, fn + 1):
                output_fields.append(QgsField(f'L{n}_{fname}', QVariant.Double))
                col_map[(fname, n)] = col_index
                col_index += 1

        total_aug_cols = col_index
        max_bfs_n      = max(cfg[0] for cfg in field_config.values())

        # Auto count columns: L1_Count … Lmax_Count (one per BFS level)
        # col_map key: ('__count__', n)
        for n in range(1, max_bfs_n + 1):
            output_fields.append(QgsField(f'L{n}_Count', QVariant.Int))
            col_map[('__count__', n)] = col_index
            col_index += 1

        total_aug_cols = col_index   # updated to include count columns

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            output_fields, source.wkbType(), source.sourceCrs(),
        )

        feedback.pushInfo(
            f'Schema: {len(target_fields)} field(s), '
            f'{total_aug_cols} new column(s), '
            f'max BFS depth = {max_bfs_n}.'
        )

        # ── 2. Load features & build adjacency ────────────────────────
        feedback.pushInfo('Loading features and building network topology …')
        all_features = {f.id(): f for f in source.getFeatures()}
        adjacency    = collections.defaultdict(set)
        node_map     = collections.defaultdict(list)

        for fid, feat in all_features.items():
            geom = feat.geometry()
            if geom.isNull():
                continue
            line = (
                geom.asPolyline()
                if not geom.isMultipart()
                else geom.asMultiPolyline()[0]
            )
            if not line:
                continue
            p_s = (round(line[0].x(),  self.PRECISION), round(line[0].y(),  self.PRECISION))
            p_e = (round(line[-1].x(), self.PRECISION), round(line[-1].y(), self.PRECISION))
            node_map[p_s].append(fid)
            node_map[p_e].append(fid)

        for fids in node_map.values():
            for f1 in fids:
                for f2 in fids:
                    if f1 != f2:
                        adjacency[f1].add(f2)

        feedback.pushInfo(
            f'Topology built: {len(all_features)} features, '
            f'{sum(len(v) for v in adjacency.values()) // 2} edge pairs.'
        )

        # ── 3. BFS augmentation per feature ───────────────────────────
        total_count   = source.featureCount()
        progress_step = 100.0 / total_count if total_count > 0 else 1

        for i, (fid, feat) in enumerate(all_features.items()):
            if feedback.isCanceled():
                break

            out_feat = QgsFeature(output_fields)
            out_feat.setGeometry(feat.geometry())

            # Pre-fill all augmented slots as NULL
            augmented_values = [None] * total_aug_cols

            visited            = {fid}
            current_layer_fids = {fid}
            network_ended      = False   # explicit termination guard

            for n in range(1, max_bfs_n + 1):

                if network_ended:
                    break   # branch exhausted — remaining slots stay NULL

                # Expand BFS: unvisited neighbours of current frontier
                next_layer_fids = set()
                for cfid in current_layer_fids:
                    for nfid in adjacency[cfid]:
                        if nfid not in visited:
                            next_layer_fids.add(nfid)

                # No new neighbours → network exhausted, stop immediately
                if not next_layer_fids:
                    network_ended = True
                    break

                # Aggregate per field (only for fields that include this level)
                for fname, (fn, fm) in field_config.items():
                    if n > fn:
                        continue   # this field doesn't request this level

                    vals = [
                        all_features[nf][fname]
                        for nf in next_layer_fids
                        if all_features[nf][fname] is not None
                        and isinstance(all_features[nf][fname], (int, float))
                    ]
                    if vals:
                        augmented_values[col_map[(fname, n)]] = AGG_FUNCTIONS[fm](vals)

                # Auto count: number of BFS neighbours at this level
                augmented_values[col_map[('__count__', n)]] = len(next_layer_fids)

                # Advance frontier — always forward, never back
                visited.update(next_layer_fids)
                current_layer_fids = next_layer_fids

            final_attrs = feat.attributes()
            final_attrs.extend(augmented_values)
            out_feat.setAttributes(final_attrs)
            sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

            if i % 100 == 0:
                feedback.setProgress(int(i * progress_step))

        return {self.OUTPUT: dest_id}
