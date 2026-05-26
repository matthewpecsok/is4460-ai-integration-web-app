import logging
import time


class RequestJSONLoggingMiddleware:
    """Emit one structured JSON log per request with timing and status details."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("flower_shop.request")

    def __call__(self, request):
        start = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self.logger.exception(
                "request.failed",
                extra={
                    "payload": {
                        "method": request.method,
                        "path": request.get_full_path(),
                        "status_code": 500,
                        "duration_ms": duration_ms,
                        "remote_addr": request.META.get("REMOTE_ADDR", ""),
                        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                    }
                },
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        event_payload = {
            "method": request.method,
            "path": request.get_full_path(),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "remote_addr": request.META.get("REMOTE_ADDR", ""),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        }

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            event_payload["user_id"] = user.pk

        self.logger.info("request.completed", extra={"payload": event_payload})
        return response
