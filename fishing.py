import requests
import csv
import json
import os
import re
import sys
import time
import smtplib
import socket
import dns.resolver
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote_plus
from bs4 import BeautifulSoup
from ddgs import DDGS
from fishing_config import (
    FRANCE_TRAVAIL_CLIENT_ID,
    FRANCE_TRAVAIL_CLIENT_SECRET,
    HUNTER_API_KEY,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

JOB_SITES = [
    "indeed.fr", "hellowork.com", "welcometothejungle.com", "linkedin.com",
    "apec.fr", "cadremploi.fr", "monster.fr", "meteojob.com", "regionsjob.com",
    "keljob.com", "glassdoor.fr", "lesjeudis.com", "jobteaser.com", "stepstone.fr",
    "talent.com", "jooble.org", "optioncarriere.com", "emploi.lefigaro.fr",
    "letudiant.fr", "studyrama-emploi.com", "l4m.fr", "directemploi.com",
    "staffme.com", "jobijoba.com", "wizbii.com",
]

REGIONS = {
    "ile-de-france": "11", "auvergne-rhone-alpes": "84", "bourgogne-franche-comte": "27",
    "bretagne": "53", "centre-val-de-loire": "24", "corse": "94", "grand-est": "44",
    "hauts-de-france": "32", "normandie": "28", "nouvelle-aquitaine": "75",
    "occitanie": "76", "pays-de-la-loire": "52", "provence-alpes-cote-d-azur": "93",
}

REGIONS_LABEL = {
    "ile-de-france": "Île-de-France", "auvergne-rhone-alpes": "Auvergne-Rhône-Alpes",
    "bourgogne-franche-comte": "Bourgogne-Franche-Comté", "bretagne": "Bretagne",
    "centre-val-de-loire": "Centre-Val de Loire", "corse": "Corse", "grand-est": "Grand Est",
    "hauts-de-france": "Hauts-de-France", "normandie": "Normandie",
    "nouvelle-aquitaine": "Nouvelle-Aquitaine", "occitanie": "Occitanie",
    "pays-de-la-loire": "Pays de la Loire", "provence-alpes-cote-d-azur": "Provence-Alpes-Côte d'Azur",
}

# Départements par région (pour la recherche multi-département)
REGION_DEPARTEMENTS = {
    "ile-de-france": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "auvergne-rhone-alpes": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "bretagne": ["22", "29", "35", "56"],
    "hauts-de-france": ["02", "59", "60", "62", "80"],
    "grand-est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "normandie": ["14", "27", "50", "61", "76"],
    "nouvelle-aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "pays-de-la-loire": ["44", "49", "53", "72", "85"],
    "provence-alpes-cote-d-azur": ["04", "05", "06", "13", "83", "84"],
    "bourgogne-franche-comte": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "centre-val-de-loire": ["18", "28", "36", "37", "41", "45"],
    "corse": ["2A", "2B"],
}

# Codes NAF pour les entreprises informatiques
CODES_NAF_INFO = [
    "62.01Z",  # Programmation informatique
    "62.02A",  # Conseil en systèmes informatiques
    "62.02B",  # Tierce maintenance informatique
    "62.03Z",  # Gestion d'installations informatiques
    "62.09Z",  # Autres activités informatiques
    "63.11Z",  # Traitement de données, hébergement
    "63.12Z",  # Portails internet
    "58.21Z",  # Edition de jeux electroniques
    "58.29A",  # Edition de logiciels système
    "58.29B",  # Edition de logiciels outils
    "58.29C",  # Edition de logiciels applicatifs
]

# Prefixes email à deviner
EMAIL_PREFIXES = ["contact", "rh", "recrutement", "info", "stage", "emploi", "candidature", "careers", "jobs", "hr"]

# Synonymes pour elargir la recherche automatiquement
SYNONYMES = {
    "informatique": ["developpeur", "développeur", "IT", "digital", "numerique", "logiciel", "software", "web"],
    "developpeur": ["developer", "développeur", "programmeur", "dev", "software engineer"],
    "web": ["frontend", "backend", "fullstack", "full-stack", "site internet"],
    "reseau": ["réseau", "network", "systeme", "système", "admin sys", "sysadmin"],
    "data": ["donnees", "données", "big data", "data analyst", "data engineer", "BI"],
    "cybersecurite": ["cybersécurité", "securite informatique", "sécurité", "pentest", "SOC"],
    "devops": ["cloud", "infrastructure", "CI/CD", "docker", "kubernetes"],
    "mobile": ["android", "ios", "flutter", "react native", "application mobile"],
}

# Codes ROME pour informatique (La Bonne Alternance)
ROME_CODES_INFO = [
    "M1805",  # Développement informatique
    "M1802",  # Expertise et support technique
    "M1801",  # Administration systèmes
    "M1803",  # Direction des SI
    "M1806",  # Conseil et maîtrise d'ouvrage en SI
    "M1810",  # Production et exploitation SI
]

# Coordonnées des régions (pour La Bonne Alternance)
REGION_COORDS = {
    "ile-de-france": (48.8566, 2.3522),
    "auvergne-rhone-alpes": (45.7640, 4.8357),
    "bretagne": (48.1173, -1.6778),
    "hauts-de-france": (50.6292, 3.0573),
    "grand-est": (48.5734, 7.7521),
    "normandie": (49.1829, -0.3707),
    "nouvelle-aquitaine": (44.8378, -0.5792),
    "occitanie": (43.6047, 1.4442),
    "pays-de-la-loire": (47.2184, -1.5536),
    "provence-alpes-cote-d-azur": (43.2965, 5.3698),
    "bourgogne-franche-comte": (47.3220, 5.0415),
    "centre-val-de-loire": (47.3941, 0.6848),
    "corse": (42.1500, 9.1039),
}

# Codes INSEE pour La Bonne Alternance
REGION_INSEE = {
    "ile-de-france": "75056",
    "auvergne-rhone-alpes": "69123",
    "bretagne": "35238",
    "hauts-de-france": "59350",
    "grand-est": "67482",
    "normandie": "14118",
    "nouvelle-aquitaine": "33063",
    "occitanie": "31555",
    "pays-de-la-loire": "44109",
    "provence-alpes-cote-d-azur": "13055",
    "bourgogne-franche-comte": "21231",
    "centre-val-de-loire": "37261",
    "corse": "2A004",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_FILE = os.path.join(SCRIPT_DIR, "emails_envoyes.json")
PENDING_FILE = os.path.join(SCRIPT_DIR, "emails_en_attente.json")
RELANCE_JOURS = 7  # Nombre de jours avant relance
MAX_MAILS_PAR_JOUR = 500  # Gmail limite a 500, on garde une marge


# ============================================================
# TRACKING EMAILS ENVOYES (JSON avec dates)
# ============================================================
def charger_emails_envoyes():
    """Charge le dictionnaire {email: {date, entreprise, relance}}"""
    if not os.path.exists(SENT_FILE):
        return {}
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def sauver_emails_envoyes(data):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def sauver_email_envoye(email, entreprise="", est_relance=False):
    data = charger_emails_envoyes()
    email_lower = email.strip().lower()
    if email_lower in data:
        data[email_lower]["relance"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        data[email_lower]["nb_relances"] = data[email_lower].get("nb_relances", 0) + 1
    else:
        data[email_lower] = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "entreprise": entreprise,
            "relance": None,
            "nb_relances": 0,
        }
    sauver_emails_envoyes(data)


def compter_mails_envoyes_aujourdhui():
    """Compte combien de mails ont été envoyés aujourd'hui"""
    data = charger_emails_envoyes()
    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    count = 0
    for info in data.values():
        if info.get("date", "").startswith(aujourdhui):
            count += 1
        if info.get("relance", "") and info["relance"].startswith(aujourdhui):
            count += 1
    return count


# ============================================================
# FILE D'ATTENTE (emails en attente pour le lendemain)
# ============================================================
def sauver_emails_en_attente(emails_list):
    """Sauvegarde les emails non envoyés pour le prochain lancement"""
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(emails_list, f, indent=2, ensure_ascii=False)
    print(f"\n  [+] {len(emails_list)} emails sauvegardes dans emails_en_attente.json")
    print(f"      Relance le script demain pour continuer l'envoi !")


def charger_emails_en_attente():
    """Charge les emails en attente du précédent lancement"""
    if not os.path.exists(PENDING_FILE):
        return []
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def supprimer_emails_en_attente():
    if os.path.exists(PENDING_FILE):
        os.remove(PENDING_FILE)


def get_emails_a_relancer():
    """Trouve les emails envoyés il y a plus de RELANCE_JOURS jours sans relance"""
    data = charger_emails_envoyes()
    a_relancer = []
    now = datetime.now()
    for email, info in data.items():
        if info.get("nb_relances", 0) >= 2:
            continue  # Max 2 relances
        date_envoi = datetime.strptime(info["date"], "%Y-%m-%d %H:%M")
        jours = (now - date_envoi).days
        if jours >= RELANCE_JOURS:
            dernier = info.get("relance")
            if dernier:
                date_relance = datetime.strptime(dernier, "%Y-%m-%d %H:%M")
                jours_relance = (now - date_relance).days
                if jours_relance < RELANCE_JOURS:
                    continue
            a_relancer.append({"email": email, "entreprise": info.get("entreprise", ""), "jours": jours})
    return a_relancer


def migrer_ancien_format():
    """Migre l'ancien emails_envoyes.txt vers le nouveau format JSON"""
    ancien = os.path.join(SCRIPT_DIR, "emails_envoyes.txt")
    if os.path.exists(ancien) and not os.path.exists(SENT_FILE):
        print("  [*] Migration emails_envoyes.txt -> .json...")
        data = {}
        with open(ancien, "r", encoding="utf-8") as f:
            for line in f:
                email = line.strip().lower()
                if email:
                    data[email] = {"date": "2026-03-06 00:00", "entreprise": "", "relance": None, "nb_relances": 0}
        sauver_emails_envoyes(data)
        print(f"    {len(data)} emails migres")


# ============================================================
# VALIDATION EMAIL
# ============================================================
def is_valid_email(email):
    if not email or "@" not in email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email.strip()):
        return False
    bad = ["francetravail.fr", "candidat.", "postuler", "lien", "http", "offres", "example.", "test@", "noreply", "no-reply", "mailer-daemon"]
    for b in bad:
        if b in email.lower():
            return False
    return True


# ============================================================
# EMAIL GUESSING - Deviner les emails à partir du domaine
# ============================================================
def deviner_emails(domaine):
    """Génère des emails probables pour un domaine donné"""
    if not domaine:
        return []
    return [f"{prefix}@{domaine}" for prefix in EMAIL_PREFIXES]


def verifier_email_smtp(email):
    """Vérifie si un email existe via SMTP (rapide, pas toujours fiable)"""
    try:
        domaine = email.split("@")[1]
        # Résoudre le MX
        mx_records = dns.resolver.resolve(domaine, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')

        # Connexion SMTP
        server = smtplib.SMTP(timeout=5)
        server.connect(mx_host, 25)
        server.helo("automail.local")
        server.mail("test@automail.local")
        code, _ = server.rcpt(email)
        server.quit()

        return code == 250
    except Exception:
        return False  # En cas de timeout ou erreur, on considère que ça existe pas


def trouver_email_par_domaine(domaine):
    """Essaie de trouver un email valide pour un domaine"""
    emails_a_tester = deviner_emails(domaine)

    # D'abord essayer les plus courants avec vérification SMTP
    for email in emails_a_tester[:4]:  # contact, rh, recrutement, info
        if verifier_email_smtp(email):
            return email

    # Sinon retourner contact@ par défaut (le plus universel)
    return f"contact@{domaine}"


# ============================================================
# SCRAPING SITE WEB ENTREPRISE (trouver email sur page contact)
# ============================================================
def chercher_site_web_entreprise(nom_entreprise):
    """Cherche le site web d'une entreprise via DuckDuckGo"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"{nom_entreprise} site officiel", region="fr-fr", max_results=5))
        for r in results:
            url = r.get("href", "")
            parsed = urlparse(url)
            domain = (parsed.netloc or "").replace("www.", "").lower()
            # Ignorer les sites d'emploi et les annuaires
            ignore = JOB_SITES + ["societe.com", "pappers.fr", "verif.com", "infogreffe.fr",
                                  "wikipedia.org", "facebook.com", "twitter.com", "youtube.com",
                                  "google.com", "pagesjaunes.fr", "duckduckgo.com", "kompass.com"]
            if domain and not any(ig in domain for ig in ignore) and "." in domain:
                return domain
    except Exception:
        pass
    return ""


def scraper_emails_site_web(domaine):
    """Scrape le site web d'une entreprise pour trouver des emails"""
    emails_trouves = set()
    pages_a_tester = [
        f"https://www.{domaine}",
        f"https://www.{domaine}/contact",
        f"https://www.{domaine}/contact/",
        f"https://www.{domaine}/nous-contacter",
        f"https://www.{domaine}/contactez-nous",
        f"https://www.{domaine}/recrutement",
        f"https://www.{domaine}/carrieres",
        f"https://www.{domaine}/jobs",
        f"https://{domaine}",
        f"https://{domaine}/contact",
    ]

    for url in pages_a_tester:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp.text)
                for email in found:
                    if is_valid_email(email) and domaine.split(".")[0] in email.lower():
                        emails_trouves.add(email.lower())
        except Exception:
            pass

    return list(emails_trouves)


# ============================================================
# UI HELPERS
# ============================================================
def afficher_regions():
    print("\n  Regions disponibles :")
    for i, nom in enumerate(REGIONS.keys(), 1):
        print(f"    {i:2d}. {nom.replace('-', ' ').title()}")
    print()


def choisir_region():
    afficher_regions()
    noms = list(REGIONS.keys())
    while True:
        choix = input("  Numero de la region (ou tapez le nom) : ").strip().lower()
        if choix.isdigit():
            idx = int(choix) - 1
            if 0 <= idx < len(noms):
                cle = noms[idx]
                return cle, REGIONS[cle], noms[idx].replace("-", " ").title()
        for nom, code in REGIONS.items():
            if choix in nom.replace("-", " "):
                return nom, code, nom.replace("-", " ").title()
        print("  [!] Region non reconnue, reessaye.")


# ============================================================
# SOURCE 1 : FRANCE TRAVAIL API
# ============================================================
def get_france_travail_token():
    url = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    data = {
        "grant_type": "client_credentials",
        "client_id": FRANCE_TRAVAIL_CLIENT_ID,
        "client_secret": FRANCE_TRAVAIL_CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    try:
        resp = requests.post(url, params={"realm": "/partenaire"}, data=data,
                             headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"    [!] Auth echouee : {e}")
        return None


def chercher_france_travail(token, mots_cles, region_code):
    if not token:
        return []
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    params = {"motsCles": mots_cles, "region": region_code, "range": "0-149"}
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                            params=params, timeout=10)
        resp.raise_for_status()
        resultats = resp.json().get("resultats", [])
        offres = []
        for r in resultats:
            ent = r.get("entreprise", {})
            contact = r.get("contact", {})
            email = ""
            if contact:
                candidate = contact.get("courriel", "")
                if is_valid_email(candidate):
                    email = candidate
            if not email:
                found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r.get("description", ""))
                for f in found:
                    if is_valid_email(f):
                        email = f
                        break
            offres.append({
                "titre": r.get("intitule", ""),
                "entreprise": ent.get("nom", ""),
                "url_entreprise": ent.get("url", ""),
                "lieu": r.get("lieuTravail", {}).get("libelle", ""),
                "email": email.strip().lower() if email else "",
                "description": r.get("description", ""),
                "source": "France Travail",
            })
        return offres
    except json.JSONDecodeError:
        return []  # Reponse vide = pas de resultats, normal
    except Exception as e:
        print(f"    [!] Erreur : {e}")
        return []


# ============================================================
# SOURCE 2 : DUCKDUCKGO
# ============================================================
def chercher_duckduckgo_jobs(mots_cles, region_label, types):
    offres = []
    entreprises_vues = set()

    for t in types:
        queries = [
            f'{t} {mots_cles} {region_label}',
            f'{t} {mots_cles} {region_label} recrutement',
            f'{t} {mots_cles} {region_label} offre emploi entreprise',
        ]
        for query in queries:
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, region="fr-fr", max_results=20))
                print(f"    [{t}] {len(results)} resultats pour : {query[:55]}...")
                for r in results:
                    url = r.get("href", "")
                    titre = r.get("title", "")
                    snippet = r.get("body", "")
                    entreprise = extraire_entreprise_from_result(titre, url)
                    if entreprise and entreprise.lower() not in entreprises_vues:
                        entreprises_vues.add(entreprise.lower())
                        url_ent = ""
                        parsed = urlparse(url)
                        domain = (parsed.netloc or "").replace("www.", "")
                        if domain and not any(jb in domain for jb in JOB_SITES):
                            url_ent = f"https://{domain}"
                        email = ""
                        found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                        for f in found:
                            if is_valid_email(f):
                                email = f.lower()
                                break
                        offres.append({
                            "titre": titre, "entreprise": entreprise,
                            "url_entreprise": url_ent, "lieu": region_label,
                            "email": email, "description": snippet,
                            "source": f"DuckDuckGo ({domain})" if domain else "DuckDuckGo",
                        })
            except Exception as e:
                print(f"    [!] Erreur DDG : {e}")
            time.sleep(1)
    return offres


def extraire_entreprise_from_result(titre, url):
    if "welcometothejungle.com" in url:
        match = re.search(r'/companies/([^/]+)', url)
        if match:
            return match.group(1).replace("-", " ").title()
    parts = re.split(r'\s*[-|–—]\s*', titre)
    noise = {"indeed", "hellowork", "linkedin", "glassdoor", "apec", "monster",
             "cadremploi", "welcome to the jungle", "meteojob", "talent.com",
             "jooble", "optioncarriere", "keljob", "regionsjob", "jobijoba",
             "stage", "alternance", "emploi", "offre", "offres", "paris",
             "france", "ile de france", "île de france", "h/f", "f/h", "cdi", "cdd",
             "wizbii", "jobteaser", "directemploi", "studyrama", "letudiant",
             "postuler", "candidature", "recherche", "stepstone", "recrutement"}
    for part in reversed(parts):
        clean = part.strip()
        if (clean and 2 < len(clean) < 60
                and clean.lower() not in noise
                and not any(n in clean.lower() for n in ["stage ", "alternance ", "offre ", "emploi "])
                and clean[0].isupper()):
            return clean
    return ""


# ============================================================
# SOURCE 3 : SCRAPING DIRECT (JSON-LD)
# ============================================================
def scraper_site_direct(url, source_name):
    offres = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return offres
        soup = BeautifulSoup(resp.text, "html.parser")
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and "@graph" in item:
                        items.extend(item["@graph"])
                for item in items:
                    if isinstance(item, dict) and item.get("@type") in ["JobPosting", "jobPosting"]:
                        org = item.get("hiringOrganization", {})
                        if isinstance(org, dict) and org.get("name"):
                            offres.append({
                                "titre": item.get("title", ""),
                                "entreprise": org.get("name", ""),
                                "url_entreprise": org.get("sameAs", "") or org.get("url", ""),
                                "lieu": "", "email": "",
                                "description": item.get("description", ""),
                                "source": source_name,
                            })
            except Exception:
                pass
    except Exception:
        pass
    return offres


def scraper_sites_directs(mots_cles, region_label, types):
    offres = []
    region_url = quote_plus(region_label)
    for t in types:
        q = quote_plus(f"{t} {mots_cles}")
        slug = f"{t}-{mots_cles}".replace(" ", "-").lower()
        urls = [
            (f"https://fr.indeed.com/jobs?q={q}&l={region_url}", "Indeed"),
            (f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={q}&l={region_url}", "HelloWork"),
            (f"https://www.welcometothejungle.com/fr/jobs?query={q}", "WTTJ"),
            (f"https://fr.talent.com/jobs?q={q}&l={region_url}", "Talent.com"),
            (f"https://fr.jooble.org/emploi-{slug}", "Jooble"),
            (f"https://www.optioncarriere.com/emploi?s={q}&l={region_url}", "OptionCarriere"),
        ]
        for url, source in urls:
            site_offres = scraper_site_direct(url, source)
            if site_offres:
                print(f"    [+] {source} : {len(site_offres)} offres")
                offres.extend(site_offres)
            time.sleep(1)
    return offres


# ============================================================
# SOURCE 4 : ANNUAIRE ENTREPRISES (API GOUVERNEMENT)
# ============================================================
def chercher_annuaire_entreprises(departements, max_par_dept=200):
    """Cherche des entreprises IT via l'API gouv (gratuit, sans clé)"""
    entreprises = []
    naf_str = ",".join(CODES_NAF_INFO)

    for dept in departements:
        page = 1
        count = 0
        while count < max_par_dept:
            try:
                per_page = min(25, max_par_dept - count)
                url = f"https://recherche-entreprises.api.gouv.fr/search?activite_principale={naf_str}&departement={dept}&page={page}&per_page={per_page}"
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    break

                data = resp.json()
                results = data.get("results", [])
                if not results:
                    break

                for r in results:
                    nom = r.get("nom_complet", "") or r.get("nom_raison_sociale", "")
                    if not nom or len(nom) <= 2:
                        continue

                    # Chercher le siège
                    siege = r.get("siege", {})
                    # Extraire le domaine du site web si disponible
                    domaine = ""
                    # L'API ne donne pas toujours le site web, on récupère ce qu'on peut
                    matching = r.get("matching_etablissements", [])
                    adresse = siege.get("adresse", "") or siege.get("geo_adresse", "")
                    commune = siege.get("libelle_commune", "")

                    entreprises.append({
                        "titre": "Candidature spontanée - Stage informatique",
                        "entreprise": nom.strip(),
                        "url_entreprise": "",
                        "lieu": f"{dept} - {commune}" if commune else f"Dept {dept}",
                        "email": "",
                        "description": "",
                        "source": "Annuaire Entreprises (gouv.fr)",
                        "siren": r.get("siren", ""),
                    })

                count += len(results)
                page += 1

                if count >= data.get("total_results", 0):
                    break

                time.sleep(0.3)

            except Exception as e:
                print(f"    [!] Erreur annuaire dept {dept} : {e}")
                break

        print(f"    [{dept}] {count} entreprises IT trouvees")

    return entreprises


# ============================================================
# HUNTER.IO
# ============================================================
def chercher_email_hunter(domaine=None, company=None):
    if not HUNTER_API_KEY or HUNTER_API_KEY == "TA_CLE_HUNTER":
        return []
    params = {"api_key": HUNTER_API_KEY, "limit": 5}
    if domaine:
        params["domain"] = domaine
    elif company:
        params["company"] = company
    else:
        return []
    try:
        resp = requests.get("https://api.hunter.io/v2/domain-search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = [e["value"] for e in data.get("emails", [])
                  if e.get("confidence", 0) >= 20 and is_valid_email(e.get("value", ""))]
        # Aussi récupérer le domaine si trouvé
        return emails
    except Exception:
        return []


def chercher_domaine_hunter(company):
    """Cherche le domaine d'une entreprise via Hunter.io"""
    if not HUNTER_API_KEY or HUNTER_API_KEY == "TA_CLE_HUNTER":
        return ""
    try:
        resp = requests.get("https://api.hunter.io/v2/domain-search",
                            params={"api_key": HUNTER_API_KEY, "company": company, "limit": 1}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("domain", "")
    except Exception:
        return ""


def extraire_domaine(url):
    if not url:
        return ""
    try:
        parsed = urlparse(url if url.startswith("http") else f"http://{url}")
        domaine = parsed.netloc or parsed.path
        domaine = re.sub(r"^www\.", "", domaine)
        ignore = JOB_SITES + ["francetravail.fr", "pole-emploi.fr", "google.com", "duckduckgo.com"]
        for ig in ignore:
            if ig in domaine:
                return ""
        return domaine
    except Exception:
        return ""


def generer_synonymes(mots_cles):
    """Génère des variations de recherche à partir des synonymes"""
    variations = set()
    mots = mots_cles.lower().split()
    for mot in mots:
        if mot in SYNONYMES:
            for syn in SYNONYMES[mot]:
                variations.add(syn)
    return list(variations)


def verifier_emails_valides(resultats):
    """Vérifie que les emails sont valides via MX lookup avant envoi"""
    valides = []
    invalides = 0
    domaines_verifies = {}  # Cache

    for r in resultats:
        email = r["email"]
        domaine = email.split("@")[1] if "@" in email else ""

        if domaine in domaines_verifies:
            if domaines_verifies[domaine]:
                valides.append(r)
            else:
                invalides += 1
            continue

        try:
            dns.resolver.resolve(domaine, 'MX')
            domaines_verifies[domaine] = True
            valides.append(r)
        except Exception:
            domaines_verifies[domaine] = False
            invalides += 1

    return valides, invalides


# ============================================================
# SOURCE 5 : LA BONNE ALTERNANCE (API gouv spéciale stages)
# ============================================================
def chercher_la_bonne_alternance(region_cle, types):
    """Cherche des entreprises via La Bonne Alternance API"""
    coords = REGION_COORDS.get(region_cle, (48.8566, 2.3522))
    insee = REGION_INSEE.get(region_cle, "75056")
    romes = ",".join(ROME_CODES_INFO)

    offres = []
    entreprises_vues = set()

    try:
        url = f"https://labonnealternance.apprentissage.beta.gouv.fr/api/v1/jobsEtFormations"
        params = {
            "romes": romes,
            "latitude": coords[0],
            "longitude": coords[1],
            "radius": 50,
            "caller": "automail",
            "insee": insee,
            "sources": "lba,offres",
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"    [!] API LBA : HTTP {resp.status_code}")
            return offres

        data = resp.json()

        # Traiter les jobs (offres et entreprises à potentiel)
        jobs = data.get("jobs") or {}
        if isinstance(jobs, dict):
            for source_key in ["lpiAffichables", "peJobs", "matchas"]:
                items = jobs.get(source_key, []) or []
                for item in items:
                    company = item.get("company", {}) or {}
                    nom = company.get("name", "")
                    if nom and nom.lower() not in entreprises_vues:
                        entreprises_vues.add(nom.lower())
                        offres.append({
                            "titre": item.get("title", "") or "Candidature spontanée - Stage IT",
                            "entreprise": nom,
                            "url_entreprise": company.get("url", "") or "",
                            "lieu": item.get("place", {}).get("city", "") or "",
                            "email": "",
                            "description": "",
                            "source": "La Bonne Alternance",
                        })
        elif isinstance(jobs, list):
            for item in jobs:
                company = item.get("company", {}) or {}
                nom = company.get("name", "")
                if nom and nom.lower() not in entreprises_vues:
                    entreprises_vues.add(nom.lower())
                    offres.append({
                        "titre": item.get("title", "") or "Candidature spontanée - Stage IT",
                        "entreprise": nom,
                        "url_entreprise": company.get("url", "") or "",
                        "lieu": item.get("place", {}).get("city", "") or "",
                        "email": "",
                        "description": "",
                        "source": "La Bonne Alternance",
                    })

    except Exception as e:
        print(f"    [!] Erreur LBA : {e}")

    return offres


# ============================================================
# ENVOI AVEC LIMITE GMAIL + MULTI-COMPTE
# ============================================================
def envoyer_liste(contacts, restant_aujourdhui):
    """Envoie les mails avec rotation de comptes Gmail et auto-stop"""
    from envoyer import envoyer_mail
    try:
        from config import COMPTES_GMAIL
    except ImportError:
        COMPTES_GMAIL = []

    total = len(contacts)
    if total == 0:
        return

    # Construire la liste des comptes disponibles
    comptes = list(COMPTES_GMAIL) if COMPTES_GMAIL else []
    if not comptes:
        from config import MON_EMAIL, MON_MOT_DE_PASSE
        comptes = [{"email": MON_EMAIL, "password": MON_MOT_DE_PASSE}]

    compte_idx = 0
    compte_actuel = comptes[compte_idx]
    limite_par_compte = MAX_MAILS_PAR_JOUR

    print(f"\n  [*] Envoi de {total} mails ({len(comptes)} compte(s) Gmail disponible(s))")
    print(f"      Compte actuel : {compte_actuel['email']}")

    ok = 0
    ok_total = 0

    for i, r in enumerate(contacts):
        email = r["email"]
        entreprise = r["entreprise"]
        poste = r["titre"]
        print(f"  [{i+1}/{total}] -> {email} ({entreprise})")
        try:
            envoyer_mail(email, entreprise=entreprise, poste=poste,
                        sender_email=compte_actuel["email"],
                        sender_password=compte_actuel["password"])
            sauver_email_envoye(email, entreprise=entreprise)
            ok += 1
            ok_total += 1
            time.sleep(2)
        except Exception as e:
            err_str = str(e)
            if "5.4.5" in err_str or "Daily user sending limit" in err_str:
                print(f"\n  [!] LIMITE GMAIL pour {compte_actuel['email']} ({ok} mails)")
                
                # Essayer le compte suivant
                compte_idx += 1
                if compte_idx < len(comptes):
                    compte_actuel = comptes[compte_idx]
                    ok = 0
                    print(f"  [*] Bascule vers : {compte_actuel['email']}")
                    # Reessayer ce mail avec le nouveau compte
                    try:
                        envoyer_mail(email, entreprise=entreprise, poste=poste,
                                    sender_email=compte_actuel["email"],
                                    sender_password=compte_actuel["password"])
                        sauver_email_envoye(email, entreprise=entreprise)
                        ok += 1
                        ok_total += 1
                        time.sleep(2)
                    except Exception:
                        print(f"    [!] Echec aussi sur le nouveau compte")
                else:
                    # Plus de comptes disponibles
                    print(f"  [!] Plus aucun compte disponible !")
                    non_envoyes = contacts[i:]
                    if non_envoyes:
                        sauver_emails_en_attente(non_envoyes)
                    break
            else:
                print(f"    [!] Echec : {e}")

    print(f"\n  [+] {ok_total}/{total} mails envoyes !")
    print(f"  [+] Historique mis a jour dans emails_envoyes.json")


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  AUTOMAIL - Fishing & Candidatures automatiques")
    print("=" * 60)
    print(f"  {len(JOB_SITES)} sites d'emploi + Annuaire Entreprises gouv.fr")
    print("  Sources : France Travail + DuckDuckGo + Scraping + Sites web + Annuaire + Hunter.io")

    # Migrer ancien format si besoin
    migrer_ancien_format()

    # Charger historique envois
    emails_deja_envoyes = charger_emails_envoyes()
    if emails_deja_envoyes:
        print(f"  {len(emails_deja_envoyes)} emails deja contactes (seront exclus)")

    # Compteur journalier
    envoyes_aujourdhui = compter_mails_envoyes_aujourdhui()
    restant_aujourdhui = max(0, MAX_MAILS_PAR_JOUR - envoyes_aujourdhui)
    print(f"  Mails envoyes aujourd'hui : {envoyes_aujourdhui}/{MAX_MAILS_PAR_JOUR}")
    if restant_aujourdhui == 0:
        print("  [!] Limite Gmail atteinte pour aujourd'hui !")

    # Relances a faire ?
    a_relancer = get_emails_a_relancer()
    if a_relancer:
        print(f"  {len(a_relancer)} relances a faire (> {RELANCE_JOURS} jours sans reponse)")

    # ======= EMAILS EN ATTENTE ======= 
    en_attente = charger_emails_en_attente()
    if en_attente:
        # Filtrer ceux deja envoyes entre temps
        en_attente = [e for e in en_attente if e["email"].lower() not in emails_deja_envoyes]
        if en_attente:
            print(f"\n  >>> {len(en_attente)} emails en attente du dernier lancement !")
            choix_resume = input("  Continuer l'envoi ? (o/N) : ").strip().lower()
            if choix_resume == "o":
                envoyer_liste(en_attente, restant_aujourdhui)
                supprimer_emails_en_attente()
                # Recalculer
                envoyes_aujourdhui = compter_mails_envoyes_aujourdhui()
                restant_aujourdhui = max(0, MAX_MAILS_PAR_JOUR - envoyes_aujourdhui)
                if restant_aujourdhui == 0:
                    print("\n  [!] Limite Gmail atteinte. Relance demain pour le reste.")
            else:
                supprimer_emails_en_attente()
                print("  File d'attente effacee.")

    # ======= MODE =======
    print()
    print("  MODE :")
    print("    1. Offres d'emploi (France Travail + sites d'emploi)")
    print("    2. Candidatures spontanees (TOUTES les boites IT de la region)")
    print("    3. Les deux (maximum de resultats)")
    mode = input("  Choix (1/2/3) [3] : ").strip() or "3"

    # Domaine
    print()
    mots_cles = input("  Domaine (ex: developpeur informatique) : ").strip()
    if not mots_cles:
        mots_cles = "informatique"
        print(f"  -> Par defaut : {mots_cles}")

    # Region
    region_cle, region_code, region_nom = choisir_region()
    region_label = REGIONS_LABEL.get(region_cle, region_nom)
    print(f"  -> Region : {region_label}")

    # Type
    print()
    print("  Type :")
    print("    1. Stage uniquement")
    print("    2. Alternance uniquement")
    print("    3. Les deux")
    choix = input("  Choix (1/2/3) [3] : ").strip() or "3"
    types = {"1": ["stage"], "2": ["alternance"], "3": ["stage", "alternance"]}.get(choix, ["stage", "alternance"])

    # Mots-cles techniques
    print()
    print("  Mots-cles techniques (optionnel, pour elargir)")
    print("  Ex: angular, react, python, java, devops")
    kw_input = input("  Mots-cles (vide = recherche simple) : ").strip()
    keywords = [k.strip() for k in kw_input.split(",") if k.strip()] if kw_input else []


    # ======= COLLECTE =======
    print()
    print("  " + "=" * 50)
    print("  COLLECTE (ca peut prendre quelques minutes)")
    print("  " + "=" * 50)

    toutes_offres = []
    recherches = [mots_cles]
    for kw in keywords:
        recherches.append(f"{mots_cles} {kw}")
        recherches.append(kw)

    # Ajouter les synonymes automatiquement
    synonymes = generer_synonymes(mots_cles)
    if synonymes:
        print(f"\n  [+] Synonymes ajoutes : {', '.join(synonymes[:8])}")
        for syn in synonymes[:5]:  # Top 5 synonymes
            recherches.append(f"{syn}")

    # ---- Mode 1 & 3: Offres d'emploi classiques ----
    if mode in ["1", "3"]:
        # 1. France Travail
        print("\n  [OFFRES] France Travail API...")
        token = get_france_travail_token()
        if token:
            for t in types:
                for rech in recherches:
                    offres = chercher_france_travail(token, f"{t} {rech}", region_code)
                    if offres:
                        print(f"    -> {len(offres)} offres ({t} + '{rech}')")
                        toutes_offres.extend(offres)

        # 2. DuckDuckGo
        print(f"\n  [OFFRES] DuckDuckGo Search...")
        for rech in recherches:
            offres_ddg = chercher_duckduckgo_jobs(rech, region_label, types)
            if offres_ddg:
                print(f"    => {len(offres_ddg)} entreprises ('{rech}')")
                toutes_offres.extend(offres_ddg)

        # 3. Scraping direct
        print(f"\n  [OFFRES] Scraping direct (6 sites)...")
        offres_scraping = scraper_sites_directs(mots_cles, region_label, types)
        print(f"    => {len(offres_scraping)} offres via scraping")
        toutes_offres.extend(offres_scraping)

    # ---- Mode 2 & 3: Candidatures spontanées ----
    if mode in ["2", "3"]:
        departements = REGION_DEPARTEMENTS.get(region_cle, [])
        if not departements:
            departements = ["75"]  # Par defaut Paris

        print(f"\n  [SPONTANE] Annuaire Entreprises ({len(departements)} departements, TOUTES les boites IT)...")
        offres_annuaire = chercher_annuaire_entreprises(departements, max_par_dept=10000)
        print(f"    => {len(offres_annuaire)} entreprises IT trouvees")
        toutes_offres.extend(offres_annuaire)

    # ---- La Bonne Alternance (toujours) ----
    print(f"\n  [LBA] La Bonne Alternance API...")
    offres_lba = chercher_la_bonne_alternance(region_cle, types)
    print(f"    => {len(offres_lba)} entreprises via La Bonne Alternance")
    toutes_offres.extend(offres_lba)

    # Dedup par nom d'entreprise
    vus = set()
    offres_uniques = []
    for o in toutes_offres:
        nom = o["entreprise"].strip().lower()
        if nom and nom != "inconnue" and len(nom) > 1 and nom not in vus:
            vus.add(nom)
            offres_uniques.append(o)

    print(f"\n  => TOTAL : {len(offres_uniques)} entreprises uniques")

    if not offres_uniques:
        print("  [!] Aucune entreprise trouvee.")
        return

    # ======= EMAILS =======
    print()
    print("  " + "=" * 50)
    print("  RECHERCHE DES EMAILS")
    print("  " + "=" * 50)

    resultats = []
    emails_vus = set()
    hunter_calls = 0
    MAX_HUNTER = 45

    # Phase 1 : Emails déjà dans les offres
    offres_sans = []
    for o in offres_uniques:
        if o["email"] and is_valid_email(o["email"]) and o["email"] not in emails_vus:
            emails_vus.add(o["email"])
            resultats.append(o)
        else:
            offres_sans.append(o)

    print(f"\n  Phase 1 - Emails dans les offres : {len(resultats)}")

    # Phase 2 : Hunter.io (pour les entreprises importantes)
    if HUNTER_API_KEY and HUNTER_API_KEY != "TA_CLE_HUNTER":
        # Prioriser les offres des job boards (plus pertinentes)
        offres_prioritaires = [o for o in offres_sans if o["source"] != "Annuaire Entreprises (gouv.fr)"]
        offres_annuaire_sans = [o for o in offres_sans if o["source"] == "Annuaire Entreprises (gouv.fr)"]

        nb = min(len(offres_prioritaires), MAX_HUNTER)
        if nb > 0:
            print(f"  Phase 2 - Hunter.io ({nb} entreprises prioritaires)...")

            for o in offres_prioritaires:
                if hunter_calls >= MAX_HUNTER:
                    break

                nom = o["entreprise"]
                if not nom or len(nom) <= 1:
                    continue

                emails = []
                dom = extraire_domaine(o["url_entreprise"])
                if dom:
                    emails = chercher_email_hunter(domaine=dom)
                    hunter_calls += 1
                if not emails:
                    emails = chercher_email_hunter(company=nom)
                    hunter_calls += 1

                if emails:
                    best = emails[0]
                    if best not in emails_vus:
                        emails_vus.add(best)
                        o["email"] = best
                        o["source"] += " + Hunter.io"
                        resultats.append(o)
                        print(f"    [+] {nom} -> {best}")

                time.sleep(0.4)

            print(f"    {hunter_calls} appels effectues")

        # Phase 2b : Hunter.io pour annuaire (trouver domaine + email)
        remaining_hunter = MAX_HUNTER - hunter_calls
        if remaining_hunter > 0 and offres_annuaire_sans:
            nb2 = min(len(offres_annuaire_sans), remaining_hunter // 2)
            if nb2 > 0:
                print(f"  Phase 2b - Hunter.io pour annuaire ({nb2} entreprises)...")
                for o in offres_annuaire_sans[:nb2]:
                    nom = o["entreprise"]
                    emails = chercher_email_hunter(company=nom)
                    hunter_calls += 1

                    if emails:
                        best = emails[0]
                        if best not in emails_vus:
                            emails_vus.add(best)
                            o["email"] = best
                            o["source"] += " + Hunter.io"
                            resultats.append(o)
                            print(f"    [+] {nom} -> {best}")
                    time.sleep(0.4)

    # Phase 3 : Chercher domaine + scraper site web
    offres_encore_sans = [o for o in offres_sans if o["email"] == "" and o not in resultats]

    if offres_encore_sans:
        print(f"  Phase 3 - Scraping sites web ({min(len(offres_encore_sans), 50)} entreprises)...")
        scraped = 0
        for o in offres_encore_sans[:50]:  # Limiter pour pas que ca prenne 3h
            nom = o["entreprise"]
            dom = extraire_domaine(o.get("url_entreprise", ""))

            # Si pas de domaine, chercher via DuckDuckGo
            if not dom:
                dom = chercher_site_web_entreprise(nom)
                time.sleep(0.5)

            if dom:
                # Scraper le site web pour emails
                emails_site = scraper_emails_site_web(dom)
                if emails_site:
                    best = emails_site[0]
                    if best not in emails_vus:
                        emails_vus.add(best)
                        o["email"] = best
                        o["source"] += " + Site web"
                        resultats.append(o)
                        scraped += 1
                        print(f"    [+] {nom} -> {best} (site web)")

        print(f"    {scraped} emails trouves via scraping de sites web")

    # Phase 4 : Email guessing MX pour les restants
    offres_encore_sans2 = [o for o in offres_sans if o["email"] == "" and o not in resultats]
    annuaire_sans = [o for o in offres_encore_sans2 if o["source"] == "Annuaire Entreprises (gouv.fr)"]

    if annuaire_sans:
        print(f"  Phase 4 - Email guessing MX ({len(annuaire_sans)} entreprises)...")
        guessed = 0
        for o in annuaire_sans:
            nom = o["entreprise"]
            # Construire un domaine probable
            domaine_guess = nom.lower().replace(" ", "").replace("'", "").replace("-", "")
            domaine_guess = re.sub(r'[^a-z0-9]', '', domaine_guess)
            if len(domaine_guess) < 3:
                continue

            # Essayer domaine.fr et domaine.com
            for ext in [".fr", ".com"]:
                test_domain = domaine_guess + ext
                email_guess = f"contact@{test_domain}"

                try:
                    dns.resolver.resolve(test_domain, 'MX')
                    if email_guess not in emails_vus:
                        emails_vus.add(email_guess)
                        o["email"] = email_guess
                        o["source"] += " + Guess"
                        resultats.append(o)
                        guessed += 1
                        if guessed % 20 == 0:
                            print(f"    ... {guessed} emails devines")
                    break
                except Exception:
                    continue

        print(f"    {guessed} emails devines via MX lookup")

    # Filtrer les emails déjà envoyés
    nouveaux = [r for r in resultats if r["email"].lower() not in emails_deja_envoyes]
    deja = len(resultats) - len(nouveaux)

    # Phase 5 : Vérification des emails
    if nouveaux:
        print(f"\n  Phase 5 - Verification des emails ({len(nouveaux)} emails)...")
        nouveaux, invalides = verifier_emails_valides(nouveaux)
        if invalides > 0:
            print(f"    {invalides} emails invalides retires (domaine inexistant)")
        print(f"    {len(nouveaux)} emails verifies OK")

    # ======= RESULTATS =======
    print()
    print("=" * 60)
    print(f"  RESULTATS : {len(nouveaux)} nouveaux contacts verifies !")
    if deja > 0:
        print(f"  ({deja} deja contactes, exclus)")
    print("=" * 60)

    if not nouveaux:
        print("  [!] Aucun nouvel email.")
    else:
        for i, r in enumerate(nouveaux, 1):
            print(f"\n  {i:3d}. {r['entreprise']}")
            print(f"       Email  : {r['email']}")
            print(f"       Poste  : {r['titre']}")
            if r["lieu"]:
                print(f"       Lieu   : {r['lieu']}")
            print(f"       Source : {r['source']}")

        # CSV
        fichier = os.path.join(SCRIPT_DIR, "emails_trouves.csv")
        with open(fichier, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Email", "Entreprise", "Poste", "Lieu", "Source"])
            for r in nouveaux:
                w.writerow([r["email"], r["entreprise"], r["titre"], r["lieu"], r["source"]])

        print(f"\n  [+] Sauvegarde dans emails_trouves.csv")

        # ======= ENVOYER =======
        print()
        choix_envoi = input("  Envoyer ton mail a tous ces contacts ? (o/N/d=differe 8h) : ").strip().lower()

        if choix_envoi == "d":
            # Envoi différé à 8h du matin
            now = datetime.now()
            if now.hour >= 8 and now.hour < 18:
                print("  [*] Il est deja l'heure de bureau, envoi maintenant...")
                choix_envoi = "o"
            else:
                if now.hour >= 18:
                    demain_8h = now.replace(hour=8, minute=0, second=0) + timedelta(days=1)
                else:
                    demain_8h = now.replace(hour=8, minute=0, second=0)
                attente = (demain_8h - now).total_seconds()
                print(f"  [*] Envoi programme a 8h00 ({demain_8h.strftime('%d/%m/%Y %H:%M')})")
                print(f"      Attente : {int(attente // 3600)}h{int((attente % 3600) // 60):02d}min")
                print(f"      (Laisse le terminal ouvert, ou Ctrl+C pour annuler)")
                try:
                    time.sleep(attente)
                    choix_envoi = "o"
                    print("\n  [*] 8h00 ! Lancement de l'envoi...")
                except KeyboardInterrupt:
                    print("\n  [!] Envoi annule.")
                    choix_envoi = ""

        if choix_envoi == "o":
            envoyer_liste(nouveaux, restant_aujourdhui)

    # ======= RELANCES =======
    if a_relancer:
        print()
        print("=" * 60)
        print(f"  RELANCES : {len(a_relancer)} emails sans reponse depuis {RELANCE_JOURS}+ jours")
        print("=" * 60)

        for r in a_relancer[:10]:
            print(f"    {r['entreprise'] or r['email']} ({r['jours']} jours)")
        if len(a_relancer) > 10:
            print(f"    ... et {len(a_relancer) - 10} autres")

        choix_relance = input("\n  Envoyer les relances ? (o/N) : ").strip().lower()
        if choix_relance == "o":
            from envoyer import envoyer_mail
            from config import CONTENU

            relance_contenu = """Madame, Monsieur,

Je me permets de revenir vers vous suite a mon precedent mail concernant ma recherche de stage en informatique.

N'ayant pas eu de retour de votre part, je souhaitais renouveler mon interet pour un eventuel stage au sein de {entreprise}.

Vous trouverez toujours en piece jointe mon CV et ma lettre de motivation.

Je reste a votre entiere disposition pour tout renseignement complementaire.

Cordialement"""

            print(f"\n  [*] Envoi de {len(a_relancer)} relances...")
            ok_rel = 0
            for i, r in enumerate(a_relancer, 1):
                email = r["email"]
                entreprise = r.get("entreprise", "")
                print(f"  [{i}/{len(a_relancer)}] Relance -> {email}")
                try:
                    # Temporairement overrider le contenu pour la relance
                    import config
                    old_contenu = config.CONTENU
                    old_objet = config.OBJET
                    config.CONTENU = relance_contenu.replace("{entreprise}", entreprise) if entreprise else relance_contenu.replace("{entreprise}", "votre entreprise")
                    config.OBJET = f"Relance - {old_objet}"
                    envoyer_mail(email, entreprise=entreprise)
                    config.CONTENU = old_contenu
                    config.OBJET = old_objet
                    sauver_email_envoye(email, entreprise=entreprise, est_relance=True)
                    ok_rel += 1
                    time.sleep(2)
                except Exception as e:
                    print(f"    [!] Echec : {e}")
            print(f"\n  [+] {ok_rel}/{len(a_relancer)} relances envoyees !")

    # Stats finales
    print()
    print("  " + "-" * 40)
    all_data = charger_emails_envoyes()
    print(f"  STATS")
    print(f"    Nouveaux contacts trouves : {len(nouveaux)}")
    print(f"    Total emails envoyes      : {len(all_data)}")
    if nouveaux:
        sources = {}
        for r in nouveaux:
            src = r["source"].split(" + ")[0]
            sources[src] = sources.get(src, 0) + 1
        for src, nb in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            print(f"    {src:30s} : {nb}")


if __name__ == "__main__":
    main()
