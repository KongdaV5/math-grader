"""Lazy model adapters. No adapter downloads weights implicitly."""

from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
import threading
import time

from local_service.errors import ModelLoadFailed, ModelNotInstalled, ProviderUnavailable


@dataclass
class RecognitionRequest:
    image: str
    answer_type: str
    capability: str
    context: dict = field(default_factory=dict)
    prompt: str = ""
    constraints: dict = field(default_factory=dict)


class BaseModelProvider:
    provider_type = "base"
    dependency = ""

    def __init__(self, model_id, manager):
        self.model_id = model_id
        self.manager = manager
        self.lifecycle = "UNLOADED"
        self._lock = threading.RLock()
        self._runtime = None

    def health(self, load=False):
        status = self.manager.get_model_status(self.model_id)["state"]
        if status != "INSTALLED":
            return {"model_id": self.model_id, "state": "MODEL_NOT_INSTALLED",
                    "lifecycle": self.lifecycle, "runtime_available": bool(find_spec(self.dependency))}
        available = bool(find_spec(self.dependency))
        if not available:
            return {"model_id": self.model_id, "state": "PROVIDER_UNAVAILABLE",
                    "lifecycle": self.lifecycle, "runtime_available": False}
        if load:
            try:
                self.load()
            except (ModelLoadFailed, ProviderUnavailable) as error:
                return {"model_id": self.model_id, "state": error.code,
                        "lifecycle": self.lifecycle, "runtime_available": True, "error": str(error)}
        return {"model_id": self.model_id, "state": "READY" if self.lifecycle == "READY" else "LOADABLE",
                "lifecycle": self.lifecycle, "runtime_available": True}

    def _installed_path(self):
        status = self.manager.get_model_status(self.model_id)
        if status["state"] != "INSTALLED":
            raise ModelNotInstalled(self.model_id)
        return Path(status["path"])

    def load(self):
        with self._lock:
            if self.lifecycle == "READY":
                return
            path = self._installed_path()
            if not find_spec(self.dependency):
                raise ProviderUnavailable(self.dependency + " is not installed")
            self.lifecycle = "LOADING"
            try:
                self._runtime = self._load(path)
                self.lifecycle = "READY"
            except Exception as error:
                self.lifecycle = "ERROR"
                raise ModelLoadFailed("{}: {}".format(self.model_id, error)) from error

    def unload(self):
        with self._lock:
            self._runtime = None
            self.lifecycle = "UNLOADED"

    def can_remove(self):
        return self.lifecycle == "UNLOADED"

    def execute(self, request):
        with self._lock:
            self.load()
            started = time.perf_counter()
            output = self._infer(request)
        from local_service.recognition import RecognitionResult
        if isinstance(output, str):
            output = {"text": output}
        metadata = {"runtime": self.manager.catalog.get(self.model_id)["runtime"], **output.get("metadata", {})}
        return RecognitionResult(text=output.get("text"), normalized_candidate=output.get("text"),
                                 confidence=output.get("confidence"), provider=self.provider_type,
                                 model=self.model_id, latency_ms=int((time.perf_counter() - started) * 1000),
                                 metadata=metadata)

    def _infer(self, request):
        raise ProviderUnavailable("Inference pipeline is not implemented for this provider")


class PPOCRONNXProvider(BaseModelProvider):
    provider_type = "ppocr_onnx"
    dependency = "onnxruntime"

    def _load(self, path):
        from local_service.ocr_runtime import load_bundle
        return load_bundle(path)

    def _infer(self, request):
        from local_service.ocr_runtime import recognize_image
        outcome = recognize_image(request.image, self._runtime)
        return {"text": outcome["text"], "confidence": outcome["confidence"],
                "metadata": {"boxes": outcome["boxes"], "lines": outcome["lines"],
                             "ocr_latency_ms": outcome["latency_ms"]}}


class PaddleFormulaProvider(BaseModelProvider):
    provider_type = "paddle_formula"
    dependency = "paddleocr"

    def _load(self, path):
        from paddleocr import FormulaRecognition
        return FormulaRecognition(model_name="PP-FormulaNet_plus-M", model_dir=str(path / "model"), device="cpu")

    @staticmethod
    def parse_output(payload):
        if hasattr(payload,"json"):
            payload=payload.json
        if isinstance(payload,dict):
            value=payload.get("res",payload).get("rec_formula")
            if isinstance(value,str) and value.strip():
                return value.strip()
        from local_service.errors import InvalidRecognitionOutput
        raise InvalidRecognitionOutput("Formula provider returned no rec_formula")

    def _infer(self, request):
        output=list(self._runtime.predict(input=request.image,batch_size=1))
        if len(output)!=1:
            from local_service.errors import InvalidRecognitionOutput
            raise InvalidRecognitionOutput("Formula provider returned an unexpected result count")
        return {"text":self.parse_output(output[0]),"metadata":{"formula_format":"latex"}}


class MLXVLMProvider(BaseModelProvider):
    provider_type = "mlx_vlm"
    dependency = "mlx_vlm"

    def _load(self, path):
        from mlx_vlm import load
        return load(str(path / "model"))

    def _infer(self, request):
        if not request.prompt:
            raise ProviderUnavailable("Vision request requires an explicit prompt")
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config
        model, processor = self._runtime
        model_path = str(self._installed_path() / "model")
        config = load_config(model_path)
        prompt = apply_chat_template(processor, config, request.prompt, num_images=1)
        output = generate(model, processor, prompt, [request.image], verbose=False,
                          max_tokens=int(request.constraints.get("max_tokens", 64)))
        return {"text": output.text if hasattr(output, "text") else str(output),
                "metadata": {"prompt": request.prompt, "constraints": request.constraints}}


MODEL_PROVIDERS = {
    "ppocr_onnx": PPOCRONNXProvider,
    "paddle_formula": PaddleFormulaProvider,
    "mlx_vlm": MLXVLMProvider,
}


class ModelProviderRegistry:
    def __init__(self, catalog, manager):
        self.catalog, self.manager = catalog, manager
        self.providers = {}

    def get(self, model_id):
        model = self.catalog.get(model_id)
        if model_id not in self.providers:
            self.providers[model_id] = MODEL_PROVIDERS[model["provider_type"]](model_id, self.manager)
        return self.providers[model_id]

    def health(self, model_id, load=False):
        return self.get(model_id).health(load=load)

    def can_remove(self, model_id):
        provider = self.providers.get(model_id)
        return provider is None or provider.can_remove()

    def unload(self, model_id):
        provider = self.providers.get(model_id)
        if provider is not None:
            provider.unload()
