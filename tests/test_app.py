import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageFont  # noqa: E402

import app as app_module  # noqa: E402

LOCAL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def local_font(size):
    return ImageFont.truetype(LOCAL_FONT, size)


def img_bytes(color=(200, 50, 50), size=(300, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    buf.seek(0)
    return buf


class KomawariTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self._orig = app_module.get_font
        app_module.get_font = local_font

    def tearDown(self):
        app_module.get_font = self._orig

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

    def test_index_ok(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_make_tate2(self):
        res = self.client.post(
            "/make",
            data={
                "layout": "縦2コマ",
                "img1": (img_bytes(), "1.png"),
                "img2": (img_bytes((0, 0, 200)), "2.png"),
                "cap1": "Hello",
                "cap2": "World",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.startswith(b"\x89PNG"))
        img = Image.open(io.BytesIO(res.data))
        boxes, total_h = app_module.panel_boxes("縦2コマ")
        self.assertEqual(img.size, (1000, total_h))

    def test_make_4koma(self):
        data = {"layout": "4コマ"}
        for i in range(1, 5):
            data[f"img{i}"] = (img_bytes(), f"{i}.png")
        res = self.client.post("/make", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        img = Image.open(io.BytesIO(res.data))
        self.assertEqual(img.size[0], 1000)

    def test_make_partial_images(self):
        res = self.client.post(
            "/make",
            data={"layout": "3コマ", "img1": (img_bytes(), "1.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)

    def test_make_no_images(self):
        res = self.client.post("/make", data={"layout": "縦2コマ"}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)

    def test_font_unavailable(self):
        def broken(size):
            raise app_module.FontUnavailable("down")

        app_module.get_font = broken
        res = self.client.post(
            "/make",
            data={"layout": "縦2コマ", "img1": (img_bytes(), "1.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 500)
        self.assertIn("フォント", res.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
