class DomainError(Exception):
    code = "DOMAIN_ERROR"
    status = 400

    def __init__(self, message=None):
        super().__init__(message or self.code)


class ModelNotInstalled(DomainError):
    code = "MODEL_NOT_INSTALLED"
    status = 404


class ModelDownloadFailed(DomainError):
    code = "MODEL_DOWNLOAD_FAILED"
    status = 502


class ModelVerifyFailed(DomainError):
    code = "MODEL_VERIFY_FAILED"
    status = 422


class ModelLoadFailed(DomainError):
    code = "MODEL_LOAD_FAILED"
    status = 503


class ProviderUnavailable(DomainError):
    code = "PROVIDER_UNAVAILABLE"
    status = 503


class InsufficientDiskSpace(DomainError):
    code = "INSUFFICIENT_DISK_SPACE"
    status = 507


class ImageProcessingFailed(DomainError):
    code = "IMAGE_PROCESSING_FAILED"
    status = 422


class PageNotFound(DomainError):
    code = "PAGE_NOT_FOUND"
    status = 422


class TemplateNotFound(DomainError):
    code = "TEMPLATE_NOT_FOUND"
    status = 404


class InvalidAnswerRegion(DomainError):
    code = "INVALID_ANSWER_REGION"
    status = 400
