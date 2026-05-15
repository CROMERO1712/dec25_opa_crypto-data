# dec25_opa_crypto-data
Pipeline de données  cryptomonnaies - Projet OPA Ingénieur Data
# 🪙 dec25_opca_crypto_data

> Projet fil rouge DataScientest — Pipeline de données cryptomonnaies  
> **Promotion :** dec25 | **Canal :** #dec25_cde_opa | **Équipe :** 4 membres

---

## 📌 Objectif

Construire une pipeline de données complète permettant de **collecter, structurer et exploiter** des données issues des marchés de cryptomonnaies, afin d'identifier :

- Les **dynamiques de marché**
- Les **corrélations entre actifs**
- Les **variables explicatives** pertinentes pour la modélisation

---

## 🪙 Périmètre — Cryptomonnaies analysées

| Crypto | Symbole | Rôle dans le portefeuille |
|--------|---------|--------------------------|
| **Bitcoin** | BTC | 🔵 Socle principal — réserve de valeur, indicateur de tendance |
| Ethereum *(optionnel)* | ETH | Smart contracts, DeFi, NFT |
| Binance Coin *(optionnel)* | BNB | Exposition aux exchanges |
| Cardano *(optionnel)* | ADA | Blockchain académique, long terme |
| Solana *(optionnel)* | SOL | Haute performance, dynamique élevée |

---

## 🏗️ Architecture de la pipeline

```
APIs Externes
(CoinGecko, DefiLlama, Etherscan, Solscan...)
          │
          ▼
┌─────────────────────┐
│   sourcing/         │  ← Scripts Python de collecte
│   script1_*.py      │     Market Cap actuelle (validation API)
│   script2_*.py      │     Snapshot complet (prix, rang, volume)
│   script3_*.py      │     Historique 365j (séries temporelles)
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   data/raw/         │  ← CSV bruts exportés (ignorés par Git)
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   database/         │  ← PostgreSQL
│   schema.sql        │     Tables : prices, ohlcv, metadata
│   insert.py         │     Insertion des données
│   queries.py        │     Requêtes analytiques
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   analysis/         │  ← Jupyter Notebooks
│   01_exploration    │     Analyse exploratoire
│   02_correlation    │     Corrélations entre actifs
│   03_modelisation   │     Variables explicatives & ML
└─────────────────────┘
```

---

## 📁 Structure du projet

```
dec25_opca_crypto_data/
│
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
│
├── sourcing/
│   ├── script1_market_cap_btc.py       ← Market Cap BTC (validation API)
│   ├── script2_market_snapshot.py      ← Snapshot complet 5 cryptos
│   └── script3_historique_market_cap.py ← Historique 365j (série temporelle)
│
├── database/
│   ├── schema.sql                      ← Création des tables PostgreSQL
│   ├── insert.py                       ← Insertion des données
│   └── queries.py                      ← Requêtes analytiques
│
├── analysis/
│   ├── 01_exploration.ipynb
│   ├── 02_correlation.ipynb
│   └── 03_modelisation.ipynb
│
├── data/                               ← ⚠️ Ignoré par Git
│   ├── raw/                            ← CSV bruts des APIs
│   └── processed/                      ← Données nettoyées
│
├── docs/
│   └── recap_opa.docx
│
└── tests/
    ├── test_script1.py
    ├── test_script2.py
    └── test_script3.py
```

---

## 🚀 Démarrage rapide

### 1. Cloner le repo
```bash
git clone https://github.com/TON_USERNAME/dec25_opca_crypto_data.git
cd dec25_opca_crypto_data
```

### 2. Installer les dépendances
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Configurer les variables d'environnement
```bash
cp .env.example .env
# Remplis .env avec tes identifiants PostgreSQL
```

### 4. Lancer les scripts de sourcing
```bash
# Validation API (Script 1)
python sourcing/script1_market_cap_btc.py

# Snapshot complet (Script 2)
python sourcing/script2_market_snapshot.py

# Historique 365 jours (Script 3)
python sourcing/script3_historique_market_cap.py
```

---

## 📦 Sources de données

| Source | Cryptos | Données |
|--------|---------|---------|
| [CoinGecko](https://www.coingecko.com/api) | BTC, ETH, BNB, ADA, SOL | Prix, Market Cap, Volume, OHLCV |
| [DefiLlama](https://defillama.com/docs/api) | ETH, SOL | TVL DeFi |
| [Etherscan](https://etherscan.io/apis) | ETH | Gas fees, smart contracts |
| [Solscan](https://solscan.io/) | SOL | TPS, activité réseau |
| [Cardano Explorer](https://explorer.cardano.org/) | ADA | Transactions, staking |

---

## 🌿 Branches

| Branche | Responsable | Statut |
|---------|-------------|--------|
| `main` | — | Version stable OPA |
| `develop` | — | Branche de travail |
| `feature/sourcing` | --- | ✅ Scripts 1, 2, 3 terminés |
| `feature/database` | Membre 2 | 🔄 En cours |
| `feature/analysis` | Membre 3 | ⏳ À venir |
| `feature/visualisation` | Membre 4 | ⏳ À venir |

---

## ✅ Avancement

- [x] Définition du scope (5 cryptos)
- [x] Identification des sources de données
- [x] Script 1 — Market Cap actuelle Bitcoin
- [x] Script 2 — Snapshot marché complet
- [x] Script 3 — Historique 365j (séries temporelles)
- [ ] Schéma base de données PostgreSQL
- [ ] Insertion des données en base
- [ ] Analyse exploratoire (Jupyter)
- [ ] Analyse des corrélations
- [ ] Modélisation (variables explicatives)
- [ ] Visualisation & Dashboard

---

## 👥 Équipe

Projet réalisé dans le cadre du diplôme **Ingénieur Data — DataScientest**  
Promotion `dec25` | Canal `#dec25_cde_opa`

---

*Aucune clé API requise pour CoinGecko en plan gratuit — accès immédiat.*
