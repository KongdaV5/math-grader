#!/usr/bin/env python3
"""Run actual P4/P5 inference using the Python and packages inside Math Grader.app."""

import argparse
import base64
import json
from pathlib import Path
import platform
import sys

from PIL import Image, ImageDraw, ImageFont

from local_service.image_pipeline import ImagePipeline
from local_service.model_catalog import ModelCatalog
from local_service.model_manager import ModelManager
from local_service.model_providers import (
    MLXVLMProvider,
    PaddleFormulaProvider,
    PPOCRONNXProvider,
    RecognitionRequest,
)
from local_service.runtime_paths import RuntimePaths
from local_service.service import MathGraderService
from local_service.vision_strategy import VisionRecognitionStrategy


def font(size):
    system_font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    return ImageFont.truetype(str(system_font), size) if system_font.is_file() else ImageFont.load_default()


def make_fixtures(directory):
    directory.mkdir(parents=True, exist_ok=True)
    page = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((25, 25, 975, 1375), outline="black", width=3)
    draw.text((90, 70), "Synthetic math worksheet", font=font(42), fill="black")
    draw.text((95, 300), "Q1", font=font(42), fill="black")
    draw.rectangle((360, 224, 780, 392), outline="#777777", width=2)
    draw.text((382, 264), "120", font=font(62), fill="black")
    page_path = directory / "synthetic-submission.png"
    page.save(page_path)

    formula = Image.new("RGB", (420, 180), "white")
    formula_draw = ImageDraw.Draw(formula)
    formula_draw.text((170, 12), "1", font=font(62), fill="black")
    formula_draw.line((120, 90, 300, 90), fill="black", width=5)
    formula_draw.text((170, 98), "2", font=font(62), fill="black")
    formula_path = directory / "synthetic-fraction.png"
    formula.save(formula_path)
    return page_path, formula_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    args = parser.parse_args()
    args.data_dir = args.data_dir.expanduser().resolve()
    args.fixture_dir = args.fixture_dir.expanduser().resolve()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    page_path, formula_path = make_fixtures(args.fixture_dir)

    paths = RuntimePaths(args.data_dir).ensure()
    catalog = ModelCatalog()
    manager = ModelManager(catalog, paths)
    required_models = ("pp-ocrv6-small", "pp-formulanet-plus-m", "qwen3-vl-4b-mlx-4bit")
    statuses = {model_id: manager.get_model_status(model_id)["state"] for model_id in required_models}
    if any(state != "INSTALLED" for state in statuses.values()):
        raise SystemExit("Required existing ModelManager installations were not found: {}".format(statuses))

    service = MathGraderService(paths.database, data_dir=paths.root)
    image_result = ImagePipeline(paths.processed).process(page_path)
    if (not image_result.page_detected or image_result.width <= 0 or image_result.height <= 0
            or not Path(image_result.processed_path).is_file()):
        raise SystemExit("Bundled ImagePipeline smoke failed: {}".format(image_result.to_dict()))

    klass = service.create_class("P5-L2 synthetic runtime smoke")
    student = service.create_student(klass["id"], "SYNTHETIC-01", "Synthetic learner")
    assignment = service.create_assignment(klass["id"], "Synthetic runtime check", "2026-09-26")
    submission = service.create_submission(assignment["id"], student["id"])
    service.start_submission(submission["id"])
    uploaded = service.add_uploaded_page(submission["id"], page_path.name, page_path.read_bytes())
    service.slice.process_page(uploaded["id"])
    template_group = service.templates.create_template_group("Synthetic smoke", "4", "fall", "Synthetic")
    template = service.templates.create_page_template(template_group["id"], 1, "Page 1")
    service.import_template_reference(template["id"], {
        "filename": page_path.name,
        "image_base64": base64.b64encode(page_path.read_bytes()).decode("ascii"),
    })
    question = service.templates.create_question(template["id"], "1", "integer", "120")
    service.templates.create_answer_region(question["id"], 1, .36, .16, .42, .12)
    service.slice.bind_template(uploaded["id"], template["id"])
    crop = service.slice.create_crops(uploaded["id"])[0]
    crop_path = paths.root / crop["crop_path"]

    ocr_provider = PPOCRONNXProvider("pp-ocrv6-small", manager)
    ocr = ocr_provider.execute(RecognitionRequest(str(crop_path), "integer", "integer"))
    if not ocr.text or "120" not in ocr.text:
        raise SystemExit("Bundled PP-OCR Small inference did not return 120: {}".format(ocr.text))
    ocr_provider.unload()

    formula_provider = PaddleFormulaProvider("pp-formulanet-plus-m", manager)
    formula = formula_provider.execute(RecognitionRequest(str(formula_path), "fraction", "fraction"))
    if not formula.text or "frac" not in formula.text or "1" not in formula.text or "2" not in formula.text:
        raise SystemExit("Bundled Formula inference did not recognize the synthetic 1/2 fixture: {}".format(formula.text))
    formula_provider.unload()

    vision_provider = MLXVLMProvider("qwen3-vl-4b-mlx-4bit", manager)
    prompt = VisionRecognitionStrategy.prompt("integer")
    vision = vision_provider.execute(RecognitionRequest(
        str(crop_path), "integer", "integer", prompt=prompt, constraints={"max_tokens": 64}
    ))
    if not vision.text or not vision.text.strip():
        raise SystemExit("Bundled Qwen3-VL 4B inference returned no text")
    vision_provider.unload()

    report = {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version.split()[0],
        "architecture": platform.machine(),
        "models": statuses,
        "image_pipeline": {"status": image_result.status, "width": image_result.width,
                           "height": image_result.height, "processed_path": image_result.processed_path},
        "pp_ocr_small": {"text": ocr.text, "latency_ms": ocr.latency_ms},
        "formula": {"text": formula.text, "latency_ms": formula.latency_ms},
        "qwen3_vl_4b": {"text": vision.text, "latency_ms": vision.latency_ms},
        "synthetic_data_only": True,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
