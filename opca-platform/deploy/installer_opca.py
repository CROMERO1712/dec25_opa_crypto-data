#!/usr/bin/env python3
"""
Installation complète de la plateforme OPCA sur une VM Ubuntu neuve (22.04 ou 24.04).

Reproduit la VM de production :
  - base PostgreSQL opca_db (conteneur opca_pg_v2, publiée sur 172.17.0.1:5433 seulement) ;
  - Adminer (127.0.0.1:8085, par tunnel SSH), API FastAPI (:8003), Streamlit (:8503) ;
  - Airflow 2.9.3 (:8081) : DAG horaire v2 (9 tâches) et Random Forest 24 h (02:15 UTC) ;
  - Prometheus, node-exporter, cAdvisor et Grafana (:3001) ;
  - cron : contrôles horaires, sauvegarde nocturne de la base, rapports à 07:00 et 22:30 (Paris).

Le script ne supprime et n'écrase jamais rien : chaque étape regarde l'existant et passe si
c'est déjà fait. On peut donc le relancer sans risque après une erreur.

Mots de passe : générés au hasard quand les fichiers .env n'existent pas, jamais affichés,
puis résumés dans ~/projet/ACCES_EQUIPE.md (droits 600). Pour garder ceux d'une autre VM,
copier avant de lancer ses fichiers pg.env, api_v2.env, grafana_v2.env, grafana_ro.env dans
~/projet/v2/ et son .env dans ~/projet/plateforme/opca-platform/.

Usage (en utilisateur normal, membre du groupe docker, avec sudo) :
  python3 installer_opca.py                          # installation complète, base vide
  python3 installer_opca.py --dump opca_db_X.dump    # idem en restaurant une sauvegarde
  python3 installer_opca.py --simulation             # montre ce qui serait fait, sans rien modifier
  python3 installer_opca.py --etapes base,airflow    # seulement certaines étapes
  python3 installer_opca.py --installer-docker       # installe aussi Docker s'il est absent
"""
import argparse
import getpass
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DEPOT = "https://github.com/CROMERO1712/dec25_opa_crypto-data.git"
BRANCHE = "vm-production-20261104"
HOME = Path.home()
UTILISATEUR = getpass.getuser()
PROJET = HOME / "projet"
PLATEFORME = PROJET / "plateforme"          # clone du dépôt
OPCA = PLATEFORME / "opca-platform"
V2 = PROJET / "v2"                          # lien vers opca-platform/v2 (chemins attendus par les scripts)
DEPLOY = OPCA / "deploy"
GW = "172.17.0.1"                           # passerelle Docker : base et Prometheus n'écoutent que là
PG = "opca_pg_v2"
SCHED = "opca_airflow-airflow-scheduler-1"
AIRFLOW_UID = "50000"
DAG_ACTIFS = ["opca_pipeline_horaire_v2", "opca_random_forest_24h"]
DAG_EN_PAUSE = []                           # l'ancien pipeline v1 a été retiré le 04/11/2026
IMAGES = [("Dockerfile.api", "projet_test-api"),
          ("Dockerfile.dashboard", "projet_test-dashboard"),
          ("Dockerfile.ml", "opca-platform-ml")]   # image du Random Forest (lancer_rf.sh)
PORTS = {8003: "API", 8503: "Streamlit", 3001: "Grafana", 8081: "Airflow", 8085: "Adminer"}
# chemins de la VM d'origine écrits en dur dans ces fichiers, adaptés si l'utilisateur n'est pas ubuntu
FICHIERS_CHEMINS = ["v2/compose/docker-compose.yaml", "v2/compose/docker-compose.grafana.yaml",
                    "v2/monitoring/docker-compose.monitoring.yaml", "v2/rf_v2/lancer_rf.sh",
                    "airflow/dags/opca_random_forest_24h.py"]
CRON = [
    "25 * * * * $HOME/projet/v2/checks/check_opca.sh >> $HOME/projet/v2/checks/check.log 2>&1",
    "17 3 * * * $HOME/projet/v2/checks/backup_v2.sh >> $HOME/projet/v2/checks/backup.log 2>&1",
    # cron est en UTC : deux lignes par rapport, seule celle qui tombe à l'heure de Paris s'exécute
    '0 5,6 * * * [ "$(TZ=Europe/Paris date +\\%H)" = 07 ] && /usr/bin/python3 '
    "$HOME/projet/rapport_quotidien/rapport_quotidien.py >> $HOME/projet/rapport_quotidien/rapport.log 2>&1",
    '30 20,21 * * * [ "$(TZ=Europe/Paris date +\\%H)" = 22 ] && /usr/bin/python3 '
    "$HOME/projet/rapport_quotidien/rapport_quotidien.py >> $HOME/projet/rapport_quotidien/rapport.log 2>&1",
]
SIMULATION = False
AVERTISSEMENTS = []


class Erreur(Exception):
    pass


# ---------------------------------------------------------------- outils

def titre(texte):
    print(f"\n=== {texte} ===")


def info(texte):
    print(f"  - {texte}")


def avertir(texte):
    AVERTISSEMENTS.append(texte)
    print(f"  ! {texte}")


def agir(description):
    """True si on doit vraiment faire l'action ; en simulation, l'affiche seulement."""
    if SIMULATION:
        print(f"    [simulation] {description}")
        return False
    info(description)
    return True


def run(cmd, *, lecture=False, entree=None, cwd=None, verifier=True, sudo=False, afficher=False):
    """Lance une commande. En simulation, seules les commandes de lecture s'exécutent.
    Les secrets passent toujours par l'entrée standard, jamais sur la ligne de commande."""
    cmd = [str(c) for c in cmd]
    if sudo and os.geteuid() != 0:
        cmd = ["sudo"] + cmd
    if SIMULATION and not lecture:
        print("    [simulation]", " ".join(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    r = subprocess.run(cmd, input=entree, cwd=cwd, text=True,
                       capture_output=not afficher)
    if verifier and r.returncode != 0:
        detail = "" if afficher else (r.stderr or r.stdout or "").strip()[-2000:]
        raise Erreur(f"échec de : {' '.join(cmd)}\n{detail}")
    return r


def ok(cmd, **kw):
    return run(cmd, lecture=True, verifier=False, **kw).returncode == 0


def attendre(test, quoi, delai=300, pas=5):
    if SIMULATION:
        return
    fin = time.time() + delai
    while time.time() < fin:
        if test():
            info(f"{quoi} : prêt")
            return
        time.sleep(pas)
    raise Erreur(f"{quoi} : toujours pas prêt après {delai} s")


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status < 500
    except Exception:
        return False


def conteneur_existe(nom):
    return ok(["docker", "inspect", nom])


def conteneur_actif(nom):
    r = run(["docker", "inspect", "-f", "{{.State.Running}}", nom], lecture=True, verifier=False)
    return r.stdout.strip() == "true"


def compose_up(fichier, dossier, conteneurs, projet=None):
    """docker compose up -d, sauf si tous les conteneurs tournent déjà : on ne recrée jamais
    un service en marche (ceux de la production ont été lancés depuis d'autres dossiers)."""
    if all(conteneur_actif(c) for c in conteneurs):
        info(f"{', '.join(conteneurs)} : tournent déjà")
        return
    run(["docker", "compose"] + (["-p", projet] if projet else []) + ["-f", fichier, "up", "-d"],
        cwd=dossier, afficher=True)


def lire_env(chemin):
    valeurs = {}
    if chemin.exists():
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, val = ligne.split("=", 1)
                valeurs[cle.strip()] = val.strip().strip("'\"")
    return valeurs


def ecrire_secret(chemin, texte):
    """Écrit un fichier lisible par le seul propriétaire (créé directement en 600)."""
    if not agir(f"création de {chemin} (droits 600)"):
        return
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texte)


def mdp():
    return secrets.token_urlsafe(24)   # lettres, chiffres, - et _ : sans souci dans .env, SQL ou JSON


def pg_env():
    env = lire_env(V2 / "pg.env")
    if not env.get("POSTGRES_PASSWORD") and SIMULATION:
        return {"POSTGRES_USER": "opca_app", "POSTGRES_DB": "opca_db", "POSTGRES_PASSWORD": "(simulation)"}
    if not env.get("POSTGRES_PASSWORD"):
        raise Erreur(f"{V2 / 'pg.env'} absent ou incomplet : lancer d'abord l'étape secrets")
    return env


def psql(sql, lecture=False):
    env = pg_env()
    return run(["docker", "exec", "-i", PG, "psql", "-v", "ON_ERROR_STOP=1", "-qAt",
                "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"]], entree=sql, lecture=lecture)


def json_airflow(arguments):
    """Sortie JSON d'une commande airflow du scheduler ([] si illisible ; Airflow peut écrire
    des avertissements avant le JSON)."""
    sortie = run(["docker", "exec", SCHED, "airflow"] + arguments, lecture=True, verifier=False).stdout
    debut = sortie.find("[")
    try:
        return json.loads(sortie[debut:]) if debut >= 0 else []
    except ValueError:
        return []


def sql_texte(valeur):
    return "'" + valeur.replace("'", "''") + "'"


# ---------------------------------------------------------------- étapes

def etape_verifier(args):
    titre("1. Vérification de la machine")
    os_release = Path("/etc/os-release").read_text() if Path("/etc/os-release").exists() else ""
    nom_os = next((l.split("=", 1)[1].strip('"') for l in os_release.splitlines()
                   if l.startswith("PRETTY_NAME=")), "inconnu")
    info(f"système : {nom_os}, utilisateur {UTILISATEUR}, dossier {PROJET}")
    if "ubuntu" not in os_release.lower():
        avertir("script prévu pour Ubuntu 22.04/24.04 (la production est en 22.04)")
    if os.geteuid() == 0:
        raise Erreur("ne pas lancer en root : utiliser l'utilisateur qui fera tourner la plateforme")
    if not shutil.which("git"):
        run(["apt-get", "update", "-q"], sudo=True, afficher=True)
        run(["apt-get", "install", "-y", "git"], sudo=True, afficher=True)

    if not shutil.which("docker"):
        if not args.installer_docker:
            raise Erreur("Docker absent : relancer avec --installer-docker, "
                         "ou l'installer (https://docs.docker.com/engine/install/ubuntu/)")
        run(["sh", "-c", "curl -fsSL https://get.docker.com | sudo sh"], afficher=True)
        run(["usermod", "-aG", "docker", UTILISATEUR], sudo=True)
        raise Erreur("Docker vient d'être installé : se déconnecter, se reconnecter "
                     "(pour le groupe docker) puis relancer le script")
    if not ok(["docker", "info"]):
        raise Erreur(f"Docker ne répond pas pour {UTILISATEUR} : "
                     f"sudo usermod -aG docker {UTILISATEUR}, puis se reconnecter")
    if not ok(["docker", "compose", "version"]):
        raise Erreur("plugin « docker compose » absent (paquet docker-compose-plugin)")
    info(run(["docker", "--version"], lecture=True).stdout.strip())
    if GW not in run(["ip", "-4", "addr", "show", "docker0"], lecture=True, verifier=False).stdout:
        raise Erreur(f"l'interface docker0 n'a pas l'adresse {GW} : la base et Prometheus "
                     "y sont publiés, vérifier la configuration réseau de Docker")

    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    libre = shutil.disk_usage(HOME).free / 2**30
    info(f"mémoire {ram:.1f} Go, disque libre {libre:.0f} Go, {os.cpu_count()} processeur(s)")
    if ram < 7:
        avertir("moins de 7 Go de mémoire : le Random Forest (1,3 Go) et Airflow risquent de manquer")
    if libre < 15:
        avertir("moins de 15 Go libres : images (~6 Go) + base + sauvegardes")
    ecoute = run(["ss", "-ltnH"], lecture=True, verifier=False).stdout
    for port, nom in PORTS.items():
        if f":{port} " in ecoute:
            avertir(f"port {port} ({nom}) déjà occupé (normal si la plateforme est déjà installée)")
    if not ok(["systemctl", "is-active", "--quiet", "ssh"]):
        avertir("le serveur SSH ne tourne pas : le DAG Random Forest en a besoin (sudo apt install openssh-server)")


def etape_code(args):
    titre("2. Code de la plateforme")
    if (PLATEFORME / ".git").exists():
        branche = run(["git", "-C", PLATEFORME, "rev-parse", "--abbrev-ref", "HEAD"], lecture=True).stdout.strip()
        info(f"dépôt déjà présent dans {PLATEFORME} (branche {branche}) : conservé tel quel, sans git pull")
    elif PLATEFORME.exists() and any(PLATEFORME.iterdir()):
        raise Erreur(f"{PLATEFORME} existe et n'est pas un dépôt git : le déplacer avant de relancer")
    else:
        if agir(f"clonage de {DEPOT} (branche {args.branche})"):
            PROJET.mkdir(exist_ok=True)
        run(["git", "clone", "--branch", args.branche, args.depot, PLATEFORME], afficher=True)

    if V2.is_symlink() or V2.exists():
        info(f"{V2} déjà présent : conservé")
    elif agir(f"lien {V2} -> {OPCA / 'v2'}"):
        V2.symlink_to(OPCA / "v2")

    if str(HOME) != "/home/ubuntu" or UTILISATEUR != "ubuntu":
        for rel in FICHIERS_CHEMINS:
            f = OPCA / rel
            if not f.exists():
                continue
            texte = f.read_text(encoding="utf-8")
            nouveau = texte.replace("/home/ubuntu/", f"{HOME}/").replace("ubuntu@172.17.0.1", f"{UTILISATEUR}@{GW}")
            if nouveau != texte and agir(f"adaptation des chemins /home/ubuntu -> {HOME} dans {rel}"):
                f.write_text(nouveau, encoding="utf-8")

    for f in list((OPCA / "v2").rglob("*.sh")) + [OPCA / "v2/rapport_quotidien/rapport_quotidien.py"]:
        if f.exists() and not os.access(f, os.X_OK) and agir(f"rendre exécutable {f.relative_to(OPCA)}"):
            f.chmod(f.stat().st_mode | 0o755)


def etape_secrets(args):
    titre("3. Fichiers de configuration et mots de passe")
    noms = ["pg.env", "api_v2.env", "grafana_v2.env", "grafana_ro.env", "opca_admin.env"]
    e = {n: lire_env(V2 / n) for n in noms}
    af = lire_env(OPCA / ".env")
    # on réutilise ce qui existe déjà pour que tous les fichiers restent cohérents entre eux
    pw_pg = e["pg.env"].get("POSTGRES_PASSWORD") or e["api_v2.env"].get("DB_PASSWORD") or mdp()
    pw_ro = e["grafana_ro.env"].get("GRAFANA_RO_PASSWORD") or e["grafana_v2.env"].get("GRAFANA_DB_PASSWORD") or mdp()
    pw_gf = e["grafana_v2.env"].get("GF_SECURITY_ADMIN_PASSWORD") or mdp()
    pw_admin = e["opca_admin.env"].get("OPCA_ADMIN_PASSWORD") or mdp()
    pw_af = af.get("AIRFLOW_ADMIN_PASSWORD") or mdp()
    cle_af = af.get("AIRFLOW_SECRET_KEY") or secrets.token_hex(32)

    fichiers = {
        V2 / "pg.env": f"POSTGRES_USER=opca_app\nPOSTGRES_DB=opca_db\nPOSTGRES_PASSWORD={pw_pg}\n",
        V2 / "api_v2.env": f"DB_HOST={GW}\nDB_PORT=5433\nDB_NAME=opca_db\nDB_USER=opca_app\nDB_PASSWORD={pw_pg}\n",
        V2 / "grafana_v2.env": (f"GF_SECURITY_ADMIN_USER=admin\nGF_SECURITY_ADMIN_PASSWORD={pw_gf}\n"
                                f"GRAFANA_DB_USER=grafana_ro\nGRAFANA_DB_PASSWORD={pw_ro}\n"),
        V2 / "grafana_ro.env": f"GRAFANA_RO_PASSWORD={pw_ro}\n",
        V2 / "opca_admin.env": f"# compte PostgreSQL des humains (Adminer)\nOPCA_ADMIN_PASSWORD={pw_admin}\n",
        # DB_* : variables historiques (le pipeline v1 qui les lisait est retiré) ; le DAG v2 lit les variables Airflow opca_v2_db_*
        OPCA / ".env": (f"DB_HOST={GW}\nDB_PORT=5433\nDB_NAME=opca_db\nDB_USER=opca_app\nDB_PASSWORD={pw_pg}\n"
                        f"AIRFLOW_UID={AIRFLOW_UID}\nAIRFLOW_ADMIN_PASSWORD={pw_af}\nAIRFLOW_SECRET_KEY={cle_af}\n"),
    }
    if e["pg.env"] and not e["opca_admin.env"]:
        # base déjà configurée ailleurs : le rôle opca_admin a son propre mot de passe, on n'en invente pas
        del fichiers[V2 / "opca_admin.env"]
    for chemin, texte in fichiers.items():
        if chemin.exists():
            info(f"{chemin} déjà présent : conservé")
        else:
            ecrire_secret(chemin, texte)
    if e["pg.env"] and e["api_v2.env"] and e["pg.env"].get("POSTGRES_PASSWORD") != e["api_v2.env"].get("DB_PASSWORD"):
        avertir("pg.env et api_v2.env n'ont pas le même mot de passe : l'API ne pourra pas se connecter")

    acces = PROJET / "ACCES_EQUIPE.md"
    if acces.exists():
        info(f"{acces} déjà présent : conservé")
    else:
        ecrire_secret(acces, f"""# Accès plateforme OPCA (fichier privé, droits 600 : ne jamais le copier dans git)

| Service | Adresse | Compte | Mot de passe |
| --- | --- | --- | --- |
| Airflow | http://<ip>:8081 | admin | {pw_af} |
| Grafana | http://<ip>:3001 | admin | {pw_gf} |
| API | http://<ip>:8003/docs | - | - |
| Streamlit | http://<ip>:8503 | - | - |
| Adminer (tunnel : ssh -L 8085:127.0.0.1:8085) | http://localhost:8085, serveur {GW}:5433, base opca_db | opca_admin | {pw_admin} |
| PostgreSQL (application) | {GW}:5433 / opca_db | opca_app | {pw_pg} |
| PostgreSQL (lecture seule) | {GW}:5433 / opca_db | grafana_ro | {pw_ro} |
""")


def etape_images(args):
    titre("4. Images Docker")
    for dockerfile, tag in IMAGES:
        if ok(["docker", "image", "inspect", tag]) and not args.reconstruire:
            info(f"image {tag} déjà présente")
        else:
            info(f"construction de {tag} ({dockerfile})")
            run(["docker", "build", "-f", dockerfile, "-t", tag, "."], cwd=OPCA, afficher=True)
    if ok(["docker", "image", "inspect", "opca-airflow:2.9.3"]) and not args.reconstruire:
        info("image opca-airflow:2.9.3 déjà présente")
    else:
        info("construction de opca-airflow:2.9.3 (Airflow + venvs collecte et ML, ~2 Go)")
        run(["docker", "compose", "-p", "opca_airflow", "-f", "docker-compose.airflow.yaml", "build"],
            cwd=OPCA, afficher=True)
    for image in ["postgres:16-alpine", "adminer:4.8.1"]:
        if not ok(["docker", "image", "inspect", image]):
            run(["docker", "pull", image], afficher=True)


def etape_base(args):
    titre("5. Base PostgreSQL opca_db")
    env = pg_env()
    if not conteneur_existe(PG):
        run(["docker", "volume", "create", "opca_pg_v2_data"])
        run(["docker", "run", "-d", "--name", PG, "--restart", "unless-stopped", "--memory", "512m",
             "--env-file", V2 / "pg.env", "-p", f"{GW}:5433:5432",
             "-v", "opca_pg_v2_data:/var/lib/postgresql/data", "postgres:16-alpine"])
    elif not conteneur_actif(PG):
        run(["docker", "start", PG])
    else:
        info(f"{PG} tourne déjà")
    # par TCP : pendant sa première initialisation, PostgreSQL n'écoute que sur sa socket locale
    attendre(lambda: ok(["docker", "exec", PG, "pg_isready", "-h", "127.0.0.1", "-U", env["POSTGRES_USER"]]),
             "PostgreSQL", delai=120, pas=3)

    # rôles créés seulement s'ils manquent : un mot de passe existant n'est jamais modifié
    pw_ro = lire_env(V2 / "grafana_ro.env").get("GRAFANA_RO_PASSWORD", "")
    pw_admin = lire_env(V2 / "opca_admin.env").get("OPCA_ADMIN_PASSWORD", "")
    psql(f"""\\set pw_ro {sql_texte(pw_ro)}
\\set pw_admin {sql_texte(pw_admin)}
SELECT format('CREATE ROLE grafana_ro LOGIN PASSWORD %L', :'pw_ro')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') \\gexec
SELECT format('CREATE ROLE opca_admin LOGIN SUPERUSER PASSWORD %L', :'pw_admin')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'opca_admin') \\gexec
""")
    info("rôles opca_app, grafana_ro (lecture seule) et opca_admin en place")

    if SIMULATION and not conteneur_existe(PG):
        nb = 0
    else:
        nb = int(psql("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'",
                      lecture=True).stdout.strip() or 0)
    if args.dump:
        dump = Path(args.dump).expanduser().resolve()
        if not dump.is_file():
            raise Erreur(f"sauvegarde introuvable : {dump}")
        if nb:
            raise Erreur(f"la base contient déjà {nb} tables : restauration refusée pour ne rien écraser")
        empreinte = dump.with_name(dump.name + ".sha256")
        if empreinte.exists():
            attendu = empreinte.read_text().split()[0]
            h = hashlib.sha256()
            with open(dump, "rb") as f:
                for bloc in iter(lambda: f.read(1 << 20), b""):
                    h.update(bloc)
            if h.hexdigest() != attendu:
                raise Erreur(f"{dump.name} : empreinte SHA-256 différente du fichier .sha256 (fichier abîmé ?)")
            info("empreinte SHA-256 de la sauvegarde vérifiée")
        info(f"restauration de {dump.name} ({dump.stat().st_size / 2**20:.0f} Mo)")
        run(["docker", "cp", dump, f"{PG}:/tmp/restauration.dump"])
        r = run(["docker", "exec", PG, "pg_restore", "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"],
                 "--no-owner", "/tmp/restauration.dump"], verifier=False)
        run(["docker", "exec", PG, "rm", "-f", "/tmp/restauration.dump"])
        if r.returncode:
            avertir("pg_restore a signalé des erreurs (souvent bénignes, ex. schéma public déjà présent) : "
                    + (r.stderr.strip().splitlines() or [""])[-1])
    elif nb == 0:
        info("base vide : création du schéma (11 tables et vues) et des données de référence")
        psql((DEPLOY / "schema_opca_db.sql").read_text(encoding="utf-8"))
        psql((DEPLOY / "donnees_reference.sql").read_text(encoding="utf-8"))
    else:
        info(f"base déjà initialisée ({nb} tables) : rien à faire")
    if not SIMULATION:
        for t in ["serie_prix", "prediction_modele", "prediction_oos", "sentiment_social"]:
            n = psql(f"SELECT count(*) FROM {t}", lecture=True).stdout.strip()
            info(f"{t} : {n} lignes")


def etape_adminer(args):
    titre("6. Adminer (accès humain à la base, par tunnel SSH seulement)")
    if conteneur_existe("opca_adminer_v2"):
        if not conteneur_actif("opca_adminer_v2"):
            run(["docker", "start", "opca_adminer_v2"])
        info("opca_adminer_v2 déjà présent")
        return
    run(["docker", "run", "-d", "--name", "opca_adminer_v2", "--restart", "unless-stopped",
         "--memory", "128m", "-p", "127.0.0.1:8085:8080", "adminer:4.8.1"])


def etape_api(args):
    titre("7. API et tableau de bord Streamlit")
    compose_up("docker-compose.yaml", V2 / "compose", ["opca_api_v2", "opca_dashboard_v2"])
    attendre(lambda: http_ok("http://127.0.0.1:8003/docs"), "API :8003", delai=120)
    attendre(lambda: http_ok("http://127.0.0.1:8503/_stcore/health"), "Streamlit :8503", delai=120)


def etape_airflow(args):
    titre("8. Airflow (DAG horaire v2 et Random Forest 24 h)")
    logs, ssh_dir = OPCA / "airflow/logs", OPCA / "airflow/ssh"
    if logs.exists() and logs.stat().st_uid == int(AIRFLOW_UID):
        info("dossier des journaux Airflow déjà prêt")
    else:
        if agir("dossier des journaux Airflow (propriétaire uid 50000)"):
            logs.mkdir(parents=True, exist_ok=True)
        run(["chown", f"{AIRFLOW_UID}:0", logs], sudo=True)

    # clé SSH du scheduler vers l'hôte : le Random Forest tourne dans un conteneur lancé sur l'hôte
    cle = ssh_dir / "airflow_collector"
    if ok(["test", "-f", cle], sudo=True):
        info("clé SSH airflow_collector déjà présente")
    else:
        if agir("création de la clé SSH airflow_collector (scheduler -> hôte)"):
            ssh_dir.mkdir(parents=True, exist_ok=True)
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "airflow-collector", "-f", cle])
        hotes = run(["ssh-keyscan", "-H", GW], verifier=False).stdout
        if agir("empreinte de l'hôte dans known_hosts et clé publique dans ~/.ssh/authorized_keys"):
            (ssh_dir / "known_hosts").write_text(hotes)
            publique = (ssh_dir / "airflow_collector.pub").read_text().strip()
            auth = HOME / ".ssh/authorized_keys"
            auth.parent.mkdir(mode=0o700, exist_ok=True)
            if publique not in (auth.read_text() if auth.exists() else ""):
                with open(auth, "a") as f:
                    f.write(publique + "\n")
            auth.chmod(0o600)
        run(["chown", "-R", f"{AIRFLOW_UID}:0", ssh_dir], sudo=True)
        run(["chmod", "700", ssh_dir], sudo=True)
        run(["sh", "-c", f"chmod 600 {ssh_dir}/*"], sudo=True)

    compose_up("docker-compose.airflow.yaml", OPCA, [SCHED, "opca_airflow-airflow-webserver-1",
               "opca_airflow-airflow-postgres-1"], projet="opca_airflow")
    attendre(lambda: http_ok("http://127.0.0.1:8081/health"), "interface Airflow :8081", delai=600, pas=10)
    attendre(lambda: ok(["docker", "exec", SCHED, "airflow", "version"]), "scheduler Airflow", delai=300, pas=10)

    # variables lues par le DAG v2 : seules les manquantes sont créées, par l'entrée standard
    deja = {v.get("key") for v in json_airflow(["variables", "list", "-o", "json"])}
    voulues = {"opca_v2_db_host": GW, "opca_v2_db_port": "5433", "opca_v2_db_name": "opca_db",
               "opca_v2_db_user": "opca_app", "opca_v2_db_password": pg_env()["POSTGRES_PASSWORD"],
               "opca_v2_write_predictions": "1"}
    manquantes = {k: v for k, v in voulues.items() if k not in deja}
    if not manquantes:
        info("variables Airflow opca_v2_* déjà présentes")
    else:
        info(f"variables Airflow à créer : {', '.join(manquantes)}")
        run(["docker", "exec", "-i", SCHED, "sh", "-c",
             "umask 077; cat > /tmp/v.json; airflow variables import /tmp/v.json; r=$?; rm -f /tmp/v.json; exit $r"],
            entree=json.dumps(manquantes))

    def etat_dags():
        return {d["dag_id"]: str(d.get("is_paused")).lower() == "true"
                for d in json_airflow(["dags", "list", "-o", "json"]) if "dag_id" in d}
    attendre(lambda: all(d in etat_dags() for d in DAG_ACTIFS + DAG_EN_PAUSE), "lecture des DAG", delai=300, pas=15)
    etat = etat_dags()
    for dag in DAG_EN_PAUSE:
        if not etat.get(dag, False):
            run(["docker", "exec", SCHED, "airflow", "dags", "pause", dag])
    for dag in DAG_ACTIFS:
        if etat.get(dag, True):
            run(["docker", "exec", SCHED, "airflow", "dags", "unpause", dag])
    info(f"DAG actifs : {', '.join(DAG_ACTIFS)} ; en pause : {', '.join(DAG_EN_PAUSE)}")

    if not SIMULATION:
        if ok(["docker", "exec", SCHED, "ssh", "-i", "/home/airflow/.ssh/airflow_collector", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", f"{UTILISATEUR}@{GW}", "true"]):
            info("SSH scheduler -> hôte : OK (Random Forest)")
        else:
            avertir("le scheduler n'arrive pas à se connecter en SSH à l'hôte : le Random Forest échouera")


def etape_supervision(args):
    titre("9. Supervision : Prometheus, node-exporter, cAdvisor, Grafana")
    compose_up("docker-compose.monitoring.yaml", V2 / "monitoring",
               ["opca_prometheus", "opca_node_exporter", "opca_cadvisor"])
    compose_up("docker-compose.grafana.yaml", V2 / "compose", ["opca_grafana_v2"])
    attendre(lambda: http_ok(f"http://{GW}:9090/-/ready"), "Prometheus", delai=120)
    attendre(lambda: http_ok("http://127.0.0.1:3001/api/health"), "Grafana :3001", delai=180)


def etape_cron(args):
    titre("10. Tâches planifiées (cron) : contrôles, sauvegarde, rapports")
    sauvegardes, rapports = PROJET / "backups/opca_v2", PROJET / "rapport_quotidien"
    if not sauvegardes.exists() and agir(f"dossier des sauvegardes {sauvegardes} (droits 700)"):
        sauvegardes.mkdir(parents=True)
        sauvegardes.chmod(0o700)
    script = rapports / "rapport_quotidien.py"
    if script.exists():
        info(f"{script} déjà présent")
    elif agir(f"copie du script de rapport dans {rapports}"):
        rapports.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OPCA / "v2/rapport_quotidien/rapport_quotidien.py", script)
        script.chmod(0o755)
    r = run(["crontab", "-l"], lecture=True, verifier=False)
    actuel = r.stdout if r.returncode == 0 else ""
    manquantes = [l for l in CRON if l not in actuel]
    if not manquantes:
        info("les 4 lignes cron sont déjà présentes")
        return
    if agir(f"ajout de {len(manquantes)} ligne(s) cron (les lignes existantes sont gardées)"):
        nouveau = actuel.rstrip("\n") + ("\n" if actuel.strip() else "") + "\n".join(manquantes) + "\n"
        run(["crontab", "-"], entree=nouveau)


def etape_controle(args):
    titre("11. Contrôle final")
    if SIMULATION:
        info("simulation : contrôle non lancé")
        return
    r = run(["bash", V2 / "checks/check_opca.sh"], verifier=False)
    lignes = r.stdout.splitlines()
    for l in lignes:
        if l.startswith(("[WARN]", "[FAIL]")):
            print("   ", l)
    bilan = [l.strip("= ") for l in lignes if "Résumé" in l]
    info(bilan[-1] if bilan else f"contrôle terminé (code {r.returncode})")
    info("juste après une installation, les contrôles de fraîcheur et de volume des données (bougies, "
         "prévisions, sauvegarde) restent en FAIL tant que les premières collectes horaires n'ont pas tourné")
    ip = (run(["hostname", "-I"], lecture=True, verifier=False).stdout.split() or ["<ip>"])[0]
    print(f"""
  Adresses (ouvrir ces ports dans le pare-feu ou le groupe de sécurité si besoin) :
    API        http://{ip}:8003/docs
    Streamlit  http://{ip}:8503
    Airflow    http://{ip}:8081
    Grafana    http://{ip}:3001
    Adminer    ssh -L 8085:127.0.0.1:8085 {UTILISATEUR}@{ip}  puis  http://localhost:8085
  Comptes et mots de passe : cat {PROJET / 'ACCES_EQUIPE.md'}""")


ETAPES = {"verifier": etape_verifier, "code": etape_code, "secrets": etape_secrets, "images": etape_images,
          "base": etape_base, "adminer": etape_adminer, "api": etape_api, "airflow": etape_airflow,
          "supervision": etape_supervision, "cron": etape_cron, "controle": etape_controle}


def main():
    global SIMULATION
    p = argparse.ArgumentParser(description="Installe la plateforme OPCA sur une VM Ubuntu neuve.")
    p.add_argument("--dump", help="sauvegarde opca_db (.dump de backup_v2.sh) à restaurer dans une base vide")
    p.add_argument("--simulation", action="store_true", help="affiche les actions sans rien modifier")
    p.add_argument("--etapes", help=f"liste séparée par des virgules parmi : {','.join(ETAPES)}")
    p.add_argument("--installer-docker", action="store_true", help="installe Docker s'il est absent")
    p.add_argument("--reconstruire", action="store_true", help="reconstruit les images même si elles existent")
    p.add_argument("--depot", default=DEPOT)
    p.add_argument("--branche", default=BRANCHE)
    args = p.parse_args()
    SIMULATION = args.simulation
    choix = args.etapes.split(",") if args.etapes else list(ETAPES)
    inconnues = [e for e in choix if e not in ETAPES]
    if inconnues:
        p.error(f"étape(s) inconnue(s) : {', '.join(inconnues)}")

    print(f"Installation OPCA{' (SIMULATION : rien ne sera modifié)' if SIMULATION else ''} - étapes : {', '.join(choix)}")
    debut = time.time()
    try:
        for nom in choix:
            ETAPES[nom](args)
    except Erreur as e:
        print(f"\nARRÊT : {e}\nCorriger puis relancer : les étapes déjà faites seront passées.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrompu : relancer le script reprend là où il s'est arrêté.")
        sys.exit(130)
    print(f"\nTerminé en {(time.time() - debut) / 60:.0f} min.")
    if AVERTISSEMENTS:
        print("Points à vérifier :")
        for a in AVERTISSEMENTS:
            print(f"  ! {a}")


if __name__ == "__main__":
    main()
