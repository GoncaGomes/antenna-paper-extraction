import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfWriter

from antenna_paper_extraction.pages import render_pdf_pages
from antenna_paper_extraction.runs import create_run


def write_pdf(path: Path, page_sizes: list[tuple[int, int]]) -> None:
    writer = PdfWriter()
    for width, height in page_sizes:
        writer.add_blank_page(width=width, height=height)
    with path.open("wb") as file:
        writer.write(file)


def write_encrypted_pdf(path: Path, password: str) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt(password)
    with path.open("wb") as file:
        writer.write(file)


def test_render_pdf_pages_renders_one_page(tmp_path: Path) -> None:
    input_pdf = tmp_path / "paper with spaces.pdf"
    write_pdf(input_pdf, [(72, 72)])
    run_dir = create_run(input_pdf, tmp_path / "runs")

    manifest = render_pdf_pages(run_dir)
    page = manifest.pages[0]
    assert manifest.page_count == 1
    assert page.page_number == 1
    assert page.asset_id == "page_0001"
    assert page.relative_path == "pages/page_0001.png"
    assert (run_dir / page.relative_path).is_file()
    assert (run_dir / "pages.json").is_file()


def test_render_pdf_pages_preserves_source_order(tmp_path: Path) -> None:
    input_pdf = tmp_path / "source.pdf"
    write_pdf(input_pdf, [(72, 72), (144, 72), (72, 144)])
    run_dir = create_run(input_pdf, tmp_path / "runs")

    manifest = render_pdf_pages(run_dir)

    assert manifest.page_count == 3
    assert [page.page_number for page in manifest.pages] == [1, 2, 3]
    assert [page.asset_id for page in manifest.pages] == [
        "page_0001",
        "page_0002",
        "page_0003",
    ]
    assert [page.relative_path for page in manifest.pages] == [
        "pages/page_0001.png",
        "pages/page_0002.png",
        "pages/page_0003.png",
    ]
    assert sorted(path.name for path in (run_dir / "pages").glob("*.png")) == [
        "page_0001.png",
        "page_0002.png",
        "page_0003.png",
    ]
    assert [(page.width_pixels, page.height_pixels) for page in manifest.pages] == [
        (200, 200),
        (400, 200),
        (200, 400),
    ]


def test_render_pdf_pages_writes_consistent_manifest_and_assets(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "source.pdf"
    write_pdf(input_pdf, [(72, 72), (144, 72), (72, 144)])
    run_dir = create_run(input_pdf, tmp_path / "runs")

    render_pdf_pages(run_dir)

    manifest = json.loads((run_dir / "pages.json").read_text(encoding="utf-8"))
    source_pdf = run_dir / "input" / "source.pdf"
    source_sha256 = hashlib.sha256(source_pdf.read_bytes()).hexdigest()

    assert manifest["schema_version"] == "1.0"
    assert manifest["document_id"].startswith("sha256:")
    assert manifest["document_id"] == f"sha256:{source_sha256}"
    assert manifest["page_count"] == 3
    assert len(manifest["pages"]) == 3

    render_settings = manifest["render_settings"]
    assert render_settings["renderer_name"] == "pypdfium2"
    assert render_settings["renderer_version"]
    assert render_settings["dpi"] == 200
    assert render_settings["image_format"] == "png"
    assert render_settings["color_space"] == "RGB"
    assert render_settings["background_color"] == "white"

    for page in manifest["pages"]:
        image_path = run_dir / page["relative_path"]
        image_bytes = image_path.read_bytes()

        assert page["media_type"] == "image/png"
        assert page["size_bytes"] == image_path.stat().st_size
        assert page["sha256"] == hashlib.sha256(image_bytes).hexdigest()

        with Image.open(image_path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.size == (page["width_pixels"], page["height_pixels"])


def test_render_pdf_pages_rejects_invalid_pdf(tmp_path: Path) -> None:
    input_pdf = tmp_path / "source.pdf"
    input_pdf.write_bytes(b"not a PDF")
    run_dir = create_run(input_pdf, tmp_path / "runs")

    with pytest.raises(pdfium.PdfiumError):
        render_pdf_pages(run_dir)

    assert not (run_dir / "pages.json").exists()


def test_render_pdf_pages_rejects_encrypted_pdf(tmp_path: Path) -> None:
    input_pdf = tmp_path / "source.pdf"
    write_encrypted_pdf(input_pdf, "secret")
    run_dir = create_run(input_pdf, tmp_path / "runs")

    with pytest.raises(pdfium.PdfiumError):
        render_pdf_pages(run_dir)

    assert not (run_dir / "pages.json").exists()
