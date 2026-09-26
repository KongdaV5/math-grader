import json
from pathlib import Path
import time
from local_service.errors import DomainError
from local_service.model_providers import ModelProviderRegistry, RecognitionRequest


class RecognitionResult:
    def __init__(
        self,
        text=None,
        normalized_candidate=None,
        confidence=None,
        provider="unknown",
        model="unknown",
        latency_ms=0,
        metadata=None,
        error=None,
    ):
        self.text = text
        self.normalized_candidate = normalized_candidate
        self.confidence = confidence
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.metadata = metadata or {}
        self.error = error

    def to_dict(self):
        return {
            "text": self.text,
            "normalized_candidate": self.normalized_candidate,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
            "error": self.error,
            "provider_id": self.provider,
            "model_id": self.model,
            "runtime": self.metadata.get("runtime"),
            "raw_metadata": self.metadata,
        }


class MockRecognitionProvider:
    def __init__(self, name, settings):
        self.name = name
        self.model = settings["model"]
        self.text = settings.get("text", "23")
        self.confidence = settings.get("confidence", 0.99)
        self.configured_error = settings.get("error")
        self.metadata = settings.get("metadata", {"mode": "configured-mock"})

    def recognize(self, source_ref, answer_type, context=None):
        started = time.perf_counter()
        elapsed = int((time.perf_counter() - started) * 1000)
        return RecognitionResult(
            text=self.text,
            normalized_candidate=self.text,
            confidence=self.confidence,
            provider="mock",
            model=self.model,
            latency_ms=elapsed,
            metadata={
                **self.metadata,
                "source_ref": source_ref,
                "answer_type": answer_type,
            },
            error=self.configured_error,
        )


class ProviderRegistry:
    def __init__(self):
        self._factories = {"mock": lambda name, settings: MockRecognitionProvider(name, settings)}

    def register(self, provider_type, factory):
        if not provider_type or not callable(factory):
            raise ValueError("Provider registration requires a type and callable factory")
        self._factories[provider_type] = factory

    def create(self, name, settings):
        provider_type = settings.get("type")
        try:
            factory = self._factories[provider_type]
        except KeyError:
            raise ValueError("No provider registered for type: {}".format(provider_type))
        return factory(name, settings)


class RecognitionGateway:
    def __init__(self, config, registry=None, catalog=None, manager=None):
        self.registry = registry or ProviderRegistry()
        self.config = config
        self.model_registry = ModelProviderRegistry(catalog, manager) if catalog and manager else None
        self._validate_model_routes(catalog)
        self.providers = {}
        self.provider_settings = config.get("providers", {})
        for name, settings in config.get("providers", {}).items():
            self.providers[name] = self.registry.create(name, settings)

    @classmethod
    def from_file(cls, path=None, registry=None, catalog=None, manager=None):
        config_path = Path(path) if path else Path(__file__).parent / "config" / "recognition.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config.get("recognition"), dict) or not isinstance(
            config.get("providers"), dict
        ):
            raise ValueError("Recognition config must contain recognition and providers objects")
        return cls(config, registry=registry, catalog=catalog, manager=manager)

    def _validate_model_routes(self, catalog):
        if self.config.get("schema_version", 1) != 1:
            raise ValueError("Unsupported recognition config schema")
        routes = self.config.get("model_routes", {})
        if not isinstance(routes, dict):
            raise ValueError("model_routes must be an object")
        if routes and catalog is None:
            raise ValueError("Model routes require a catalog")
        for capability, route in routes.items():
            if not isinstance(route, dict) or not route.get("primary"):
                raise ValueError("Invalid model route")
            for model_id in (route["primary"], route.get("fallback")):
                if not model_id:
                    continue
                model = catalog.get(model_id)
                if capability not in model["capabilities"]:
                    raise ValueError("Model {} does not support {}".format(model_id, capability))

    def recognize_request(self, request):
        if not isinstance(request, RecognitionRequest):
            raise TypeError("RecognitionRequest required")
        if self.model_registry is None:
            raise ValueError("Model providers are not configured")
        route = self.config.get("model_routes", {}).get(request.capability)
        if not route:
            raise ValueError("No model route for capability " + request.capability)
        errors = []
        for model_id in (route["primary"], route.get("fallback")):
            if not model_id:
                continue
            try:
                return self.model_registry.get(model_id).execute(request)
            except DomainError as error:
                errors.append({"model_id": model_id, "code": error.code, "message": str(error)})
        error = errors[-1]
        return RecognitionResult(provider="model", model=error["model_id"],
                                 metadata={"attempts": errors}, error=error["code"])

    def recognize(self, source_ref, answer_type, context=None):
        routes = self.config["recognition"]
        route = routes.get(answer_type, routes.get("default"))
        if not route or not route.get("primary"):
            raise ValueError("No recognition route configured for answer type: {}".format(answer_type))

        primary_name = route["primary"]
        result = self._call(primary_name, source_ref, answer_type, context)
        if not result.error:
            return result

        fallback_name = route.get("fallback")
        if not fallback_name:
            return result

        fallback = self._call(fallback_name, source_ref, answer_type, context)
        fallback.metadata = dict(fallback.metadata)
        fallback.metadata["fallback_from"] = primary_name
        fallback.metadata["fallback_error"] = result.error
        return fallback

    def _call(self, provider_name, source_ref, answer_type, context):
        try:
            provider = self.providers[provider_name]
        except KeyError:
            raise ValueError("Recognition provider not configured: {}".format(provider_name))
        started = time.perf_counter()
        settings = self.provider_settings.get(provider_name, {})
        try:
            return provider.recognize(source_ref, answer_type, context=context)
        except Exception as error:
            return RecognitionResult(
                provider=settings.get("type", "unknown"),
                model=settings.get("model", "unknown"),
                latency_ms=int((time.perf_counter() - started) * 1000),
                metadata={"provider_name": provider_name, "source_ref": source_ref},
                error="{}: {}".format(type(error).__name__, error),
            )
