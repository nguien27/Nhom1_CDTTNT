"""Compatibility wrapper cho API GĐ3-02 cũ.

Mapper chính nằm trong ``gd2_02_mapping_adapter.py`` và dùng GĐ2-02 làm nền tảng.
"""

from typing import List

from .gd2_02_mapping_adapter import GD202SchemaMappingAdapter
from .models import ExtractedField


class SchemaMapper:
    def __init__(self):
        self.adapter = GD202SchemaMappingAdapter()

    def map_headers(self, headers: List[str]):
        return self.adapter.map_headers(headers)

    def map_extracted_fields(self, fields: List[ExtractedField]):
        return self.adapter.map_extracted_fields(fields)


def map_schema(source_fields, source_type: str = "header"):
    mapper = SchemaMapper()
    if source_type == "header":
        return mapper.map_headers(source_fields)
    return mapper.map_extracted_fields(source_fields)
