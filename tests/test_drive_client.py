"""Cliente HTTPX real con MockTransport; R6 parcial, cero Google remoto."""

from unittest import IsolatedAsyncioTestCase

import httpx

from botsky.adapters.drive import DriveClient, DriveError

SCOPE = "a" * 64


async def token():
    return "synthetic-token"


def metadata(**kw):
    return dict(
        id="file1",
        name="archivo.txt",
        mimeType="text/plain",
        size="3",
        parents=["folder1"],
        appProperties={"botsky_scope": SCOPE},
        trashed=False,
        **kw,
    )


class DriveClientTest(IsolatedAsyncioTestCase):
    async def make(self, handle, **kw):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)
        return DriveClient("folder1", token, client=http, **kw)

    async def test_disabled_and_missing_scope_never_call_client(self):
        def forbidden(request):
            raise AssertionError("unexpected HTTP")

        client = await self.make(forbidden)
        with self.assertRaises(DriveError) as caught:
            await client.search(None)
        self.assertEqual(caught.exception.code, "invalid_scope")
        client._token_provider = None
        with self.assertRaises(DriveError) as caught:
            await client.search(None, scope_key=SCOPE)
        self.assertEqual(caught.exception.code, "drive_not_configured")

    async def test_search_scope_escaped_query_and_verified_download(self):
        calls = []

        def handle(request):
            calls.append(request)
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-token")
            if request.url.path.endswith("/files"):
                q = request.url.params["q"]
                self.assertIn("botsky_scope", q)
                self.assertIn("name contains 'a\\'b'", q)
                return httpx.Response(200, json={"files": [metadata()]})
            if request.url.params.get("alt") == "media":
                return httpx.Response(200, content=b"abc")
            return httpx.Response(200, json=metadata())

        client = await self.make(handle)
        self.assertEqual((await client.search("a'b", scope_key=SCOPE))[0].id, "file1")
        self.assertEqual(await client.download("file1", scope_key=SCOPE), b"abc")
        self.assertEqual(len(calls), 3)

    async def test_foreign_metadata_blocks_bytes_and_redirect_is_not_followed(self):
        calls = []

        def handle(request):
            calls.append(request)
            data = metadata()
            data["appProperties"] = {"botsky_scope": "b" * 64}
            return httpx.Response(200, json=data)

        client = await self.make(handle)
        with self.assertRaises(DriveError) as caught:
            await client.download("file1", scope_key=SCOPE)
        self.assertEqual(caught.exception.code, "file_outside_scope")
        self.assertEqual(len(calls), 1)

        async def redirect(request):
            return httpx.Response(302, headers={"Location": "https://example.invalid/stolen"})

        client = await self.make(redirect)
        with self.assertRaises(DriveError):
            await client.search(None, scope_key=SCOPE)

    async def test_uncertain_upload_uses_reserved_id_and_never_reposts(self):
        calls = []

        def handle(request):
            calls.append(request.method)
            if request.method == "POST":
                raise httpx.ReadTimeout("synthetic cutoff", request=request)
            return httpx.Response(200, json=metadata())

        client = await self.make(handle)
        result = await client.upload("file1", "archivo.txt", "text/plain", b"abc", scope_key=SCOPE)
        self.assertEqual(result.id, "file1")
        self.assertEqual(calls, ["POST", "GET"])

    async def test_resumable_upload_rejects_foreign_location_and_stays_uncertain(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        calls = []

        def handle(request):
            calls.append((request.method, request.url.host))
            if request.method == "POST":
                return httpx.Response(200, headers={"Location": "https://attacker.invalid/upload"})
            return httpx.Response(404, json={})

        client = await self.make(handle)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            path.write_bytes(b"abc")
            with self.assertRaises(DriveError) as caught:
                await client.upload_file(
                    "file1", "archivo.txt", "text/plain", path, scope_key=SCOPE
                )
        self.assertEqual(caught.exception.code, "upload_uncertain")
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(calls, [("POST", "www.googleapis.com"), ("GET", "www.googleapis.com")])

    async def test_resumable_upload_streams_file_and_size_is_verified(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        calls = []

        async def handle(request):
            calls.append(request.method)
            if request.method == "POST":
                self.assertEqual(request.headers["x-upload-content-length"], "3")
                return httpx.Response(
                    200,
                    headers={
                        "Location": "https://www.googleapis.com/upload/drive/v3/files?upload_id=synthetic"
                    },
                )
            self.assertEqual(await request.aread(), b"abc")
            return httpx.Response(200, json=metadata())

        client = await self.make(handle)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            path.write_bytes(b"abc")
            result = await client.upload_file(
                "file1", "archivo.txt", "text/plain", path, scope_key=SCOPE
            )
        self.assertEqual(result.size, 3)
        self.assertEqual(calls, ["POST", "PUT"])

    async def test_metadata_body_limit_and_deleted_file_are_rejected(self):
        def huge(request):
            return httpx.Response(200, content=b"x" * 65537)

        client = await self.make(huge)
        with self.assertRaises(DriveError) as caught:
            await client.search(None, scope_key=SCOPE)
        self.assertEqual(caught.exception.code, "invalid_provider_result")

        def deleted(request):
            data = metadata()
            data["trashed"] = True
            return httpx.Response(200, json={"files": [data]})

        client = await self.make(deleted)
        with self.assertRaises(DriveError) as caught:
            await client.search(None, scope_key=SCOPE)
        self.assertEqual(caught.exception.code, "file_outside_scope")
