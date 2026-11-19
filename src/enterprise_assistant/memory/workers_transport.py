"""Bridge HTTPX requests to Cloudflare Workers' JavaScript ``fetch`` API.

Python Workers run in Pyodide and do not provide ordinary Python sockets.
This small transport keeps the existing HTTPX D1 adapter contract while
issuing its authenticated requests through the Workers runtime.
"""

import httpx
from js import Object
from js import fetch as worker_fetch
from pyodide.ffi import to_js


class CloudflareFetchTransport(httpx.AsyncBaseTransport):
    """Send bounded JSON requests through the Workers ``fetch`` global."""

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Translate one HTTPX request and return its JSON response.

        Args:
            request: Fully resolved D1 gateway request from HTTPX.

        Returns:
            HTTPX response preserving status and content type.

        Raises:
            httpx.ConnectError: The Workers fetch call fails.
        """
        try:
            body = await request.aread()
            headers = {
                name: value
                for name, value in request.headers.items()
                if name.lower() not in {"host", "content-length"}
            }
            options: dict[str, object] = {
                "method": request.method,
                "headers": headers,
            }
            if body:
                options["body"] = body.decode("utf-8")
            response = await worker_fetch(
                str(request.url),
                to_js(options, dict_converter=Object.fromEntries),
            )
            content = await response.text()
            content_type = response.headers.get("content-type")
        except Exception as exc:
            raise httpx.ConnectError(
                "Cloudflare fetch failed.", request=request
            ) from exc

        headers = (
            {"content-type": str(content_type)}
            if content_type
            else {}
        )
        return httpx.Response(
            status_code=int(response.status),
            headers=headers,
            content=str(content).encode("utf-8"),
            request=request,
        )


    async def aclose(self) -> None:
        """Release no resources; Workers owns the underlying fetch client."""

