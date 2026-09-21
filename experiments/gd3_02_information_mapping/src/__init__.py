"""GĐ3-02 - Information Extraction + AI Schema Mapping."""

from .information_extractor import InformationExtractor, extract_information
from .output_formatter import OutputFormatter, format_for_backend, format_for_ui
from .pipeline import InformationExtractionPipeline, run_pipeline
from .schema_mapper import SchemaMapper, map_schema

__version__ = "2.1.0-fixed"

__all__ = [
    "InformationExtractor",
    "extract_information",
    "SchemaMapper",
    "map_schema",
    "InformationExtractionPipeline",
    "run_pipeline",
    "OutputFormatter",
    "format_for_backend",
    "format_for_ui",
]
