"""Чистая доменная статистика повторов, контрастов и спектров."""

from .aba import analyze_aba
from .models import (
    AbaUnit,
    AnalysisContext,
    ContrastRefusal,
    DescriptiveEffect,
    Estimator,
    FeaturePair,
    FeatureValue,
    InferentialEffect,
    PairedUnit,
    PairingError,
    ProtocolInferenceDeclaration,
    QualifiedWithinRunContrast,
    RawRepeatedSamplesError,
    SpectrumPair,
    paired_unit_from_aggregates,
)
from .paired import estimate_paired, linear_ratio_to_db
from .protocols import PROTOCOL_TO_ESTIMATOR, EstimatorRejectedError, authorize_estimator
from .spectra import analyze_spectra, benjamini_hochberg
from .tables import analyze_feature_table

__all__ = [
    "PROTOCOL_TO_ESTIMATOR",
    "AbaUnit",
    "AnalysisContext",
    "ContrastRefusal",
    "DescriptiveEffect",
    "Estimator",
    "EstimatorRejectedError",
    "FeaturePair",
    "FeatureValue",
    "InferentialEffect",
    "PairedUnit",
    "PairingError",
    "ProtocolInferenceDeclaration",
    "QualifiedWithinRunContrast",
    "RawRepeatedSamplesError",
    "SpectrumPair",
    "analyze_aba",
    "analyze_feature_table",
    "analyze_spectra",
    "authorize_estimator",
    "benjamini_hochberg",
    "estimate_paired",
    "linear_ratio_to_db",
    "paired_unit_from_aggregates",
]
