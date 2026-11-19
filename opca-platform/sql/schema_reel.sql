--
-- PostgreSQL database dump
--

\restrict 5gz50g4EKm4NnU4QWO5EdBwxXqaMi6DX3bUUdGCK82u23NbcZLIa8Fx3i1IxO43

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activite_marche; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activite_marche (
    activite_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    pas_temps character varying(10) NOT NULL,
    volume_total numeric(24,8) NOT NULL,
    nombre_trades integer NOT NULL,
    ratio_achat_vente numeric(8,4),
    liquidite_score numeric(8,4),
    instrument_id integer NOT NULL,
    plateforme_id integer NOT NULL
);


--
-- Name: activite_marche_activite_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.activite_marche_activite_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: activite_marche_activite_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.activite_marche_activite_id_seq OWNED BY public.activite_marche.activite_id;


--
-- Name: evenement_marche; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evenement_marche (
    evenement_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    categorie character varying(100) NOT NULL,
    titre character varying(255) NOT NULL,
    impact_score numeric(8,4)
);


--
-- Name: evenement_marche_evenement_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.evenement_marche_evenement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: evenement_marche_evenement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.evenement_marche_evenement_id_seq OWNED BY public.evenement_marche.evenement_id;


--
-- Name: indicateur_technique; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.indicateur_technique (
    indicateur_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    pas_temps character varying(10) NOT NULL,
    sma_20 numeric(18,8),
    sma_50 numeric(18,8),
    rsi_14 numeric(8,4),
    macd numeric(18,8),
    volatilite numeric(12,6),
    instrument_id integer NOT NULL,
    plateforme_id integer NOT NULL
);


--
-- Name: indicateur_technique_indicateur_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.indicateur_technique_indicateur_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: indicateur_technique_indicateur_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.indicateur_technique_indicateur_id_seq OWNED BY public.indicateur_technique.indicateur_id;


--
-- Name: instrument_marche; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instrument_marche (
    instrument_id integer NOT NULL,
    symbole character varying(20) NOT NULL,
    actif character varying(50) NOT NULL,
    devise_cotation character varying(20) NOT NULL
);


--
-- Name: instrument_marche_instrument_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.instrument_marche_instrument_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: instrument_marche_instrument_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.instrument_marche_instrument_id_seq OWNED BY public.instrument_marche.instrument_id;


--
-- Name: plateforme; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plateforme (
    plateforme_id integer NOT NULL,
    nom character varying(100) NOT NULL
);


--
-- Name: plateforme_plateforme_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plateforme_plateforme_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plateforme_plateforme_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plateforme_plateforme_id_seq OWNED BY public.plateforme.plateforme_id;


--
-- Name: prediction_modele; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prediction_modele (
    prediction_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    horizon_prediction character varying(50) NOT NULL,
    prix_predit numeric(18,8),
    direction_predite character varying(10) NOT NULL,
    score_confiance numeric(5,4)
);


--
-- Name: prediction_modele_prediction_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prediction_modele_prediction_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prediction_modele_prediction_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prediction_modele_prediction_id_seq OWNED BY public.prediction_modele.prediction_id;


--
-- Name: sentiment_social; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sentiment_social (
    sentiment_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    source character varying(100) NOT NULL,
    score_sentiment numeric(6,3),
    nombre_messages integer,
    score_engagement numeric(8,4)
);


--
-- Name: sentiment_social_sentiment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sentiment_social_sentiment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sentiment_social_sentiment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sentiment_social_sentiment_id_seq OWNED BY public.sentiment_social.sentiment_id;


--
-- Name: serie_prix; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.serie_prix (
    prix_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    pas_temps character varying(10) NOT NULL,
    prix_ouverture numeric(18,8) NOT NULL,
    prix_haut numeric(18,8) NOT NULL,
    prix_bas numeric(18,8) NOT NULL,
    prix_fermeture numeric(18,8) NOT NULL,
    volume numeric(24,8) DEFAULT 0 NOT NULL,
    variation_prix_pct numeric(10,4),
    instrument_id integer NOT NULL,
    plateforme_id integer NOT NULL
);


--
-- Name: serie_prix_prix_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.serie_prix_prix_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: serie_prix_prix_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.serie_prix_prix_id_seq OWNED BY public.serie_prix.prix_id;


--
-- Name: signal_trading; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signal_trading (
    signal_id integer NOT NULL,
    date_heure timestamp without time zone NOT NULL,
    signal character varying(10) NOT NULL,
    prix_entree numeric(18,8) NOT NULL,
    stop_loss numeric(18,8),
    take_profit numeric(18,8),
    score_confiance numeric(5,4),
    instrument_id integer NOT NULL,
    prediction_id integer,
    sentiment_id integer,
    evenement_id integer
);


--
-- Name: signal_trading_signal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.signal_trading_signal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: signal_trading_signal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.signal_trading_signal_id_seq OWNED BY public.signal_trading.signal_id;


--
-- Name: activite_marche activite_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activite_marche ALTER COLUMN activite_id SET DEFAULT nextval('public.activite_marche_activite_id_seq'::regclass);


--
-- Name: evenement_marche evenement_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evenement_marche ALTER COLUMN evenement_id SET DEFAULT nextval('public.evenement_marche_evenement_id_seq'::regclass);


--
-- Name: indicateur_technique indicateur_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicateur_technique ALTER COLUMN indicateur_id SET DEFAULT nextval('public.indicateur_technique_indicateur_id_seq'::regclass);


--
-- Name: instrument_marche instrument_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instrument_marche ALTER COLUMN instrument_id SET DEFAULT nextval('public.instrument_marche_instrument_id_seq'::regclass);


--
-- Name: plateforme plateforme_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plateforme ALTER COLUMN plateforme_id SET DEFAULT nextval('public.plateforme_plateforme_id_seq'::regclass);


--
-- Name: prediction_modele prediction_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prediction_modele ALTER COLUMN prediction_id SET DEFAULT nextval('public.prediction_modele_prediction_id_seq'::regclass);


--
-- Name: sentiment_social sentiment_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sentiment_social ALTER COLUMN sentiment_id SET DEFAULT nextval('public.sentiment_social_sentiment_id_seq'::regclass);


--
-- Name: serie_prix prix_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.serie_prix ALTER COLUMN prix_id SET DEFAULT nextval('public.serie_prix_prix_id_seq'::regclass);


--
-- Name: signal_trading signal_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_trading ALTER COLUMN signal_id SET DEFAULT nextval('public.signal_trading_signal_id_seq'::regclass);


--
-- Name: activite_marche activite_marche_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activite_marche
    ADD CONSTRAINT activite_marche_pkey PRIMARY KEY (activite_id);


--
-- Name: evenement_marche evenement_marche_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evenement_marche
    ADD CONSTRAINT evenement_marche_pkey PRIMARY KEY (evenement_id);


--
-- Name: indicateur_technique indicateur_technique_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicateur_technique
    ADD CONSTRAINT indicateur_technique_pkey PRIMARY KEY (indicateur_id);


--
-- Name: instrument_marche instrument_marche_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instrument_marche
    ADD CONSTRAINT instrument_marche_pkey PRIMARY KEY (instrument_id);


--
-- Name: plateforme plateforme_nom_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plateforme
    ADD CONSTRAINT plateforme_nom_key UNIQUE (nom);


--
-- Name: plateforme plateforme_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plateforme
    ADD CONSTRAINT plateforme_pkey PRIMARY KEY (plateforme_id);


--
-- Name: prediction_modele prediction_modele_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prediction_modele
    ADD CONSTRAINT prediction_modele_pkey PRIMARY KEY (prediction_id);


--
-- Name: sentiment_social sentiment_social_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sentiment_social
    ADD CONSTRAINT sentiment_social_pkey PRIMARY KEY (sentiment_id);


--
-- Name: serie_prix serie_prix_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.serie_prix
    ADD CONSTRAINT serie_prix_pkey PRIMARY KEY (prix_id);


--
-- Name: signal_trading signal_trading_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_trading
    ADD CONSTRAINT signal_trading_pkey PRIMARY KEY (signal_id);


--
-- Name: serie_prix uq_serie_prix; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.serie_prix
    ADD CONSTRAINT uq_serie_prix UNIQUE (instrument_id, plateforme_id, date_heure, pas_temps);


--
-- Name: idx_activite_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_activite_datetime ON public.activite_marche USING btree (date_heure);


--
-- Name: idx_activite_plateforme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_activite_plateforme ON public.activite_marche USING btree (plateforme_id);


--
-- Name: idx_indicateur_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicateur_datetime ON public.indicateur_technique USING btree (date_heure);


--
-- Name: idx_indicateur_plateforme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_indicateur_plateforme ON public.indicateur_technique USING btree (plateforme_id);


--
-- Name: idx_prediction_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prediction_datetime ON public.prediction_modele USING btree (date_heure);


--
-- Name: idx_serie_prix_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_serie_prix_datetime ON public.serie_prix USING btree (date_heure);


--
-- Name: idx_serie_prix_instrument; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_serie_prix_instrument ON public.serie_prix USING btree (instrument_id);


--
-- Name: idx_serie_prix_plateforme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_serie_prix_plateforme ON public.serie_prix USING btree (plateforme_id);


--
-- Name: idx_signal_datetime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_signal_datetime ON public.signal_trading USING btree (date_heure);


--
-- Name: activite_marche fk_activite_instrument; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activite_marche
    ADD CONSTRAINT fk_activite_instrument FOREIGN KEY (instrument_id) REFERENCES public.instrument_marche(instrument_id) ON DELETE CASCADE;


--
-- Name: activite_marche fk_activite_plateforme; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activite_marche
    ADD CONSTRAINT fk_activite_plateforme FOREIGN KEY (plateforme_id) REFERENCES public.plateforme(plateforme_id) ON DELETE CASCADE;


--
-- Name: indicateur_technique fk_indicateur_instrument; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicateur_technique
    ADD CONSTRAINT fk_indicateur_instrument FOREIGN KEY (instrument_id) REFERENCES public.instrument_marche(instrument_id) ON DELETE CASCADE;


--
-- Name: indicateur_technique fk_indicateur_plateforme; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicateur_technique
    ADD CONSTRAINT fk_indicateur_plateforme FOREIGN KEY (plateforme_id) REFERENCES public.plateforme(plateforme_id) ON DELETE CASCADE;


--
-- Name: serie_prix fk_serie_prix_instrument; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.serie_prix
    ADD CONSTRAINT fk_serie_prix_instrument FOREIGN KEY (instrument_id) REFERENCES public.instrument_marche(instrument_id) ON DELETE CASCADE;


--
-- Name: serie_prix fk_serie_prix_plateforme; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.serie_prix
    ADD CONSTRAINT fk_serie_prix_plateforme FOREIGN KEY (plateforme_id) REFERENCES public.plateforme(plateforme_id) ON DELETE CASCADE;


--
-- Name: signal_trading fk_signal_evenement; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_trading
    ADD CONSTRAINT fk_signal_evenement FOREIGN KEY (evenement_id) REFERENCES public.evenement_marche(evenement_id) ON DELETE SET NULL;


--
-- Name: signal_trading fk_signal_instrument; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_trading
    ADD CONSTRAINT fk_signal_instrument FOREIGN KEY (instrument_id) REFERENCES public.instrument_marche(instrument_id) ON DELETE CASCADE;


--
-- Name: signal_trading fk_signal_prediction; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_trading
    ADD CONSTRAINT fk_signal_prediction FOREIGN KEY (prediction_id) REFERENCES public.prediction_modele(prediction_id) ON DELETE SET NULL;


--
-- Name: signal_trading fk_signal_sentiment; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_trading
    ADD CONSTRAINT fk_signal_sentiment FOREIGN KEY (sentiment_id) REFERENCES public.sentiment_social(sentiment_id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict 5gz50g4EKm4NnU4QWO5EdBwxXqaMi6DX3bUUdGCK82u23NbcZLIa8Fx3i1IxO43

