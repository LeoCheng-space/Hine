"""Only BB is an access-session and persistence authority."""
import logging

import aiohttp

from . import protocol as p

LOG = logging.getLogger("hine_realtime")


class Fault(Exception):
    def __init__(self, code="DEPENDENCY_UNAVAILABLE", retryable=True, retry_after=None, user_session=False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        self.user_session = user_session

    def payload(self):
        result = {"code": self.code, "message": p.MESSAGES[self.code], "retryable": self.retryable}
        if self.code == "RATE_LIMITED" and self.retryable and self.retry_after is not None:
            result["retry_after_ms"] = self.retry_after
        return result


class InternalClient:
    def __init__(self, settings, session):
        self.settings = settings
        self.session = session

    async def call(self, operation, body, write=False):
        try:
            async with self.session.post(
                self.settings.api_url + "/internal/v1/" + operation,
                json=body,
                headers={"Authorization": "Bearer " + self.settings.outbound_token},
                allow_redirects=False,
            ) as response:
                chunks = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    if len(chunks) + len(chunk) > 1048576:
                        raise p.Invalid("Oversize authority response")
                    chunks.extend(chunk)
                try:
                    decoded = p.obj(p.loads(chunks))
                except (p.Invalid, TypeError):
                    raise Fault("OUTCOME_UNCONFIRMED" if write and response.status == 200 else "DEPENDENCY_UNAVAILABLE") from None
                if response.status == 200:
                    if set(decoded) != {"data"} or not isinstance(decoded["data"], dict):
                        raise Fault("OUTCOME_UNCONFIRMED" if write else "DEPENDENCY_UNAVAILABLE")
                    return decoded["data"]
                if set(decoded) != {"error"}:
                    raise Fault()
                try:
                    value = p.obj(decoded["error"])
                    for key in ["code", "message", "request_id", "retryable", "details"]:
                        p.check(key in value)
                    p.string(value["code"], True)
                    p.string(value["message"])
                    p.string(value["request_id"], True)
                    p.boolean(value["retryable"])
                    p.obj(value["details"])
                    p.check(value["code"] in p.ERROR_STATUS and p.ERROR_STATUS[value["code"]] == response.status)
                except (p.Invalid, TypeError):
                    raise Fault() from None
                code = value["code"]
                user_session = code == "UNAUTHENTICATED" and value["details"].get("auth_layer") == "user_session" and operation != "readSessionInvalidations"
                if code == "UNAUTHENTICATED" and not user_session:
                    LOG.warning("internal_service_identity_failure operation=%s", operation)
                    raise Fault()
                delay = value["details"].get("retry_after_ms")
                if type(delay) is not int or not 0 <= delay <= 9007199254740991:
                    delay = None
                raise Fault(code, value["retryable"], delay, user_session)
        except Fault:
            raise
        except aiohttp.ClientConnectorError:
            LOG.warning("internal_connect_failure operation=%s", operation)
            raise Fault() from None
        except (aiohttp.ClientError, TimeoutError, p.Invalid, UnicodeError, TypeError, ValueError):
            LOG.warning("internal_response_failure operation=%s", operation)
            raise Fault("OUTCOME_UNCONFIRMED" if write else "DEPENDENCY_UNAVAILABLE") from None
