# webhook_server.py
from flask import Flask, request, abort
import stripe
import asyncio
import os
from vending import load_data, save_data, send_log

app = Flask(__name__)

# 環境変数から取得
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not STRIPE_WEBHOOK_SECRET:
    raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set!")

bot = None

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print(f"Webhook error: {e}")
        return abort(400)

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

        if bot:
            user = asyncio.run(bot.fetch_user(int(order["user_id"])))
            asyncio.run(user.send("決済確認！処理中…"))

        from stripe_integration import send_to_smm
        success = asyncio.run(send_to_smm(order))

        if success:
            order["status"] = "completed"
            save_data(data)
            if bot:
                asyncio.run(user.send("完了！反映されました！"))
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
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
