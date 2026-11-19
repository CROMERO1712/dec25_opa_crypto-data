--
-- PostgreSQL database dump
--

\restrict 2fAQvPlPr6yCvSRPJnuzTj4uoLLSqZhvoPLwY4sMfkZbpoglGvF73Obq4XVMmkR

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

--
-- Data for Name: instrument_marche; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.instrument_marche VALUES (1, 'BTC-USD', 'Bitcoin', 'USD');
INSERT INTO public.instrument_marche VALUES (2, 'ETH-USD', 'Ethereum', 'USD');
INSERT INTO public.instrument_marche VALUES (4, 'BTC-USD', 'Bitcoin', 'USD');
INSERT INTO public.instrument_marche VALUES (3, 'SOL-USD', 'Solana', 'USD');


--
-- Data for Name: plateforme; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.plateforme VALUES (1, 'Binance');
INSERT INTO public.plateforme VALUES (2, 'Coinbase');


--
-- Name: instrument_marche_instrument_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.instrument_marche_instrument_id_seq', 4, true);


--
-- Name: plateforme_plateforme_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.plateforme_plateforme_id_seq', 1, false);


--
-- PostgreSQL database dump complete
--

\unrestrict 2fAQvPlPr6yCvSRPJnuzTj4uoLLSqZhvoPLwY4sMfkZbpoglGvF73Obq4XVMmkR

