import asyncio
import logging
import time
from urllib.parse import urljoin
import yaml
from aiohttp import ClientSession, web


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, requests_per_minute, max_connections):
        self.rate = requests_per_minute / 60
        self.max_connections = max_connections
        self.tokens = max_connections
        self.last_update = time.monotonic()

    async def acquire(self):
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
    def __init__(self, config):
        self.config = config
        self.limiters = {}

    def get_limiter(self, key, throttle_config):
        if key not in self.limiters:
            self.limiters[key] = RateLimiter(
                throttle_config["requests_per_minute"],
                throttle_config["max_connections"],
            )
        return self.limiters[key]

    async def handle_request(self, request):
        start_time = time.time()
        request_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        for url_config in self.config["allowed_urls"]:
            if request.path.startswith(url_config["source"]):
                if request.method not in url_config["methods"]:
                    logger.info(
                        f"{request_timestamp} - Path: {request.path} - Method: {request.method} - Status: 405 - Response Time: {(time.time() - start_time):.4f}s"
                    )
                    return web.Response(status=405, text="Method not allowed")

                # Apply throttling
                throttle_key = request.headers.get(
                    self.config["throttle_key_header"], request.remote
                )
                limiter = self.get_limiter(throttle_key, url_config["throttle"])
                if not await limiter.acquire():
                    logger.info(
                        f"{request_timestamp} - Path: {request.path} - Method: {request.method} - Status: 429 - Response Time: {(time.time() - start_time):.4f}s"
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
                        logger.info(
                            f"{request_timestamp} - Path: {request.path} - Method: {request.method} - Status: {resp.status} - Response Time: {(time.time() - start_time):.4f}s"
                        )
                        return response


async def main():
    with open("config.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    proxy = ReverseProxy(config)
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy.handle_request)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8080)

    print("Starting server on http://localhost:8080")
    await site.start()

    # Run forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
