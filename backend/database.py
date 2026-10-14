"""
Base de données SQLite minimale pour le site d'Obed.

Volontairement simple : sqlite3 de la bibliothèque standard, pas d'ORM.
Trois tables : contacts, orders (commandes), testimonials (témoignages).

Cycle de vie d'une commande (colonne `status`) :
    awaiting_price → pending → deposit_paid → completed
    (awaiting_price uniquement pour les commandes sur mesure, en attente
    qu'Obed fixe un prix ; les 3 forfaits du site démarrent à `pending`)
    `failed` peut survenir si la vérification du paiement échoue.

Le fichier de base de données est créé automatiquement au premier lancement,
à backend/data/site.db.
"""

import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Emplacement configurable : en production, pointe DB_PATH vers un volume
# persistant (ex. /data/site.db). Sur un disque éphémère (hébergeur gratuit),
# la base est effacée à chaque redéploiement.
DB_PATH = Path(os.environ.get("DB_PATH") or Path(__file__).resolve().parent / "data" / "site.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_ref TEXT NOT NULL UNIQUE,
                plan_name TEXT NOT NULL,
                is_custom INTEGER NOT NULL DEFAULT 0,
                custom_description TEXT,
                total_amount INTEGER,
                deposit_amount INTEGER,
                currency TEXT NOT NULL DEFAULT 'XOF',
                client_name TEXT NOT NULL,
                client_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                transaction_id TEXT,
                invoice_number TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS testimonials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                message TEXT NOT NULL,
                rating INTEGER,
                approved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        # Une transaction de paiement ne peut valider qu'une seule commande
        # (empêche de réutiliser un même transaction_id sur plusieurs commandes).
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_transaction_id "
            "ON orders(transaction_id) WHERE transaction_id IS NOT NULL"
        )
