"""Optional, manual page normalization; never overwrites source photographs."""

from dataclasses import asdict, dataclass
from pathlib import Path
import time
import uuid

from local_service.errors import ImageProcessingFailed


@dataclass
class ImageProcessResult:
    source_path: str
    processed_path: str
    width: int
    height: int
    page_detected: bool
    perspective_corrected: bool
    blur_score: float
    exposure_score: float
    warnings: list
    transform: dict
    processing_time_ms: int
    status: str

    def to_dict(self):
        return asdict(self)


class ImagePipeline:
    def __init__(self, processed_dir, blur_threshold=65.0, underexposed_threshold=45.0,
                 overexposed_threshold=235.0):
        self.processed_dir = Path(processed_dir)
        self.blur_threshold = blur_threshold
        self.underexposed_threshold = underexposed_threshold
        self.overexposed_threshold = overexposed_threshold

    def process(self, source_path):
        try:
            import cv2
            import numpy as np
            from PIL import Image, ImageOps
        except ImportError as error:
            raise ImageProcessingFailed("Image runtime dependencies are unavailable: " + str(error)) from error
        started = time.perf_counter()
        source = Path(source_path).resolve(strict=True)
        try:
            with Image.open(source) as original:
                orientation = original.getexif().get(274, 1)
                oriented = ImageOps.exif_transpose(original).convert("RGB")
                rgb = np.asarray(oriented)
        except Exception as error:
            raise ImageProcessingFailed("Cannot decode source image: " + str(error)) from error
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        exposure = float(gray.mean())
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 140)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        corners = None
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
            if cv2.contourArea(contour) < width * height * .12:
                break
            approx = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                corners = approx.reshape(4, 2).astype("float32")
                break
        transform = {"exif_orientation": orientation, "source_width": width, "source_height": height}
        corrected = False
        if corners is not None:
            s = corners.sum(axis=1)
            d = np.diff(corners, axis=1).ravel()
            ordered = np.array([corners[np.argmin(s)], corners[np.argmin(d)],
                                corners[np.argmax(s)], corners[np.argmax(d)]], dtype="float32")
            top, right, bottom, left = ordered
            out_width = max(1, int(max(np.linalg.norm(top - right), np.linalg.norm(bottom - left))))
            out_height = max(1, int(max(np.linalg.norm(top - left), np.linalg.norm(right - bottom))))
            target = np.array([[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1],
                               [0, out_height - 1]], dtype="float32")
            matrix = cv2.getPerspectiveTransform(ordered, target)
            bgr = cv2.warpPerspective(bgr, matrix, (out_width, out_height))
            corrected = True
            transform.update({"source_corners": ordered.tolist(), "matrix": matrix.tolist(),
                              "output_width": out_width, "output_height": out_height})
        warnings = []
        if corners is None:
            warnings.append("PAGE_NOT_FOUND")
        if blur < self.blur_threshold:
            warnings.append("TOO_BLURRY")
        if exposure < self.underexposed_threshold:
            warnings.append("UNDEREXPOSED")
        elif exposure > self.overexposed_threshold:
            warnings.append("OVEREXPOSED")
        status = warnings[0] if warnings else "OK"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        destination = self.processed_dir / (uuid.uuid4().hex + ".png")
        if not cv2.imwrite(str(destination), bgr):
            raise ImageProcessingFailed("Cannot write processed image")
        out_height, out_width = bgr.shape[:2]
        return ImageProcessResult(str(source), str(destination), out_width, out_height,
                                  corners is not None, corrected, round(blur, 3), round(exposure, 3),
                                  warnings, transform, int((time.perf_counter() - started) * 1000), status)
