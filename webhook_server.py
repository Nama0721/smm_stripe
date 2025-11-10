# webhook_server.py
from flask import Flask, request, abort
import stripe
import asyncio
from vending import load_data, save_data, send_log  # 必要なら調整

app = Flask(__name__)

# ←←←← ここに Stripe Dashboard からコピーしたシークレット貼り付け
STRIPE_WEBHOOK_SECRET = "whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

bot = None  # Render 起動時に bot を渡す（後で）

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except:
        return abort(400)

    # 決済完了イベントだけ処理
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_key = session.metadata.get("order_key")
        if not order_key:
            return "", 200

        data = load_data()
        if order_key not in data["orders"]:
            return "", 200

        order = data["orders"][order_key]
        order["status"] = "processing"
        order["transaction_id"] = session.id
        save_data(data)

        # DM 通知（bot が必要）
        if bot:
            user = asyncio.run(bot.fetch_user(int(order["user_id"])))
            asyncio.run(user.send(f"決済確認！処理中…"))

        # SMM API 送信（vending.py から関数呼び出し）
        from stripe_integration import send_to_smm  # 必要に応じて
        success = asyncio.run(send_to_smm(order))

        if success:
            order["status"] = "completed"
            save_data(data)
            if bot:
                asyncio.run(user.send(f"完了！反映されました！"))
                asyncio.run(send_log(bot, order_key, "achievements"))
                asyncio.run(send_log(bot, order_key, "sales"))
        else:
            order["status"] = "failed"
            save_data(data)
            if bot:
                asyncio.run(user.send("処理失敗…管理者に連絡を"))

    return "", 200

def run_server(discord_bot):
    global bot
    bot = discord_bot
    app.run(host="0.0.0.0", port=10000)  # Render はポート 10000 を使う
