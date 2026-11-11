import base64
import json

import pytest

from app.services import images


def test_parse_spec_with_and_without_size():
    assert images.parse_spec("a red  fox | 512x512") == ("a red fox", "512x512")
    assert images.parse_spec("a red fox") == ("a red fox", "1280x720")
    with pytest.raises(images.ImageError):
        images.parse_spec("   ")


def test_cache_key_follows_prompt_and_size():
    a = images.file_name("a fox | 512x512")
    assert a == images.file_name("a  fox|512x512")
    assert a != images.file_name("a fox | 1024x1024")
    assert a.startswith("a-fox-") and a.endswith(".png")


def test_gen_specs_finds_every_tag():
    md = "Hi\n\n![fox](gen: a fox | 512x512)\n\n![](image.png) ![Owl](GEN: an owl)"
    assert images.gen_specs(md) == ["a fox | 512x512", "an owl"]


class FakeAI:
    def __init__(self):
        self.calls = []

    async def image(self, prompt, *, model=None, size="1024x1024"):
        self.calls.append((prompt, model, size))
        return base64.b64encode(b"PNGDATA").decode()


async def test_generate_caches_with_sidecar(monkeypatch, image_dir):
    fake = FakeAI()
    monkeypatch.setattr(images, "ai", fake)

    png = await images.generate("a fox | 512x512")
    assert png.parent == image_dir and png.read_bytes() == b"PNGDATA"
    meta = json.loads(png.with_suffix(".json").read_text())
    assert meta["prompt"] == "a fox" and meta["size"] == "512x512" and meta["model"] == "image-fast"

    await images.generate("a fox | 512x512")          # cached: not drawn again
    assert len(fake.calls) == 1
