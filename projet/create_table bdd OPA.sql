-- ============================================
-- TABLE : INSTRUMENT_MARCHE
-- ============================================

CREATE TABLE instrument_marche (
    instrument_id      SERIAL PRIMARY KEY,
    symbole            VARCHAR(20) NOT NULL UNIQUE,
    actif              VARCHAR(50) NOT NULL,
    devise_cotation    VARCHAR(20) NOT NULL,
    plateforme         VARCHAR(100) NOT NULL
);

-- ============================================
-- TABLE : SERIE_PRIX
-- ============================================

CREATE TABLE serie_prix (
    prix_id              SERIAL PRIMARY KEY,
    date_heure           TIMESTAMP NOT NULL,
    pas_temps            VARCHAR(10) NOT NULL,

    prix_ouverture       NUMERIC(18,8) NOT NULL,
    prix_haut            NUMERIC(18,8) NOT NULL,
    prix_bas             NUMERIC(18,8) NOT NULL,
    prix_fermeture       NUMERIC(18,8) NOT NULL,

    volume               NUMERIC(24,8) NOT NULL DEFAULT 0,
    variation_prix_pct   NUMERIC(10,4),

    instrument_id        INTEGER NOT NULL,

    CONSTRAINT fk_serie_prix_instrument
        FOREIGN KEY (instrument_id)
        REFERENCES instrument_marche(instrument_id)
        ON DELETE CASCADE

);

-- Une seule bougie OHLC par date/pas de temps/instrument
ALTER TABLE serie_prix
ADD CONSTRAINT uq_serie_prix
UNIQUE (instrument_id, date_heure, pas_temps);

-- ============================================
-- TABLE : ACTIVITE_MARCHE
-- ============================================

CREATE TABLE activite_marche (
    activite_id         SERIAL PRIMARY KEY,
    date_heure          TIMESTAMP NOT NULL,
    pas_temps           VARCHAR(10) NOT NULL,

    volume_total        NUMERIC(24,8) NOT NULL,
    nombre_trades       INTEGER NOT NULL,

    ratio_achat_vente   NUMERIC(8,4),
    liquidite_score     NUMERIC(8,4),

    instrument_id       INTEGER NOT NULL,

    CONSTRAINT fk_activite_instrument
        FOREIGN KEY (instrument_id)
        REFERENCES instrument_marche(instrument_id)
        ON DELETE CASCADE

);

-- ============================================
-- TABLE : INDICATEUR_TECHNIQUE
-- ============================================

CREATE TABLE indicateur_technique (
    indicateur_id     SERIAL PRIMARY KEY,

    date_heure        TIMESTAMP NOT NULL,
    pas_temps         VARCHAR(10) NOT NULL,

    sma_20            NUMERIC(18,8),
    sma_50            NUMERIC(18,8),
    rsi_14            NUMERIC(8,4),
    macd              NUMERIC(18,8),
    volatilite        NUMERIC(12,6),

    instrument_id     INTEGER NOT NULL,

    CONSTRAINT fk_indicateur_instrument
        FOREIGN KEY (instrument_id)
        REFERENCES instrument_marche(instrument_id)
        ON DELETE CASCADE

);

-- ============================================
-- TABLE : SENTIMENT_SOCIAL
-- ============================================

CREATE TABLE sentiment_social (
    sentiment_id       SERIAL PRIMARY KEY,

    date_heure         TIMESTAMP NOT NULL,
    source             VARCHAR(100) NOT NULL,

    score_sentiment    NUMERIC(6,3),
    nombre_messages    INTEGER,
    score_engagement   NUMERIC(8,4)

);

-- ============================================
-- TABLE : EVENEMENT_MARCHE
-- ============================================

CREATE TABLE evenement_marche (
    evenement_id      SERIAL PRIMARY KEY,

    date_heure        TIMESTAMP NOT NULL,
    categorie         VARCHAR(100) NOT NULL,
    titre             VARCHAR(255) NOT NULL,

    impact_score      NUMERIC(8,4)
);

-- ============================================
-- TABLE : PREDICTION_MODELE
-- ============================================

CREATE TABLE prediction_modele (
    prediction_id        SERIAL PRIMARY KEY,

    date_heure           TIMESTAMP NOT NULL,
    horizon_prediction   VARCHAR(50) NOT NULL,

    prix_predit          NUMERIC(18,8),
    direction_predite    VARCHAR(10) NOT NULL,

    score_confiance      NUMERIC(5,4)
);

-- ============================================
-- TABLE : SIGNAL_TRADING
-- ============================================

CREATE TABLE signal_trading (
    signal_id          SERIAL PRIMARY KEY,

    date_heure         TIMESTAMP NOT NULL,

    signal             VARCHAR(10) NOT NULL,

    prix_entree        NUMERIC(18,8) NOT NULL,
    stop_loss          NUMERIC(18,8),
    take_profit        NUMERIC(18,8),

    score_confiance    NUMERIC(5,4),

    instrument_id      INTEGER NOT NULL,
    prediction_id      INTEGER,
    sentiment_id       INTEGER,
    evenement_id       INTEGER,

    CONSTRAINT fk_signal_instrument
        FOREIGN KEY (instrument_id)
        REFERENCES instrument_marche(instrument_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_signal_prediction
        FOREIGN KEY (prediction_id)
        REFERENCES prediction_modele(prediction_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_signal_sentiment
        FOREIGN KEY (sentiment_id)
        REFERENCES sentiment_social(sentiment_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_signal_evenement
        FOREIGN KEY (evenement_id)
        REFERENCES evenement_marche(evenement_id)
        ON DELETE SET NULL
);

-- ============================================
-- INDEX POUR LES PERFORMANCES
-- ============================================

CREATE INDEX idx_serie_prix_datetime
ON serie_prix(date_heure);

CREATE INDEX idx_serie_prix_instrument
ON serie_prix(instrument_id);

CREATE INDEX idx_prediction_datetime
ON prediction_modele(date_heure);

CREATE INDEX idx_signal_datetime
ON signal_trading(date_heure);

CREATE INDEX idx_indicateur_datetime
ON indicateur_technique(date_heure);

CREATE INDEX idx_activite_datetime
ON activite_marche(date_heure);