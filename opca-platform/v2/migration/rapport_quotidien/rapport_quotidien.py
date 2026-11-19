#!/usr/bin/env python3
"""Rapport quotidien de la plateforme OPCA, écrit dans ~/projet/rapport_quotidien.

Rassemble, en lecture seule : le contrôle check_opca.sh, les ressources de la VM,
les exécutions Airflow des dernières 24 h, la fraîcheur des données et les résultats
réels des modèles (vue v_prediction_oos_eval). Écrit deux fichiers par passage :
  rapport_AAAA-MM-JJ_matin.html / .txt   (07:00 heure de Paris, après RF et sauvegarde)
  rapport_AAAA-MM-JJ_soir.html  / .txt   (22:30 heure de Paris)
et met à jour dernier_rapport.html / .txt. Les rapports de plus de 60 jours sont effacés.

Usage :
  python3 rapport_quotidien.py           # créneau déduit de l'heure (matin avant 15 h, soir après)
  python3 rapport_quotidien.py --test    # écrit seulement dernier_rapport.*
"""
import html
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DOSSIER = Path.home() / "projet/rapport_quotidien"
CONSERVATION_JOURS = 60
CHECK = Path.home() / "projet/v2/checks/check_opca.sh"
PG_AIRFLOW = "opca_airflow-airflow-postgres-1"
PG_OPCA = "opca_pg_v2"


def sh(cmd, timeout=120):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def sql_airflow(requete):
    r = subprocess.run(["docker", "exec", "-i", PG_AIRFLOW, "psql", "-U", "airflow", "-d", "airflow",
                        "-At", "-F", "|"], input=requete, capture_output=True, text=True, timeout=60)
    return [l.split("|") for l in r.stdout.strip().splitlines() if l]


def sql_opca(requete):
    r = subprocess.run(["docker", "exec", "-i", PG_OPCA, "sh", "-c",
                        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "|"'],
                       input=requete, capture_output=True, text=True, timeout=60)
    return [l.split("|") for l in r.stdout.strip().splitlines() if l]


def en_texte(corps):
    t = re.sub(r"</t[dh]>", " | ", corps)
    t = re.sub(r"<(tr|p|h2|h3|li)[^>]*>", "\n", t)
    t = re.sub(r"<li>", "\n- ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", t).strip() + "\n"


def tableau(entetes, lignes):
    th = "".join(f'<th style="text-align:left;padding:4px 10px;border-bottom:1px solid #ccc">{html.escape(e)}</th>' for e in entetes)
    corps = ""
    for l in lignes:
        corps += "<tr>" + "".join(f'<td style="padding:4px 10px;border-bottom:1px solid #eee">{html.escape(str(c))}</td>' for c in l) + "</tr>"
    return f'<table style="border-collapse:collapse;font-size:14px">{"<tr>" + th + "</tr>"}{corps}</table>'


def main():
    test = "--test" in sys.argv
    maintenant = datetime.now(timezone.utc)
    paris = maintenant.astimezone(ZoneInfo("Europe/Paris"))
    creneau = "matin" if paris.hour < 15 else "soir"
    alertes = []

    # 1. Contrôle complet
    sortie_check = sh(f"bash {CHECK}", timeout=180)
    resume_check = next((l for l in sortie_check.splitlines() if "Résumé" in l), "Résumé introuvable")
    anomalies = [l for l in sortie_check.splitlines() if l.startswith(("[WARN]", "[FAIL]", "[ÉCHEC]"))]
    alertes += anomalies
    if "Résumé introuvable" in resume_check:
        alertes.append("le script check_opca.sh n'a pas produit de résumé")

    # 2. Ressources
    disque = sh("df -h / | tail -1 | awk '{print $5\" utilisés, \"$4\" libres\"}'")
    disque_pct = int(sh("df / | tail -1 | awk '{print $5}'").rstrip("%") or 0)
    memoire = sh("free -m | awk '/Mem:/{print $7\" Mo disponibles sur \"$2\" Mo\"}'")
    charge = sh("cut -d' ' -f1-3 /proc/loadavg")
    conteneurs = sh("docker ps --format '{{.Names}}' | wc -l")
    stats = [l.split("\t") for l in sh("docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' | sort").splitlines()]
    if disque_pct >= 80:
        alertes.append(f"disque à {disque_pct} %")
    for nom, _, _, pct in stats:
        if float(pct.rstrip("%") or 0) >= 85:
            alertes.append(f"{nom} utilise {pct} de sa limite mémoire")

    # 3. Airflow sur 24 h
    runs = sql_airflow("""select dag_id, state, count(*) from dag_run
        where start_date > now() - interval '24 hours' group by 1, 2 order by 1, 2;""")
    for dag, etat, n in runs:
        if etat not in ("success", "running", "queued"):
            alertes.append(f"DAG {dag} : {n} exécution(s) en état {etat} sur 24 h")
    rf = sql_airflow("""select state, to_char(start_date, 'DD/MM HH24:MI'),
        to_char(end_date - start_date, 'HH24:MI:SS') from dag_run
        where dag_id = 'opca_random_forest_24h' order by start_date desc limit 1;""")
    if not rf or rf[0][0] != "success":
        alertes.append(f"dernier Random Forest : {rf[0][0] if rf else 'aucune exécution'}")
    rf_age = sql_airflow("""select extract(epoch from now() - max(start_date))/3600 from dag_run
        where dag_id = 'opca_random_forest_24h' and state = 'success';""")
    if rf_age and rf_age[0][0] and float(rf_age[0][0]) > 26:
        alertes.append("aucun Random Forest réussi depuis plus de 26 h")

    # 4. Fraîcheur des données
    fraicheur = sql_opca("""
        select 'serie_prix ' || instrument_id || '/' || plateforme_id, to_char(max(date_heure), 'DD/MM HH24:MI'),
               count(*) filter (where date_heure > now() at time zone 'utc' - interval '24 hours')
        from serie_prix group by instrument_id, plateforme_id
        union all
        select 'activite_marche ' || instrument_id, to_char(max(date_heure), 'DD/MM HH24:MI'),
               count(*) filter (where date_heure > now() at time zone 'utc' - interval '24 hours')
        from activite_marche group by instrument_id
        order by 1;""")

    # 5. Modèles (prévisions comparées au prix réel)
    oos = sql_opca("""
        select horizon_prediction,
               count(*) filter (where prix_reel is not null),
               round(avg(abs(prix_predit - prix_reel)) filter (where prix_reel is not null), 0),
               round(avg(abs(prix_actuel - prix_reel)) filter (where prix_reel is not null), 0),
               round(100.0 * avg(case when sign(variation_predite) = sign(variation_reelle) then 1 else 0 end)
                     filter (where prix_reel is not null), 1)
        from v_prediction_oos_eval group by 1 order by 1;""")
    oos_24h = sql_opca("""
        select count(*), round(avg(abs(prix_predit - prix_reel)), 0), round(avg(abs(prix_actuel - prix_reel)), 0)
        from v_prediction_oos_eval
        where horizon_prediction not like '%RF%' and prix_reel is not null
          and date_cible > now() at time zone 'utc' - interval '24 hours';""")
    rf_prev = sql_opca("""
        select to_char(date_reference, 'DD/MM HH24:MI'), to_char(date_cible, 'DD/MM HH24:MI'),
               round(prix_actuel, 0), round(prix_predit, 0), coalesce(round(prix_reel, 0)::text, 'à venir'),
               coalesce(round(prix_predit - prix_reel, 0)::text, '')
        from v_prediction_oos_eval where horizon_prediction like '%RF%'
        order by date_reference desc limit 5;""")

    # Rapport
    etat = "OK" if not alertes else f"{len(alertes)} point(s) d'attention"
    sujet = f"[OPCA] Rapport du {paris:%d/%m/%Y} ({creneau}) : {etat}"
    couleur = "#1a7f37" if not alertes else "#b35900"
    bloc_alertes = ("<p>Aucun point d'attention.</p>" if not alertes else
                    "<ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in alertes) + "</ul>")
    xgb_24h = ""
    if oos_24h and oos_24h[0][0] != "0":
        n, mae, naif = oos_24h[0]
        xgb_24h = f"<p>XGBoost sur les dernières 24 h : {n} prévisions, erreur moyenne {mae} $ (naïve : {naif} $).</p>"

    corps = f"""<div style="font-family:Arial,sans-serif;color:#14213D;max-width:820px">
<h2 style="margin-bottom:4px">Rapport OPCA du {paris:%d/%m/%Y} ({creneau})</h2>
<p style="margin-top:0;color:#5B6676">{paris:%d/%m/%Y %H:%M} heure de Paris ({maintenant:%H:%M} UTC) · VM 51.44.254.88</p>
<p style="font-size:18px;font-weight:bold;color:{couleur}">{html.escape(etat)} · {html.escape(resume_check.strip("= "))}</p>
<h3>Points d'attention</h3>{bloc_alertes}
<h3>Ressources</h3>
<p>Disque : {html.escape(disque)} · Mémoire : {html.escape(memoire)} · Charge : {html.escape(charge)} · {conteneurs} conteneurs actifs</p>
{tableau(["Conteneur", "CPU", "Mémoire", "% limite"], stats)}
<h3>Airflow (24 h)</h3>
{tableau(["DAG", "État", "Exécutions"], runs)}
<p>Dernier Random Forest : {html.escape(" · ".join(rf[0]) if rf else "aucun")}</p>
<h3>Données</h3>
{tableau(["Table / série", "Dernière bougie (UTC)", "Lignes sur 24 h"], fraicheur)}
<h3>Modèles : prévisions comparées au prix réel</h3>
{tableau(["Modèle", "Prévisions évaluées", "Erreur moy. ($)", "Erreur naïve ($)", "Bonne direction (%)"], oos)}
{xgb_24h}
<p>Dernières prévisions Random Forest :</p>
{tableau(["Faite le", "Pour le", "Prix actuel", "Prédit", "Réel", "Écart"], rf_prev)}
<p style="color:#5B6676;font-size:12px;margin-top:24px">Généré automatiquement par ~/projet/rapport_quotidien/rapport_quotidien.py (07:00 et 22:30 heure de Paris). Lecture seule : rien n'est modifié sur la VM.</p>
</div>"""

    page = f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{html.escape(sujet)}</title></head><body>{corps}</body></html>'
    texte = f"{sujet}\n\n" + en_texte(corps)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    noms = ["dernier_rapport"] if test else [f"rapport_{paris:%Y-%m-%d}_{creneau}", "dernier_rapport"]
    for nom in noms:
        (DOSSIER / f"{nom}.html").write_text(page)
        (DOSSIER / f"{nom}.txt").write_text(texte)

    limite = time.time() - CONSERVATION_JOURS * 86400
    for f in DOSSIER.glob("rapport_*.*"):
        if f.stat().st_mtime < limite:
            f.unlink()
    print(f"{maintenant:%F %T} UTC {sujet} -> {DOSSIER / noms[0]}.html")


if __name__ == "__main__":
    main()
