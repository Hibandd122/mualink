from flask import Flask, request, jsonify
import cloudscraper, time, re
from bs4 import BeautifulSoup

app = Flask(__name__)
scraper = cloudscraper.create_scraper()

scraper.headers.update({
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "vi,en;q=0.9",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version": '"138.0.7204.101"',
    "sec-ch-ua-full-version-list": '"Not)A;Brand";v="8.0.0.0", "Chromium";v="138.0.7204.101", "Google Chrome";v="138.0.7204.101"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"10.0.0"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
})
# Trích tất cả các link từ thẻ <a href="...">
def extract_all_links_from_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http"):
            links.add(href)
    return list(links)


# Gửi POST tới mualink.vip để lấy link snote
def get_final_url(alias):
    url = "https://mualink.vip/links/redirect-to-link"
    data = {"alias": alias}
    while True:
        try:
            r = scraper.post(url, data=data, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            form = soup.find("form", {"id": "quick-link"})
            if form:
                action = form.get("action", "").replace("&amp;", "&")
                if "snote.vip/notes/" in action:
                    return action.split("url=")[-1]
        except:
            pass
        time.sleep(1)


# Route API: GET /resolve?alias=...
@app.route("/resolve")
def resolve():
    alias = request.args.get("alias")
    if not alias:
        return jsonify({"error": "Missing alias"}), 400

    snote_url = get_final_url(alias)
    try:
        scraper.cookies.update(
            {
                "cf_clearance": "axfEMvMPTWidkzXN4bcRahod9Mf5W1Dyb8uyd.5Aa6s-1752150452-1.2.1.1-0G9KSABOpDn2nIw2r_ddMVRPbChAbPdOSU2dG8LEGfhdDeFFJEQlmY29IaDoo5tGqGstTeUQUcMAnJpe1NvgDOkhVsoJwQe.b6uGN_AwNkJylkUUbtv4x9Ath.uKWi6RUEtah9cOdw4r8Un_aiiLF.l0TVf6v4pbPCbLpcFppNW0iyW.XRMQ9TDuF3lZL7zzih8C6Cvadeg7UDXMPzyldByBAXkEAcKTT2YUEqGsjmk",
                "XSRF-TOKEN": "eyJpdiI6InNCN241VStHdGlQeTVsZkozTFZpbmc9PSIsInZhbHVlIjoia1c4cUdGczlIYUt5d09VOUxlZUM2cCtIVEhDM0dZYnRNZFwvOW52ME9EZ01oYnlFRUpkWGdhTGlIVmdNdGhLUEEiLCJtYWMiOiJjNzhiYTM4NjU0OWYwODA0MDFiYjgwNmRkODRjNGZhYjRhOTRkZDY5ZjI4OTg5ODdhM2Q4MDcxYTBhYTk4MjQ1In0%3D",
                "online_notepad_session": "eyJpdiI6InFZT0VUSG9kSWFGWXZRRWZ4OElXUHc9PSIsInZhbHVlIjoiZ1RpU0I4amluT0g5cmljMEpSZ2h5ODNHamMwaTl0WGdNbFh4bDQwRk5EZXVTbFA0bHltT0h0TktLVkR1Vlk0aCIsIm1hYyI6IjA1NWRjMzc4OGNhMzMxMmYwNzE4MzQ0OGY4NmFmMTQyNjMzY2E3ODM1MGMxMzg1M2Q4NWExYmEzZDg2YjlmNjMifQ%3D%3D",
                "view-note": "eyJpdiI6InV1N2RSVTVxNXJlc1BMc2NCb2ViTlE9PSIsInZhbHVlIjoiMUloaStkSnZOWXZEM1RqVHlVb1hIYXZBMmhLY0dxeFFqTThHRFE2NEVxZ3FaQ1Iyd1JxWThDK1pyTTlONWQ0eiIsIm1hYyI6IjYwZjRkMWI4ZDI3NmRjMTFhMmZjMjMxMWZlMTc5ZGE0OWVmN2E5ZmRiNTU4NTZkMGQwYjQ1ZDFkZTBkNGJkNmMifQ%3D%3D",
                "jAeGgRtdE7yjpQ8D5D4JKcgfPHsanBOOh7s6s2fS": "eyJpdiI6IlF6dUpKckY5b3Y2dXRGbmk3aXBvNFE9PSIsInZhbHVlIjoiZ2RNOEprSFVweGtJRVhxTUZ0cVVHMFQxQU40ejJ1SkM5aEtsZjVvbHl0dTI2Q25kOVB4VEtCUm53ajFmbmJLbDFSSDdJcHg3bFhiVXpWeFVzeTRqZG96NzRVT0FYazFweDFpYzk1MnB4aTZFdXhBNVNLU2REb2FVZ2IzM0hSODNwYWF2cGJxaHhWeUR3TUZsZzVtbVxcLysxU0FWeGRXaDNwaTlWaU9WdzFycG01ZUJkTVwvcEY2STJuaU9BWXFDdWxmOWQ2UFI3Y3h0TjFzNXAyY01ON0NubXVqWkRwbWtSM0tKb2x6T1RGc0FlWWtzK1o1c3RxTEl6cFlORHpqSmZzSHlIYnJhUHJCNXpMSFl0VW9tU3l1SzFsUGNXVXU2aW15OFZFY0VcL3dMMHBha2lSVEcraUc5RUlwczdDcFRBVUsiLCJtYWMiOiJlZTZjMmQ4ZGY5ODRmN2NmOTc0NDc3NjAyZjAxNzM4YjJiMWVkMzUwOGM3NDgxMjA0M2IzY2EzZmQ4M2Y2NzViIn0%3D",
            }
        )
        r = scraper.get(snote_url, timeout=15)
        real_links = extract_all_links_from_html(r.text)

        return jsonify(
            {
                "alias": alias,
                "snote_url": snote_url,
                "real_links": real_links
                or r.text,  # ✅ trả HTML nếu không tìm thấy link
            }
        )

    except Exception as e:
        return jsonify({"error": f"Lỗi tải snote: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
