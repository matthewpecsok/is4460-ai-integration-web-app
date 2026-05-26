import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger("flower_shop.gemini")


class GeminiRecommendationError(Exception):
    """Raised when a Gemini product recommendation cannot be completed."""


class GeminiNotConfigured(GeminiRecommendationError):
    """Raised when the Gemini API key is missing."""


def get_product_recommendation(question, products):
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiNotConfigured("GEMINI_API_KEY is not configured.")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _build_prompt(question, products)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 350,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        _gemini_url(),
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=getattr(settings, "GEMINI_TIMEOUT_SECONDS", 10)) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("gemini.http_error", extra={"payload": {"status_code": exc.code}})
        raise GeminiRecommendationError("Gemini could not complete the recommendation.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("gemini.request_error", extra={"payload": {"error": str(exc)}})
        raise GeminiRecommendationError("Gemini could not complete the recommendation.") from exc

    recommendation = _extract_text(response_payload)
    if not recommendation:
        raise GeminiRecommendationError("Gemini returned an empty recommendation.")
    return recommendation


def _gemini_url():
    model = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _build_prompt(question, products):
    product_lines = []
    for product in products:
        stock_status = "in stock" if product.in_stock else "out of stock"
        description = product.description or "No description provided."
        product_lines.append(
            f"- {product.name}: ${product.price} ({stock_status}). {description}"
        )

    product_context = "\n".join(product_lines) or "No products are currently listed."
    return (
        "You are a helpful flower shop product guide. Recommend products only from the catalog below. "
        "Prefer in-stock products, mention prices when useful, and keep the answer concise. "
        "If nothing fits, say so and suggest the closest available option.\n\n"
        f"Customer request: {question}\n\n"
        f"Catalog:\n{product_context}"
    )


def _extract_text(response_payload):
    parts = (
        response_payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    return "\n".join(part.get("text", "") for part in parts).strip()
