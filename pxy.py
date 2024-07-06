import asyncio
import logging
import time
from urllib.parse import urljoin
import yaml
from aiohttp import ClientSession, web


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter"""
    def __init__(self, requests_per_minute, max_connections):
        self.rate = requests_per_minute / 60
        self.max_connections = max_connections
        self.tokens = max_connections
        self.last_update = time.monotonic()

    async def acquire(self):
        """Aquire lock based on key and timeout"""
        # while True: return 429 instead of wait
        now = time.monotonic()
        time_passed = now - self.last_update
        self.tokens = min(self.max_connections, self.tokens + time_passed * self.rate)
        self.last_update = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
        # await asyncio.sleep(0.1)


class ReverseProxy:
    """
    A reverse proxy implementation with request handling and logging.
    """

    def __init__(self, config):
        self.config = config
        self.limiters = {}

    def get_limiter(self, key, throttle_config):
        """
        Get or create a rate limiter for the given key.

        :param key: The key to identify the rate limiter.
        :param throttle_config: Configuration for the rate limiter.
        :return: A rate limiter instance.
        """
        if key not in self.limiters:
            self.limiters[key] = RateLimiter(
                throttle_config["requests_per_minute"],
                throttle_config["max_connections"],
            )
        return self.limiters[key]

    async def handle_request(self, request):
        """
        Handle incoming requests, apply throttling, and proxy to the target.

        :param request: The incoming request object.
        :return: The response from the target server or an error response.
        """
        start_time = time.time()
        # request_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        for url_config in self.config["allowed_urls"]:
            if request.path.startswith(url_config["source"]):
                if request.method not in url_config["methods"]:
                    logger.debug(
                        "Path: %s - Method: %s - Status: 405 - Response Time: %.4fs",
                        request.path,
                        request.method,
                        time.time() - start_time,
                    )
                    return web.Response(status=405, text="Method not allowed")

                # Apply throttling
                throttle_key = request.headers.get(
                    self.config["throttle_key_header"], request.remote
                )
                limiter = self.get_limiter(throttle_key, url_config["throttle"])
                if not await limiter.acquire():
                    logger.debug(
                        "Path: %s - Method: %s - Status: 429 - Response Time: %.4fs",
                        request.path,
                        request.method,
                        time.time() - start_time,
                    )
                    return web.Response(status=429, text="Rate limit exceeded")

                # Proxy the request
                target_url = urljoin(
                    url_config.get("host", self.config["global_host"]),
                    url_config["destination"]
                    + request.path[len(url_config["source"]) :],
                )

                headers = {
                    k: v for k, v in request.headers.items() if k.lower() != "host"
                }
                headers["X-Forwarded-Host"] = request.host

                async with ClientSession() as session:
                    async with session.request(
                        method=request.method,
                        url=target_url,
                        headers=headers,
                        data=await request.read(),
                    ) as resp:
                        response = web.Response(
                            status=resp.status,
                            headers=resp.headers,
                            body=await resp.read(),
                        )
                        logger.debug(
                            "Path: %s - Method: %s - Status: %d - "
                            "Response Time: %.4fs",
                            request.path,
                            request.method,
                            resp.status,
                            time.time() - start_time,
                        )
                        return response

        logger.debug(
            "Path: %s - Method: %s - Status: 404 - Response Time: %.4fs",
            request.path,
            request.method,
            time.time() - start_time,
        )
        return web.Response(status=404, text="Not found")


async def main():
    """Entrypoint"""
    with open("config.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    proxy = ReverseProxy(config)
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy.handle_request)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8080)

    logger.info("Starting server on http://localhost:8080")
    await site.start()

    # Run forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
