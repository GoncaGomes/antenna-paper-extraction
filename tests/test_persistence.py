from pathlib import Path

import pytest

from antenna_paper_extraction.persistence import read_json, write_json


def test_write_and_read_json(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "manifest.json"
    expected = {
        "name": "antena de medição",
        "value": 123,
    }

    write_json(output_path, expected)

    assert output_path.exists()
    assert read_json(output_path) == expected


def test_write_json_leaves_no_temporary_file(tmp_path: Path) -> None:
    output_path = tmp_path / "manifest.json"

    write_json(output_path, {"status": "complete"})

    temporary_files = list(tmp_path.glob(f".{output_path.name}.*.tmp"))
    assert temporary_files == []


def test_read_json_rejects_non_object_root(tmp_path: Path) -> None:
    input_path = tmp_path / "list.json"
    input_path.write_text('["item"]', encoding="utf-8")

    with pytest.raises(TypeError, match="JSON root must be an object"):
        read_json(input_path)