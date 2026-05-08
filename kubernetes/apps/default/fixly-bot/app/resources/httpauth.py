import httpx


class HttpAuth(httpx.Auth):
    def __init__(self, auth_service):
        self.auth_service = auth_service

    async def async_auth_flow(self, request: httpx.Request):
        is_protected_api = "api.fixly.pl/graphql" in str(request.url)

        if is_protected_api:
            token = await self.auth_service.getAccessToken()
            if token:
                request.headers["authorization"] = token

        response = yield request

        if is_protected_api and response.status_code == 401:
            print("[HttpAuth] Got 401: Refreshing token and retrying web request...")

            success = await self.auth_service.refresh()

            if success:
                new_token = await self.auth_service.getAccessToken()
                request.headers["authorization"] = new_token

                yield request
