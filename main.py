import os
import logging
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Charger les variables d'environnement
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Critères par défaut
user_criteria = {
    "marque": "BMW",
    "modele": "530d",
    "prix_max": 25000,
    "annee_min": 2017,
    "km_max": 120000,
    "frais_import": 1500,
    "frais_vente": 500
}

pending_field = {}

# --------- Fonctions de scraping LeParking ---------
def get_annonces_leparking(marque, modele, prix_max, annee_min, km_max):
    url = f"https://www.leparking.fr/recherche?marque={marque}&modele={modele}&prix_max={prix_max}&annee_min={annee_min}&km_max={km_max}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    annonces = []

    # Sélecteurs HTML fictifs, à adapter selon le site réel
    for item in soup.select(".listing-item")[:20]:
        try:
            titre = item.select_one(".listing-title").get_text(strip=True)
            prix = int(item.select_one(".listing-price").get_text(strip=True).replace("€","").replace(" ",""))
            lien = item.select_one("a")["href"]
            annonces.append({"titre": titre, "prix": prix, "lien": lien})
        except:
            continue
    return annonces

def calculer_roi(prix_achat, frais_import, frais_vente, prix_vente_estime):
    return round(((prix_vente_estime - prix_achat - frais_import - frais_vente) / prix_achat) * 100, 1)

# --------- Commandes Bot ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🚗 Bonjour M. Garin,\nBienvenue sur AutoROI.\n\n"
        f"Utilisez /menu pour modifier vos critères.\n"
        f"Utilisez /runonce pour voir les 10 meilleures annonces."
    )

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Marque", callback_data="edit_marque"),
         InlineKeyboardButton("Modèle", callback_data="edit_modele")],
        [InlineKeyboardButton("Prix max (€)", callback_data="edit_prix"),
         InlineKeyboardButton("Année min", callback_data="edit_annee")],
        [InlineKeyboardButton("Km max", callback_data="edit_km")],
        [InlineKeyboardButton("Frais import (€)", callback_data="edit_import"),
         InlineKeyboardButton("Frais vente (€)", callback_data="edit_vente")],
        [InlineKeyboardButton("✅ Voir annonces", callback_data="show_ads")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ Choisissez un critère à modifier :", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("edit_"):
        field = query.data.split("_")[1]
        pending_field[query.from_user.id] = field
        await query.edit_message_text(f"✏️ Entrez une nouvelle valeur pour **{field}** :")
        return
    elif query.data == "show_ads":
        await send_ads(update, context)

async def update_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending_field:
        return
    field = pending_field.pop(user_id)
    value = update.message.text.strip()
    try:
        if field in ["prix", "annee", "km", "import", "vente"]:
            value = int(value)
    except ValueError:
        await update.message.reply_text("⚠️ Merci d’entrer un nombre valide.")
        return
    if field == "marque": user_criteria["marque"] = value
    elif field == "modele": user_criteria["modele"] = value
    elif field == "prix": user_criteria["prix_max"] = int(value)
    elif field == "annee": user_criteria["annee_min"] = int(value)
    elif field == "km": user_criteria["km_max"] = int(value)
    elif field == "import": user_criteria["frais_import"] = int(value)
    elif field == "vente": user_criteria["frais_vente"] = int(value)
    await update.message.reply_text(f"✅ {field.capitalize()} mis à jour : {value}")
    await show_criteria(update, context)

async def show_criteria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        f"📋 *Critères actuels AutoROI:*\n"
        f"- Marque : {user_criteria['marque']}\n"
        f"- Modèle : {user_criteria['modele']}\n"
        f"- Prix max : {user_criteria['prix_max']} €\n"
        f"- Année min : {user_criteria['annee_min']}\n"
        f"- Km max : {user_criteria['km_max']} km\n"
        f"- Frais import : {user_criteria['frais_import']} €\n"
        f"- Frais vente : {user_criteria['frais_vente']} €"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

async def send_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    marque = user_criteria["marque"]
    modele = user_criteria["modele"]
    annonces = get_annonces_leparking(marque, modele, user_criteria["prix_max"], user_criteria["annee_min"], user_criteria["km_max"])
    for annonce in annonces:
        prix_vente_estime = annonce["prix"] + 3000
        annonce["roi"] = calculer_roi(annonce["prix"], user_criteria["frais_import"], user_criteria["frais_vente"], prix_vente_estime)
    annonces = sorted(annonces, key=lambda x: x["roi"], reverse=True)[:10]
    message = "🔔 *TOP 10 — Meilleures affaires réelles :*\n\n"
    for i, a in enumerate(annonces, 1):
        message += f"{i}. [{a['titre']} – {a['prix']} € – ROI {a['roi']}%]({a['lien']})\n"
    await update.callback_query.edit_message_text(message, parse_mode="Markdown", disable_web_page_preview=True)

# --------- Main ---------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("criteres", show_criteria))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_field))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
