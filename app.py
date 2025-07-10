from flask import Flask, request, jsonify
import cloudscraper, time, re
from bs4 import BeautifulSoup

app = Flask(__name__)
scraper = cloudscraper.create_scraper()

def extract_link_from_snote(html):
    soup = BeautifulSoup(html, "html.parser")
    a = soup.find("a", href=True)
    if a and a['href'].startswith("http"):
        return a['href']
    match = re.search(r'https?://[^\s"\']+', soup.get_text())
    return match.group(0) if match else None

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
