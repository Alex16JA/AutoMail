import requests
import csv
import json
import os
import re
import sys
import time
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_FILE = os.path.join(SCRIPT_DIR, "emails_envoyes.txt")


# ============================================================
# TRACKING EMAILS ENVOYES
# ============================================================
def charger_emails_envoyes():
    """Charge la liste des emails deja envoyes"""
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())


def sauver_email_envoye(email):
    """Ajoute un email a la liste des envoyes"""
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
    bad = ["francetravail.fr", "candidat.", "postuler", "lien", "http", "offres", "example."]
    for b in bad:
        if b in email.lower():
            return False
    return True


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
# SOURCE 2 : DUCKDUCKGO (via lib python - bypass CAPTCHA)
# ============================================================
def chercher_duckduckgo_jobs(mots_cles, region_label, types):
    """Cherche sur DuckDuckGo via la lib python (contourne les CAPTCHA)"""
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
                            "titre": titre,
                            "entreprise": entreprise,
                            "url_entreprise": url_ent,
                            "lieu": region_label,
                            "email": email,
                            "description": snippet,
                            "source": f"DuckDuckGo ({domain})" if domain else "DuckDuckGo",
                        })

            except Exception as e:
                print(f"    [!] Erreur DDG : {e}")

            time.sleep(1)

    return offres


def extraire_entreprise_from_result(titre, url):
    """Extrait le nom d'entreprise depuis un résultat de recherche"""
    # WTTJ
    if "welcometothejungle.com" in url:
        match = re.search(r'/companies/([^/]+)', url)
        if match:
            return match.group(1).replace("-", " ").title()

    # Patterns dans les titres : "Poste - Entreprise - Lieu"
    parts = re.split(r'\s*[-|–—]\s*', titre)

    noise = {"indeed", "hellowork", "linkedin", "glassdoor", "apec", "monster",
             "cadremploi", "welcome to the jungle", "meteojob", "talent.com",
             "jooble", "optioncarriere", "keljob", "regionsjob", "jobijoba",
             "stage", "alternance", "emploi", "offre", "offres", "paris",
             "france", "ile de france", "île de france", "h/f", "f/h", "cdi", "cdd",
             "wizbii", "jobteaser", "directemploi", "studyrama", "letudiant",
             "postuler", "candidature", "recherche", "stepstone", "recrutement"}

    for part in reversed(parts):  # Entreprise souvent en 2e ou 3e position
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
        return [e["value"] for e in resp.json().get("data", {}).get("emails", [])
                if e.get("confidence", 0) >= 20 and is_valid_email(e.get("value", ""))]
    except Exception:
        return []


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
    print("  FISHING MAIL - Trouver les emails des recruteurs")
    print("=" * 60)
    print(f"  {len(JOB_SITES)} sites d'emploi cibles")
    print("  Sources : France Travail + DuckDuckGo + Scraping + Hunter.io")

    # Charger historique envois
    emails_deja_envoyes = charger_emails_envoyes()
    if emails_deja_envoyes:
        print(f"  {len(emails_deja_envoyes)} emails deja contactes (seront exclus)")

    print()
    mots_cles = input("  Domaine (ex: developpeur informatique) : ").strip()
    if not mots_cles:
        mots_cles = "developpeur informatique"
        print(f"  -> Par defaut : {mots_cles}")

    region_cle, region_code, region_nom = choisir_region()
    region_label = REGIONS_LABEL.get(region_cle, region_nom)
    print(f"  -> Region : {region_label}")

    print()
    print("  Type :")
    print("    1. Stage uniquement")
    print("    2. Alternance uniquement")
    print("    3. Les deux")
    choix = input("  Choix (1/2/3) [3] : ").strip() or "3"
    types = {"1": ["stage"], "2": ["alternance"], "3": ["stage", "alternance"]}.get(choix, ["stage", "alternance"])

    # Filtres par mots-cles dans la description
    print()
    print("  Mots-cles a chercher dans les descriptions (optionnel)")
    print("  Ex: angular, react, python, java")
    filtres_input = input("  Mots-cles (vide = pas de filtre) : ").strip()
    filtres = [f.strip().lower() for f in filtres_input.split(",") if f.strip()] if filtres_input else []

    # ======= COLLECTE =======
    print()
    print("  " + "=" * 50)
    print("  COLLECTE (ca peut prendre 1-2 min)")
    print("  " + "=" * 50)

    toutes_offres = []

    # 1. France Travail
    print("\n  [1/3] France Travail API...")
    token = get_france_travail_token()
    if token:
        for t in types:
            offres = chercher_france_travail(token, f"{t} {mots_cles}", region_code)
            print(f"    -> {len(offres)} offres ({t})")
            toutes_offres.extend(offres)

    # 2. DuckDuckGo (lib python, pas de CAPTCHA)
    print(f"\n  [2/3] DuckDuckGo Search...")
    offres_ddg = chercher_duckduckgo_jobs(mots_cles, region_label, types)
    print(f"    => {len(offres_ddg)} entreprises via DuckDuckGo")
    toutes_offres.extend(offres_ddg)

    # 3. Scraping direct
    print(f"\n  [3/3] Scraping direct (6 sites)...")
    offres_scraping = scraper_sites_directs(mots_cles, region_label, types)
    print(f"    => {len(offres_scraping)} offres via scraping")
    toutes_offres.extend(offres_scraping)

    # Dedup
    vus = set()
    offres_uniques = []
    for o in toutes_offres:
        nom = o["entreprise"].strip().lower()
        if nom and nom != "inconnue" and len(nom) > 1 and nom not in vus:
            vus.add(nom)
            offres_uniques.append(o)

    print(f"\n  => TOTAL : {len(offres_uniques)} entreprises uniques")

    # Filtrage par mots-cles
    if filtres:
        avant = len(offres_uniques)
        offres_filtrees = []
        for o in offres_uniques:
            texte = (o.get("titre", "") + " " + o.get("description", "")).lower()
            mots_trouves = [f for f in filtres if f in texte]
            if mots_trouves:
                o["mots_trouves"] = mots_trouves
                offres_filtrees.append(o)
        offres_uniques = offres_filtrees
        print(f"  => FILTRE : {len(offres_uniques)}/{avant} offres contiennent {filtres}")

    if not offres_uniques:
        print("  [!] Aucune offre trouvee.")
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

    # Phase 1
    offres_sans = []
    for o in offres_uniques:
        if o["email"] and is_valid_email(o["email"]) and o["email"] not in emails_vus:
            emails_vus.add(o["email"])
            resultats.append(o)
        else:
            offres_sans.append(o)

    print(f"\n  Phase 1 - Emails dans les offres : {len(resultats)}")

    # Phase 2 : Hunter.io
    if HUNTER_API_KEY and HUNTER_API_KEY != "TA_CLE_HUNTER":
        nb = min(len(offres_sans), MAX_HUNTER)
        print(f"  Phase 2 - Hunter.io ({nb} entreprises)...")

        for o in offres_sans:
            if hunter_calls >= MAX_HUNTER:
                print(f"    [!] Limite credits atteinte ({MAX_HUNTER})")
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

    # Filtrer les emails deja envoyes
    nouveaux = [r for r in resultats if r["email"].lower() not in emails_deja_envoyes]
    deja = len(resultats) - len(nouveaux)

    # ======= RESULTATS =======
    print()
    print("=" * 60)
    print(f"  RESULTATS : {len(nouveaux)} nouveaux emails !")
    if deja > 0:
        print(f"  ({deja} deja contactes, exclus)")
    print("=" * 60)

    if not nouveaux:
        print("  [!] Aucun nouvel email. Tous deja contactes ou aucun trouve.")
        return

    for i, r in enumerate(nouveaux, 1):
        print(f"\n  {i:3d}. {r['entreprise']}")
        print(f"       Email  : {r['email']}")
        print(f"       Poste  : {r['titre']}")
        if r["lieu"]:
            print(f"       Lieu   : {r['lieu']}")
        print(f"       Source : {r['source']}")
        if r.get("mots_trouves"):
            print(f"       Match  : {', '.join(r['mots_trouves'])}")

    # CSV
    fichier = os.path.join(SCRIPT_DIR, "emails_trouves.csv")
    with open(fichier, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Email", "Entreprise", "Poste", "Lieu", "Source"])
        for r in nouveaux:
            w.writerow([r["email"], r["entreprise"], r["titre"], r["lieu"], r["source"]])

    print(f"\n  [+] Sauvegarde dans emails_trouves.csv")

    # Envoyer ?
    print()
    choix = input("  Envoyer ton mail a tous ces contacts ? (o/N) : ").strip().lower()
    if choix == "o":
        from config import MON_EMAIL, OBJET
        from envoyer import envoyer_mail
        print(f"\n  [*] Envoi de {len(nouveaux)} mails...")
        ok = 0
        for i, r in enumerate(nouveaux, 1):
            email = r["email"]
            print(f"  [{i}/{len(nouveaux)}] -> {email} ({r['entreprise']})")
            try:
                envoyer_mail(email)
                sauver_email_envoye(email)
                ok += 1
                time.sleep(2)
            except Exception as e:
                print(f"    [!] Echec : {e}")
        print(f"\n  [+] {ok}/{len(nouveaux)} mails envoyes !")
        print(f"  [+] Historique mis a jour dans emails_envoyes.txt")


if __name__ == "__main__":
    main()
