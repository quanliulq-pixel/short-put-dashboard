# -*- coding: utf-8 -*-
"""
Static Site Builder for GitHub Pages / Cloudflare Pages / Vercel Static Hosting.
Generates a complete `dist/index.html` containing the mobile & desktop interactive report.
"""
import os
from app import app

def main():
    os.makedirs("dist", exist_ok=True)
    with app.test_client() as client:
        resp = client.get("/api/export-mobile?dte=30")
        if resp.status_code != 200:
            raise RuntimeError(f"Export failed with status {resp.status_code}")
        html_bytes = resp.data
        out_path = os.path.join("dist", "index.html")
        with open(out_path, "wb") as f:
            f.write(html_bytes)
        print(f"Successfully built static site at {out_path} ({len(html_bytes)} bytes)")

if __name__ == "__main__":
    main()
