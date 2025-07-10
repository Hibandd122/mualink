from flask import Flask, request, jsonify
import cloudscraper, time, re
from bs4 import BeautifulSoup

app = Flask(__name__)
scraper = cloudscraper.create_scraper()

def extract_all_links_from_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    links = set()

    for a in soup.find_all("a", href=True):
        href = a['href'].strip()
        if href.startswith("http"):
            links.add(href)

    return list(links)

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
        except: pass
        time.sleep(1)

@app.route("/resolve")
def resolve():
    alias = request.args.get("alias")
    if not alias:
        return jsonify({"error": "Missing alias"}), 400

    snote_url = get_final_url(alias)
    try:
        r = scraper.get(snote_url, timeout=15)
        real_url = extract_link_from_snote(r.text)
    except Exception as e:
        return jsonify({"error": f"Lỗi tải snote: {str(e)}"})

    return jsonify({
        "alias": alias,
        "snote_url": snote_url,
        "real_url": real_url or "Không tìm thấy"
    })

if __name__ == "__main__":
    app.run(debug=True)
