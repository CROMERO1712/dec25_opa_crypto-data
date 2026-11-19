"""Génère grafana/dashboards/infra.json : tableau « Infrastructure VM » (Prometheus).

Lancer : python generer_tableau_infra.py   (écrit le fichier à côté, dans grafana/dashboards/)
"""
import json
import os

DS = {"type": "prometheus", "uid": "opca-prom"}
VERT, ORANGE, ROUGE = "green", "orange", "red"
panels = []
_id = 0


def pid():
    global _id
    _id += 1
    return _id


def seuils(orange, rouge):
    return {"mode": "absolute", "steps": [{"color": VERT, "value": None},
                                          {"color": ORANGE, "value": orange},
                                          {"color": ROUGE, "value": rouge}]}


def ligne(titre, y):
    panels.append({"type": "row", "title": titre, "id": pid(), "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []})


def stat(titre, expr, x, y, unite="percent", orange=70, rouge=85, w=4, desc="", decimales=0, inverse=False):
    th = seuils(orange, rouge)
    if inverse:   # plus c'est bas, plus c'est grave (ex. mémoire disponible)
        th = {"mode": "absolute", "steps": [{"color": ROUGE, "value": None},
                                            {"color": ORANGE, "value": rouge},
                                            {"color": VERT, "value": orange}]}
    panels.append({
        "type": "stat", "title": titre, "id": pid(), "datasource": DS, "description": desc,
        "gridPos": {"h": 4, "w": w, "x": x, "y": y},
        "targets": [{"refId": "A", "datasource": DS, "expr": expr, "instant": True}],
        "fieldConfig": {"defaults": {"unit": unite, "decimals": decimales, "thresholds": th,
                                     "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "background", "graphMode": "area", "textMode": "value", "justifyMode": "center"},
    })


def courbe(titre, cibles, x, y, unite, w=12, h=8, desc="", max_=None, seuil=None, legende_table=False):
    defaults = {"unit": unite, "custom": {"lineWidth": 2, "fillOpacity": 8, "showPoints": "never",
                                          "spanNulls": True, "gradientMode": "none"},
                "color": {"mode": "palette-classic"}}
    if max_ is not None:
        defaults["max"] = max_
        defaults["min"] = 0
    if seuil is not None:
        defaults["thresholds"] = {"mode": "absolute", "steps": [{"color": "transparent", "value": None},
                                                               {"color": ROUGE, "value": seuil}]}
        defaults["custom"]["thresholdsStyle"] = {"mode": "dashed"}
    panels.append({
        "type": "timeseries", "title": titre, "id": pid(), "datasource": DS, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [{"refId": chr(65 + i), "datasource": DS, "expr": e, "legendFormat": l}
                    for i, (e, l) in enumerate(cibles)],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"tooltip": {"mode": "multi", "sort": "desc"},
                    "legend": {"displayMode": "table" if legende_table else "list", "placement": "right" if legende_table else "bottom",
                               "calcs": ["lastNotNull", "max"] if legende_table else []}},
    })


def tableau_conteneurs(y):
    base = '{name=~".+"}'
    panels.append({
        "type": "table", "title": "Conteneurs : mémoire et CPU (maintenant)", "id": pid(), "datasource": DS,
        "description": "Mémoire utilisée, limite fixée dans docker compose et part de la limite. Au-delà de 90 % de sa limite, un conteneur risque d'être tué par le système (OOM).",
        "gridPos": {"h": 10, "w": 24, "x": 0, "y": y},
        "targets": [
            {"refId": "A", "datasource": DS, "format": "table", "instant": True,
             "expr": f"sum by (name) (container_memory_working_set_bytes{base})"},
            {"refId": "B", "datasource": DS, "format": "table", "instant": True,
             "expr": f"sum by (name) (container_spec_memory_limit_bytes{base}) > 0"},
            {"refId": "C", "datasource": DS, "format": "table", "instant": True,
             "expr": f"100 * sum by (name) (container_memory_working_set_bytes{base}) / (sum by (name) (container_spec_memory_limit_bytes{base}) > 0)"},
            {"refId": "D", "datasource": DS, "format": "table", "instant": True,
             "expr": f"100 * sum by (name) (rate(container_cpu_usage_seconds_total{base}[5m]))"},
        ],
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True},
                "renameByName": {"name": "Conteneur", "Value #A": "Mémoire utilisée", "Value #B": "Limite",
                                 "Value #C": "% de la limite", "Value #D": "CPU (% d'un cœur)"}}},
            {"id": "sortBy", "options": {"sort": [{"field": "% de la limite", "desc": True}]}},
        ],
        "fieldConfig": {"defaults": {"custom": {"align": "auto"}}, "overrides": [
            {"matcher": {"id": "byName", "options": "Mémoire utilisée"}, "properties": [{"id": "unit", "value": "bytes"}]},
            {"matcher": {"id": "byName", "options": "Limite"}, "properties": [{"id": "unit", "value": "bytes"}]},
            {"matcher": {"id": "byName", "options": "CPU (% d'un cœur)"},
             "properties": [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1}]},
            {"matcher": {"id": "byName", "options": "% de la limite"}, "properties": [
                {"id": "unit", "value": "percent"}, {"id": "decimals", "value": 0}, {"id": "max", "value": 100},
                {"id": "thresholds", "value": seuils(75, 90)},
                {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}}]},
        ]},
        "options": {"showHeader": True, "cellHeight": "sm"},
    })


# --- Vue d'ensemble -----------------------------------------------------------------------------
ligne("VM : vue d'ensemble", 0)
CPU = '100 * (1 - sum(rate(node_cpu_seconds_total{mode="idle"}[5m])) / sum(rate(node_cpu_seconds_total[5m])))'
MEM = "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
DISQUE = '100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})'
stat("CPU", CPU, 0, 1, desc="Utilisation moyenne des processeurs sur 5 min.")
stat("Mémoire utilisée", MEM, 4, 1, orange=80, rouge=90, desc="Part de la mémoire non disponible (le cache disque est compté comme disponible).")
stat("Disque /", DISQUE, 8, 1, orange=75, rouge=85, desc="Remplissage du disque principal (base, sauvegardes, images Docker).")
stat("Charge / cœur", 'scalar(node_load5) / scalar(count(node_cpu_seconds_total{mode="idle"}))', 12, 1, unite="none",
     orange=1, rouge=2, decimales=2, desc="Charge moyenne sur 5 min divisée par le nombre de cœurs. Au-dessus de 1, des tâches attendent.")
stat("Conteneurs actifs", 'count(count by (name) (container_last_seen{name=~".+"} > (time() - 120)))', 16, 1,
     unite="none", orange=0, rouge=0, desc="Nombre de conteneurs Docker vus dans les 2 dernières minutes.")
panels[-1]["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}
stat("Allumée depuis", "time() - node_boot_time_seconds", 20, 1, unite="s", orange=1e12, rouge=1e12,
     desc="Temps écoulé depuis le dernier redémarrage de la VM.")
panels[-1]["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}

# --- Historique de la VM ------------------------------------------------------------------------
ligne("VM : historique", 5)
courbe("CPU (%)", [(CPU, "CPU")], 0, 6, "percent", max_=100, seuil=85)
courbe("Mémoire", [("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "utilisée"),
                   ("node_memory_MemAvailable_bytes", "disponible")], 12, 6, "bytes")
courbe("Disque / (%)", [(DISQUE, "/")], 0, 14, "percent", max_=100, seuil=85)
courbe("Réseau des conteneurs", [('sum(rate(container_network_receive_bytes_total{name=~".+"}[5m]))', "reçu"),
                                ('sum(rate(container_network_transmit_bytes_total{name=~".+"}[5m]))', "envoyé")],
       12, 14, "Bps", desc="Trafic réseau de l'ensemble des conteneurs (collecte des prix, API, Grafana...).")

# --- Conteneurs ---------------------------------------------------------------------------------
ligne("Conteneurs", 22)
tableau_conteneurs(23)
courbe("Mémoire par conteneur (8 plus gros)",
       [('topk(8, sum by (name) (container_memory_working_set_bytes{name=~".+"}))', "{{name}}")],
       0, 33, "bytes", legende_table=True)
courbe("CPU par conteneur (% d'un cœur, 8 plus actifs)",
       [('topk(8, 100 * sum by (name) (rate(container_cpu_usage_seconds_total{name=~".+"}[5m])))', "{{name}}")],
       12, 33, "percent", legende_table=True)

tableau = {
    "uid": "opca-infra", "title": "Infrastructure VM OPCA", "tags": ["opca", "infra"],
    "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": True,
    "refresh": "1m", "time": {"from": "now-6h", "to": "now"},
    "description": "Ressources de la VM (CPU, mémoire, disque, réseau) et des conteneurs Docker. Source : Prometheus (node-exporter + cAdvisor).",
    "panels": panels, "templating": {"list": []}, "annotations": {"list": []},
    "links": [{"title": "Monitoring des données", "type": "dashboards", "tags": ["opca"], "asDropdown": False}],
}
sortie = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grafana", "dashboards", "infra.json")
with open(sortie, "w", encoding="utf-8", newline="\n") as f:
    json.dump(tableau, f, ensure_ascii=False, indent=2)
print("écrit", sortie, len(panels), "éléments")
