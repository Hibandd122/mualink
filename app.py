from flask import Flask, request, jsonify
import cloudscraper, time
from bs4 import BeautifulSoup

app = Flask(__name__)
scraper = cloudscraper.create_scraper()

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

@app.route("/resolve")
def resolve():
    alias = request.args.get("alias")
    if not alias:
        return jsonify({"error": "Missing alias"}), 400

    snote_url = get_final_url(alias)
    return jsonify({
        "snote_url": snote_url
    })

if __name__ == "__main__":
    app.run(debug=True)
