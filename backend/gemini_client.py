import logging

import httpx


logger = logging.getLogger(__name__)
FALLBACK_MODEL = "gemini-3.5-flash-lite"


async def generate_content(
    api_key: str,
    model: str,
    request_body: dict,
    client: httpx.AsyncClient | None = None,
    timeout: float = 60.0,
) -> httpx.Response:
    models = [model]
    if model != FALLBACK_MODEL:
        models.append(FALLBACK_MODEL)

    if client is None:
        async with httpx.AsyncClient(timeout=timeout) as owned_client:
            return await _generate_content(owned_client, api_key, models, request_body)
    return await _generate_content(client, api_key, models, request_body)


async def _generate_content(
    client: httpx.AsyncClient,
    api_key: str,
    models: list[str],
    request_body: dict,
) -> httpx.Response:
    for index, model in enumerate(models):
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        try:
            response = await client.post(
                endpoint,
                headers={"x-goog-api-key": api_key},
                json=request_body,
            )
        except httpx.ReadTimeout:
            if index == 0 and len(models) > 1:
                logger.warning(
                    "Gemini model %s timed out; retrying with fallback model",
                    model,
                )
                continue
            raise

        if response.status_code == 503 and index == 0 and len(models) > 1:
            logger.warning(
                "Gemini model %s is unavailable; retrying with fallback model",
                model,
            )
            continue
        response.raise_for_status()
        return response

    raise RuntimeError("Gemini content generation did not return a response.")
