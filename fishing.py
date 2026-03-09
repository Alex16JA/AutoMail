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
from datetime import datetime
from urllib.parse import urlparse, quote_plus
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_FILE = os.path.join(SCRIPT_DIR, "emails_envoyes.txt")


# ============================================================
# TRACKING EMAILS ENVOYES
# ============================================================
def charger_emails_envoyes():
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())


def sauver_email_envoye(email):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(email.strip().lower() + "\n")


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


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  AUTOMAIL - Fishing & Candidatures automatiques")
    print("=" * 60)
    print(f"  {len(JOB_SITES)} sites d'emploi + Annuaire Entreprises gouv.fr")
    print("  Sources : France Travail + DuckDuckGo + Scraping + Annuaire + Hunter.io")

    # Charger historique envois
    emails_deja_envoyes = charger_emails_envoyes()
    if emails_deja_envoyes:
        print(f"  {len(emails_deja_envoyes)} emails deja contactes (seront exclus)")

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

    # Phase 3 : Email guessing pour les entreprises de l'annuaire
    offres_encore_sans = [o for o in offres_sans if o["email"] == "" and o not in resultats]
    annuaire_sans = [o for o in offres_encore_sans if o["source"] == "Annuaire Entreprises (gouv.fr)"]

    if annuaire_sans:
        print(f"  Phase 3 - Email guessing ({len(annuaire_sans)} entreprises)...")
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

                # Vérifier si le domaine a des enregistrements MX
                try:
                    dns.resolver.resolve(test_domain, 'MX')
                    # Le domaine existe ! Utiliser contact@
                    if email_guess not in emails_vus:
                        emails_vus.add(email_guess)
                        o["email"] = email_guess
                        o["source"] += " + Guess"
                        resultats.append(o)
                        guessed += 1
                        if guessed % 10 == 0:
                            print(f"    ... {guessed} emails devinés")
                    break
                except Exception:
                    continue

        print(f"    {guessed} emails devines via MX lookup")

    # Filtrer les emails déjà envoyés
    nouveaux = [r for r in resultats if r["email"].lower() not in emails_deja_envoyes]
    deja = len(resultats) - len(nouveaux)

    # ======= RESULTATS =======
    print()
    print("=" * 60)
    print(f"  RESULTATS : {len(nouveaux)} nouveaux contacts !")
    if deja > 0:
        print(f"  ({deja} deja contactes, exclus)")
    print("=" * 60)

    if not nouveaux:
        print("  [!] Aucun nouvel email.")
        return

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
    choix = input("  Envoyer ton mail a tous ces contacts ? (o/N) : ").strip().lower()
    if choix == "o":
        from envoyer import envoyer_mail
        print(f"\n  [*] Envoi de {len(nouveaux)} mails personnalises...")
        ok = 0
        for i, r in enumerate(nouveaux, 1):
            email = r["email"]
            entreprise = r["entreprise"]
            poste = r["titre"]
            print(f"  [{i}/{len(nouveaux)}] -> {email} ({entreprise})")
            try:
                envoyer_mail(email, entreprise=entreprise, poste=poste)
                sauver_email_envoye(email)
                ok += 1
                time.sleep(2)
            except Exception as e:
                print(f"    [!] Echec : {e}")
        print(f"\n  [+] {ok}/{len(nouveaux)} mails envoyes !")
        print(f"  [+] Historique mis a jour dans emails_envoyes.txt")

    # Stats finales
    print()
    print("  " + "-" * 40)
    print(f"  STATS : {len(nouveaux)} contacts trouves")
    sources = {}
    for r in nouveaux:
        src = r["source"].split(" + ")[0]
        sources[src] = sources.get(src, 0) + 1
    for src, nb in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        print(f"    {src:30s} : {nb}")
    print(f"  Total emails deja envoyes : {len(emails_deja_envoyes) + (ok if choix == 'o' else 0)}")


if __name__ == "__main__":
    main()
