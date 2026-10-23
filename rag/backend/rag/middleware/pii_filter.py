import json
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import ContentStream, Response

class PIIFilterMiddleware(BaseHTTPMiddleware):
    PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "cedula": r"\b\d{7,10}\b",
        "telefono": r"\b(?:\+57)?3\d{9}\b",
    }

    SENSITIVE_KEYS = {"cedula", "telefono", "password", "hashed_password", "token"}

    def _mask_text(self, text: str) -> str:
        text = re.sub(
            self.PATTERNS["email"],
            lambda m: m.group(0)[0] + "***" + m.group(0)[m.group(0).find("@") - 1:],
            text
        )
        text = re.sub(
            self.PATTERNS["telefono"],
            lambda m: m.group(0)[:4] + "*****" + m.group(0)[-2:],
            text
        )
        return text

    def _sanitize_json(self, data):
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if k.lower() in self.SENSITIVE_KEYS:
                    sanitized[k] = "******"
                else:
                    sanitized[k] = self._sanitize_json(v)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_json(item) for item in data]
        elif isinstance(data, str):
            return self._mask_text(data)
        return data

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        
        if "application/json" in content_type:
            response_body = [chunk async for chunk in response.body_iterator]
            response.body_iterator = ContentStream(response_body)
            
            try:
                raw_body = b"".join(response_body).decode("utf-8")
                json_data = json.loads(raw_body)
                sanitized_data = self._sanitize_json(json_data)
                
                filtered_content = json.dumps(sanitized_data)
                return Response(
                    content=filtered_content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type="application/json"
                )
            except Exception:
                pass

        return response
