from flask import Flask, request, jsonify
import cloudscraper
from bs4 import BeautifulSoup
import time

app = Flask(__name__)
scraper = cloudscraper.create_scraper()

def get_mualink_final_url(alias):
    post_url = "https://mualink.vip/links/redirect-to-link"
    data = {'alias': alias}
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    while True:
        try:
            resp = scraper.post(post_url, data=data, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            form = soup.find("form", {"id": "quick-link"})

            if form and "url=" in form.get("action", ""):
                action = form["action"].replace("&amp;", "&")
                final_url = action.split("url=")[-1]

                if final_url.startswith("https://snote.vip/notes/"):
                    return final_url

                print(f"[⚠️] URL khác snote: {final_url}, thử lại...")
            else:
                print("[❌] Không tìm thấy form hoặc URL, thử lại...")

            time.sleep(1)

        except Exception as e:
            print(f"[ERROR] Lỗi khi gửi POST: {e}")
            time.sleep(2)

@app.route("/resolve", methods=["GET"])
def resolve():
    alias = request.args.get("alias")
    if not alias:
        return jsonify({"error": "Thiếu alias ?alias=..."}), 400

    final_url = get_mualink_final_url(alias)
    if final_url:
        return jsonify({"alias": alias, "final_url": final_url})
    return jsonify({"error": "Không tìm được link"}), 500

if __name__ == "__main__":
    app.run(debug=True)
