"""
Backend FastAPI pour le site vitrine d'Obed VODOUHE.

Règle centrale : tout client paie un acompte de 70% du montant total au
moment de la réservation, jamais 100%. Le montant est toujours calculé et
vérifié côté serveur — jamais fait confiance à ce qu'envoie le navigateur.

Deux façons de créer une commande :
  - POST /api/orders          → un des 3 forfaits listés (prix connu à l'avance)
  - POST /api/quote-request   → un projet sur mesure (prix à définir avec toi)

Pour une commande sur mesure, tu fixes le prix via
POST /api/admin/orders/{id}/set-price une fois d'accord avec le client ;
la commande passe alors en attente de paiement de l'acompte, comme les
forfaits standards.

Lancer en local :
    pip install -r requirements.txt
    uvicorn main:app --reload

Variables d'environnement à définir avant la mise en production
(voir README.md pour le détail) :
    KKIAPAY_PUBLIC_KEY, KKIAPAY_PRIVATE_KEY, KKIAPAY_SECRET_KEY
    KKIAPAY_SANDBOX=true|false
    ADMIN_TOKEN   (pour consulter/valider commandes, témoignages, fixer un prix)
"""

import html
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

try:  # charge backend/.env en local ; sans effet si python-dotenv est absent
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import database

DEPOSIT_RATE = 0.70  # 70% à la réservation, pour toutes les commandes

app = FastAPI(title="Obed VODOUHE — API du site vitrine")
database.init_db()

# Origines autorisées (séparées par des virgules) : en production, mets l'URL
# exacte du site, ex. ALLOWED_ORIGINS=https://TON-COMPTE.github.io
# Par défaut, seules les adresses locales sont acceptées.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_ref() -> str:
    """Référence publique non devinable, utilisée dans les URLs et liens envoyés au client."""
    return uuid.uuid4().hex[:12]


def deposit_for(total_amount: int) -> int:
    return round(total_amount * DEPOSIT_RATE)


# ---------- Services et tarifs (statique) ----------
# L'index.html a déjà ces valeurs en dur côté frontend pour que le site
# fonctionne même sans backend ; le prix réel facturé au client est
# toujours recalculé ici, jamais accepté tel quel depuis le frontend.

SERVICES = [
    {"path": "/code-review", "title": "Revue de code",
     "desc": "Relecture de ta base Python : bugs, structure, sécurité, recommandations concrètes."},
    {"path": "/rest-api", "title": "Développement API REST",
     "desc": "Conception et implémentation d'API avec FastAPI ou Django — endpoints, auth, permissions."},
    {"path": "/tests", "title": "Tests automatisés",
     "desc": "Mise en place de tests unitaires et d'intégration pour sécuriser tes déploiements."},
    {"path": "/api-docs", "title": "Documentation d'API",
     "desc": "Documentation claire de tes endpoints pour que ton équipe s'y retrouve."},
]

PRICING = {
    "Revue de code": {"price": 15000, "currency": "XOF", "unit": "à l'unité"},
    "API REST au forfait": {"price": 75000, "currency": "XOF", "unit": "forfait"},
    "Accompagnement mensuel": {"price": 150000, "currency": "XOF", "unit": "par mois"},
}


@app.get("/api/services")
def get_services():
    return SERVICES


@app.get("/api/pricing")
def get_pricing():
    return [{"name": k, **v} for k, v in PRICING.items()]


# ---------- Contact ----------

class ContactMessage(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)


@app.post("/api/contact")
def post_contact(payload: ContactMessage):
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO contacts (name, email, message, created_at) VALUES (?, ?, ?, ?)",
            (payload.name, payload.email, payload.message, now_iso()),
        )
    # TODO (optionnel) : envoyer un email de notification ici via smtplib
    # ou un service comme Resend/SendGrid, pour être notifié immédiatement.
    return {"status": "ok"}


# ---------- Commandes sur un forfait standard ----------

class OrderCreate(BaseModel):
    plan_name: str = Field(max_length=100)
    client_name: str = Field(min_length=1, max_length=100)
    client_email: EmailStr


def _order_public_view(row) -> dict:
    """Ce que le client a le droit de voir sur sa propre commande."""
    return {
        "public_ref": row["public_ref"],
        "plan_name": row["plan_name"],
        "is_custom": bool(row["is_custom"]),
        "custom_description": row["custom_description"],
        "total_amount": row["total_amount"],
        "deposit_amount": row["deposit_amount"],
        "currency": row["currency"],
        "status": row["status"],
        "invoice_number": row["invoice_number"],
    }


@app.post("/api/orders")
def create_order(payload: OrderCreate):
    plan = PRICING.get(payload.plan_name)
    if not plan:
        raise HTTPException(status_code=400, detail="Forfait inconnu — utilise /api/quote-request pour un projet sur mesure")

    total = plan["price"]
    deposit = deposit_for(total)
    ts = now_iso()
    ref = new_ref()

    with database.get_connection() as conn:
        conn.execute(
            """INSERT INTO orders
               (public_ref, plan_name, is_custom, total_amount, deposit_amount, currency,
                client_name, client_email, status, created_at, updated_at)
               VALUES (?, ?, 0, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (ref, payload.plan_name, total, deposit, plan["currency"],
             payload.client_name, payload.client_email, ts, ts),
        )

    return {
        "public_ref": ref, "plan_name": payload.plan_name, "is_custom": False,
        "total_amount": total, "deposit_amount": deposit, "currency": plan["currency"],
        "status": "pending",
    }


# ---------- Demande de devis (projet hors forfaits listés) ----------

class QuoteRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=100)
    client_email: EmailStr
    description: str = Field(min_length=1, max_length=5000)


@app.post("/api/quote-request")
def create_quote_request(payload: QuoteRequest):
    ts = now_iso()
    ref = new_ref()
    with database.get_connection() as conn:
        conn.execute(
            """INSERT INTO orders
               (public_ref, plan_name, is_custom, custom_description, currency,
                client_name, client_email, status, created_at, updated_at)
               VALUES (?, 'Projet sur mesure', 1, ?, 'XOF', ?, ?, 'awaiting_price', ?, ?)""",
            (ref, payload.description, payload.client_name, payload.client_email, ts, ts),
        )
    return {
        "public_ref": ref, "status": "awaiting_price",
        "message": "Merci ! Je reviens vers toi avec un prix sous peu. Garde cette référence pour suivre ta commande.",
    }


# ---------- Suivi public d'une commande (par référence, pas par id) ----------

@app.get("/api/orders/{public_ref}")
def get_order(public_ref: str):
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM orders WHERE public_ref = ?", (public_ref,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Commande introuvable — vérifie ta référence")
        return _order_public_view(row)


# ---------- Paiement Kkiapay — vérification serveur ----------
# Point important pour la sécurité : on ne fait JAMAIS confiance à la seule
# confirmation envoyée par le navigateur du client. On revérifie la
# transaction directement auprès de Kkiapay avec la clé privée, et on ne
# marque l'acompte "payé" que si Kkiapay confirme un statut SUCCESS ET que
# le montant correspond exactement à l'acompte attendu (70% du total).

class PaymentConfirmation(BaseModel):
    public_ref: str = Field(max_length=64)
    transaction_id: str | None = Field(default=None, max_length=128)


def _verify_with_kkiapay(transaction_id: str):
    """Appelle le SDK Admin Kkiapay pour vérifier la transaction.

    Renvoie (success: bool, amount: int | None, raw_status: str) ou lève
    une exception explicite si les clés ne sont pas configurées.
    """
    public_key = os.environ.get("KKIAPAY_PUBLIC_KEY")
    private_key = os.environ.get("KKIAPAY_PRIVATE_KEY")
    secret_key = os.environ.get("KKIAPAY_SECRET_KEY")
    sandbox = os.environ.get("KKIAPAY_SANDBOX", "true").lower() != "false"

    if not (public_key and private_key and secret_key):
        raise RuntimeError(
            "Clés Kkiapay non configurées côté serveur (KKIAPAY_PUBLIC_KEY, "
            "KKIAPAY_PRIVATE_KEY, KKIAPAY_SECRET_KEY). Voir README.md."
        )

    from kkiapay import Kkiapay  # import local : évite un crash au démarrage si le paquet manque

    client = Kkiapay(public_key, private_key, secret_key, sandbox=sandbox)
    transaction = client.verify_transaction(transaction_id)

    status = getattr(transaction, "status", None)
    amount = getattr(transaction, "amount", None)
    return status == "SUCCESS", amount, status


@app.post("/api/kkiapay/confirm")
def confirm_payment(payload: PaymentConfirmation):
    with database.get_connection() as conn:
        order = conn.execute("SELECT * FROM orders WHERE public_ref = ?", (payload.public_ref,)).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="Commande introuvable")

        if order["status"] in ("deposit_paid", "completed"):
            return {"status": "confirmed"}  # déjà confirmée, idempotent

        if order["total_amount"] is None:
            return {"status": "failed", "reason": "prix pas encore fixé pour cette commande"}

        if not payload.transaction_id:
            return {"status": "failed", "reason": "transaction_id manquant"}

        # Une transaction ne peut servir qu'une seule fois : sans cette garde,
        # un même paiement pourrait valider plusieurs commandes de même acompte.
        already_used = conn.execute(
            "SELECT 1 FROM orders WHERE transaction_id = ? AND id != ?",
            (payload.transaction_id, order["id"]),
        ).fetchone()
        if already_used:
            raise HTTPException(status_code=409, detail="Cette transaction a déjà été utilisée")

        try:
            success, verified_amount, raw_status = _verify_with_kkiapay(payload.transaction_id)
        except RuntimeError as exc:
            # Clés non configurées : on ne peut pas vérifier, donc on ne
            # confirme pas automatiquement plutôt que de faire semblant.
            raise HTTPException(status_code=503, detail=str(exc))

        amount_matches = verified_amount is not None and int(verified_amount) == int(order["deposit_amount"])

        if success and amount_matches:
            try:
                conn.execute(
                    "UPDATE orders SET status = 'deposit_paid', transaction_id = ?, updated_at = ? WHERE id = ?",
                    (payload.transaction_id, now_iso(), order["id"]),
                )
            except sqlite3.IntegrityError:  # course entre deux requêtes simultanées
                raise HTTPException(status_code=409, detail="Cette transaction a déjà été utilisée")
            return {"status": "confirmed"}
        else:
            # On ne mémorise pas le transaction_id d'un paiement refusé : il ne
            # doit pas bloquer une nouvelle tentative légitime.
            conn.execute(
                "UPDATE orders SET status = 'failed', updated_at = ? WHERE id = ?",
                (now_iso(), order["id"]),
            )
            return {"status": "failed", "reason": raw_status}


# ---------- Témoignages ----------
# Publiés uniquement après validation manuelle (approved=1), pour éviter
# les faux témoignages ou le spam. Utilise les endpoints /api/admin/...
# ci-dessous pour les valider.

class TestimonialCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    rating: int | None = None


@app.get("/api/testimonials")
def list_public_testimonials():
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT id, client_name, message, rating, created_at "
            "FROM testimonials WHERE approved = 1 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


@app.post("/api/testimonials")
def submit_testimonial(payload: TestimonialCreate):
    if payload.rating is not None and not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=400, detail="La note doit être entre 1 et 5")
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO testimonials (client_name, message, rating, approved, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (payload.client_name, payload.message, payload.rating, now_iso()),
        )
    return {"status": "ok", "message": "Merci, ton témoignage sera publié après validation."}


# ---------- Facture ----------
# Une page HTML simple, imprimable (Ctrl/Cmd+P → Enregistrer en PDF),
# disponible dès que l'acompte est confirmé. C'est la "facture normalisée"
# fournie au client, avec le solde restant clairement indiqué.

def _invoice_html(order) -> str:
    total = order["total_amount"] or 0
    deposit = order["deposit_amount"] or 0
    balance = total - deposit
    # Toute valeur saisie par un client est échappée avant d'entrer dans le HTML.
    esc = lambda value: html.escape(str(value if value is not None else ""))
    label = esc(order["custom_description"] if order["is_custom"] else order["plan_name"])
    date_str = esc(order["updated_at"][:10])
    invoice_no = esc(order["invoice_number"] or "")
    public_ref = esc(order["public_ref"])
    status = esc(order["status"])
    client_name = esc(order["client_name"])
    client_email = esc(order["client_email"])
    currency = esc(order["currency"])

    return f"""<!doctype html>
<html lang="fr"><head><meta charset="UTF-8">
<title>Facture {invoice_no or public_ref}</title>
<style>
  body {{ font-family: 'Manrope', Arial, sans-serif; color:#1a1a1a; max-width:720px; margin:2.5rem auto; padding:0 1.5rem; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:3px solid #8BC34A; padding-bottom:1rem; margin-bottom:1.5rem; }}
  .head h1 {{ font-size:1.3rem; margin:0 0 .3rem; }}
  .muted {{ color:#666; font-size:.9rem; }}
  table {{ width:100%; border-collapse:collapse; margin:1.5rem 0; }}
  td, th {{ padding:.6rem .4rem; border-bottom:1px solid #e5e5e5; text-align:left; font-size:.95rem; }}
  th {{ color:#666; font-weight:600; font-size:.8rem; text-transform:uppercase; }}
  .totals td {{ font-weight:700; }}
  .balance {{ color:#c0392b; }}
  .btn {{ background:#8BC34A; color:#0D1321; border:none; padding:.6rem 1.2rem; border-radius:6px; font-weight:700; cursor:pointer; }}
  @media print {{ .no-print {{ display:none; }} }}
</style></head>
<body>
  <div class="head">
    <div>
      <h1>Obed VODOUHE</h1>
      <div class="muted">Développeur Full-Stack Python — Cotonou, Bénin<br>
      leonardovodouhe06@gmail.com — +229 01 53 95 45 01</div>
    </div>
    <div style="text-align:right;">
      <div class="muted">Facture</div>
      <div style="font-weight:700;">{invoice_no or '(en attente de finalisation)'}</div>
      <div class="muted">{date_str}</div>
    </div>
  </div>

  <div class="muted">Facturé à :</div>
  <div style="font-weight:700; margin-bottom:1rem;">{client_name} — {client_email}</div>

  <table>
    <tr><th>Prestation</th><th>Référence</th><th>Statut</th></tr>
    <tr><td>{label}</td><td>{public_ref}</td><td>{status}</td></tr>
  </table>

  <table>
    <tr><td>Montant total</td><td style="text-align:right;">{total:,} {currency}</td></tr>
    <tr><td>Acompte versé (70%)</td><td style="text-align:right;">{deposit:,} {currency}</td></tr>
    <tr class="totals"><td class="balance">Solde restant dû</td><td style="text-align:right;" class="balance">{balance:,} {currency}</td></tr>
  </table>

  <p class="muted">Le solde restant est à régler selon les modalités convenues avec Obed VODOUHE (livraison finale du projet).</p>

  <button class="btn no-print" onclick="window.print()">Imprimer / Enregistrer en PDF</button>
</body></html>"""


@app.get("/invoice/{public_ref}", response_class=HTMLResponse)
def get_invoice(public_ref: str):
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM orders WHERE public_ref = ?", (public_ref,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Commande introuvable")
        if row["status"] not in ("deposit_paid", "completed"):
            return HTMLResponse(
                "<p style='font-family:sans-serif; padding:2rem;'>"
                "La facture sera disponible une fois l'acompte confirmé.</p>",
                status_code=200,
            )
        return HTMLResponse(_invoice_html(row))


# ---------- Administration (toi uniquement) ----------
# Protégé par un jeton partagé simple : envoie l'en-tête
# "X-Admin-Token: <valeur de ADMIN_TOKEN>" pour y accéder.

def _check_admin(x_admin_token: str | None):
    expected = os.environ.get("ADMIN_TOKEN")
    # compare_digest : comparaison à temps constant (évite les attaques par chronométrage)
    if not expected or not x_admin_token or not secrets.compare_digest(
        x_admin_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Non autorisé")


@app.get("/api/admin/orders")
def admin_list_orders(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    with database.get_connection() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]


class SetPrice(BaseModel):
    total_amount: int


@app.post("/api/admin/orders/{order_id}/set-price")
def admin_set_price(order_id: int, payload: SetPrice, x_admin_token: str | None = Header(default=None)):
    """Fixe le prix d'une commande (typiquement une commande sur mesure,
    après discussion avec le client). Recalcule automatiquement l'acompte
    de 70% et repasse la commande en attente de paiement de cet acompte."""
    _check_admin(x_admin_token)
    if payload.total_amount <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide")
    deposit = deposit_for(payload.total_amount)
    with database.get_connection() as conn:
        cur = conn.execute(
            "UPDATE orders SET total_amount = ?, deposit_amount = ?, status = 'pending', updated_at = ? WHERE id = ?",
            (payload.total_amount, deposit, now_iso(), order_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Commande introuvable")
    return {"status": "pending", "total_amount": payload.total_amount, "deposit_amount": deposit}


@app.post("/api/admin/orders/{order_id}/complete")
def admin_complete_order(order_id: int, x_admin_token: str | None = Header(default=None)):
    """Marque une commande comme livrée/terminée et lui attribue un numéro
    de facture définitif (si elle n'en a pas déjà un)."""
    _check_admin(x_admin_token)
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Commande introuvable")

        invoice_number = row["invoice_number"]
        if not invoice_number:
            year = datetime.now(timezone.utc).year
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE invoice_number IS NOT NULL"
            ).fetchone()["n"]
            invoice_number = f"FAC-{year}-{count + 1:04d}"

        conn.execute(
            "UPDATE orders SET status = 'completed', invoice_number = ?, updated_at = ? WHERE id = ?",
            (invoice_number, now_iso(), order_id),
        )
    return {"status": "completed", "invoice_number": invoice_number}


@app.get("/api/admin/testimonials")
def admin_list_testimonials(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    with database.get_connection() as conn:
        rows = conn.execute("SELECT * FROM testimonials ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]


@app.post("/api/admin/testimonials/{testimonial_id}/approve")
def admin_approve_testimonial(testimonial_id: int, x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    with database.get_connection() as conn:
        cur = conn.execute(
            "UPDATE testimonials SET approved = 1 WHERE id = ?", (testimonial_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Témoignage introuvable")
    return {"status": "approved"}


# Le frontend est publié uniquement sur GitHub Pages ; ce service ne fournit
# que l'API et les factures générées.
