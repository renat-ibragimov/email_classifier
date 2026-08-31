import json

from httpx import ASGITransport, AsyncClient

from app.main import app

EXPECTED_SAMPLES = {
    "personal.eml",
    "newsletter.eml",
    "transactional.eml",
    "spam.eml",
    "hard_p.eml",
}


async def _get(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


class TestIndexPage:

    async def test_serves_html(self):
        response = await _get("/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    async def test_docs_still_reachable(self):
        response = await _get("/docs")

        assert response.status_code == 200


class TestSamples:

    async def test_manifest_lists_every_sample(self):
        response = await _get("/static/samples/samples.json")

        assert response.status_code == 200

        manifest = json.loads(response.content)
        samples = manifest["samples"]

        assert {sample["filename"] for sample in samples} == EXPECTED_SAMPLES
        for sample in samples:
            assert sample["label"]
            assert sample["description"]

    async def test_every_listed_sample_is_downloadable(self):
        manifest = json.loads((await _get("/static/samples/samples.json")).content)

        for sample in manifest["samples"]:
            response = await _get("/static/samples/" + sample["filename"])

            assert response.status_code == 200
            assert b"From:" in response.content
