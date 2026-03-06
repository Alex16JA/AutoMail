import requests
import csv
import json
import os
import re
import sys
import time
from urllib.parse import urlparse, quote_plus, unquote
from bs4 import BeautifulSoup
from fishing_config import (
    FRANCE_TRAVAIL_CLIENT_ID,
    FRANCE_TRAVAIL_CLIENT_SECRET,
    HUNTER_API_KEY,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "DNT": "1",
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


# ============================================================
# VALIDATION EMAIL
# ============================================================
def is_valid_email(email):
    """Verifie qu'une string est bien un email valide"""
    if not email or "@" not in email:
        return False
    # Doit matcher le format basique email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email.strip()):
        return False
    # Rejeter les trucs qui sont clairement pas des emails
    bad = ["francetravail.fr", "candidat.", "postuler", "lien", "http", "offres"]
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
                "source": "France Travail",
            })
        return offres
    except Exception as e:
        print(f"    [!] Erreur : {e}")
        return []


# ============================================================
# SOURCE 2 : DUCKDUCKGO (ne bloque pas comme Google)
# ============================================================
def duckduckgo_search(query, max_results=30):
    """Cherche sur DuckDuckGo HTML (pas de CAPTCHA)"""
    resultats = []
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        resp = requests.get(url, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "text/html",
        }, timeout=15)

        if resp.status_code != 200:
            return resultats

        soup = BeautifulSoup(resp.text, "html.parser")

        # DuckDuckGo HTML results
        for result in soup.find_all("div", class_="result"):
            title_el = result.find("a", class_="result__a")
            snippet_el = result.find("a", class_="result__snippet")

            if not title_el:
                continue

            href = title_el.get("href", "")
            # DuckDuckGo encode les URLs via redirect
            if "uddg=" in href:
                match = re.search(r'uddg=([^&]+)', href)
                if match:
                    href = unquote(match.group(1))

            titre = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if href and titre:
                resultats.append({"url": href, "titre": titre, "snippet": snippet})

            if len(resultats) >= max_results:
                break

    except Exception as e:
        print(f"    [!] Erreur DuckDuckGo : {e}")

    return resultats


def extraire_entreprise_from_result(resultat):
    """Extraire le nom de l'entreprise depuis un résultat de recherche"""
    titre = resultat["titre"]
    url = resultat["url"]

    entreprise = ""

    # WTTJ : /companies/nom-entreprise
    if "welcometothejungle.com" in url:
        match = re.search(r'/companies/([^/]+)', url)
        if match:
            return match.group(1).replace("-", " ").title()

    # Patterns dans les titres
    # "Poste - Entreprise - Lieu" ou "Poste | Entreprise"
    parts = re.split(r'\s*[-|–—]\s*', titre)

    # Filtrer les parties qui sont des noms de job boards ou des postes generiques
    noise = {"indeed", "hellowork", "linkedin", "glassdoor", "apec", "monster",
             "cadremploi", "welcome to the jungle", "meteojob", "talent.com",
             "jooble", "optioncarriere", "keljob", "regionsjob", "jobijoba",
             "stage", "alternance", "emploi", "offre", "offres", "paris",
             "france", "ile de france", "h/f", "f/h", "cdi", "cdd", "recrutement",
             "wizbii", "jobteaser", "directemploi", "studyrama", "letudiant",
             "postuler", "candidature", "recherche", "stepstone"}

    for part in parts:
        clean = part.strip()
        if (clean and len(clean) > 2 and len(clean) < 60
                and clean.lower() not in noise
                and not any(n in clean.lower() for n in ["stage ", "alternance ", "offre ", "emploi ", "recrute"])
                and not clean[0].islower()):  # Les noms d'entreprise commencent en majuscule
            entreprise = clean
            # On prefere les parties du milieu/fin (souvent le nom d'entreprise)

    return entreprise


def chercher_duckduckgo_jobs(mots_cles, region_label, types):
    """Cherche sur DuckDuckGo pour trouver des offres sur tous les sites d'emploi"""
    offres = []
    entreprises_vues = set()

    for t in types:
        # Requetes ciblees sur les sites d'emploi
        queries = [
            f'{t} {mots_cles} {region_label} site:welcometothejungle.com',
            f'{t} {mots_cles} {region_label} site:indeed.fr',
            f'{t} {mots_cles} {region_label} site:hellowork.com',
            f'{t} {mots_cles} {region_label} site:apec.fr',
            f'{t} {mots_cles} {region_label} recrutement',
            f'{t} {mots_cles} {region_label} postuler entreprise',
            f'"{t}" "{mots_cles}" "{region_label}" contact email entreprise',
        ]

        for query in queries:
            resultats = duckduckgo_search(query, max_results=15)
            print(f"    [{t}] {len(resultats)} resultats pour : {query[:60]}...")

            for r in resultats:
                entreprise = extraire_entreprise_from_result(r)
                if entreprise and entreprise.lower() not in entreprises_vues:
                    entreprises_vues.add(entreprise.lower())

                    url_ent = ""
                    parsed = urlparse(r["url"])
                    domain = (parsed.netloc or "").replace("www.", "")
                    if domain and not any(jb in domain for jb in JOB_SITES):
                        url_ent = f"https://{domain}"

                    email = ""
                    found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r["snippet"])
                    for f in found:
                        if is_valid_email(f):
                            email = f.lower()
                            break

                    offres.append({
                        "titre": r["titre"],
                        "entreprise": entreprise,
                        "url_entreprise": url_ent,
                        "lieu": region_label,
                        "email": email,
                        "source": f"DuckDuckGo ({domain})",
                    })

            time.sleep(2)  # Respecter DuckDuckGo

    return offres


# ============================================================
# SOURCE 3 : SCRAPING DIRECT (JSON-LD + HTML)
# ============================================================
def scraper_site_direct(url, source_name):
    """Scrape un site et extrait les JSON-LD JobPosting + HTML"""
    offres = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return offres

        soup = BeautifulSoup(resp.text, "html.parser")

        # JSON-LD
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                # Aussi chercher dans @graph
                for item in items:
                    if isinstance(item, dict) and "@graph" in item:
                        items.extend(item["@graph"])

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") in ["JobPosting", "jobPosting"]:
                        org = item.get("hiringOrganization", {})
                        if isinstance(org, dict) and org.get("name"):
                            offres.append({
                                "titre": item.get("title", ""),
                                "entreprise": org.get("name", ""),
                                "url_entreprise": org.get("sameAs", "") or org.get("url", ""),
                                "lieu": "",
                                "email": "",
                                "source": source_name,
                            })
            except Exception:
                pass

    except Exception:
        pass
    return offres


def scraper_sites_directs(mots_cles, region_label, types):
    """Scrape directement les sites d'emploi accessibles"""
    offres = []
    region_url = quote_plus(region_label)

    for t in types:
        q = quote_plus(f"{t} {mots_cles}")
        slug = f"{t}-{mots_cles}".replace(" ", "-").lower()

        urls = [
            (f"https://fr.indeed.com/jobs?q={q}&l={region_url}", "Indeed"),
            (f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={q}&l={region_url}", "HelloWork"),
            (f"https://www.welcometothejungle.com/fr/jobs?query={q}&refinementList%5Boffices.country_code%5D%5B%5D=FR", "WTTJ"),
            (f"https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles={q}&typeContrat=104437", "Apec"),
            (f"https://fr.talent.com/jobs?q={q}&l={region_url}", "Talent.com"),
            (f"https://fr.jooble.org/emploi-{slug}", "Jooble"),
            (f"https://www.optioncarriere.com/emploi?s={q}&l={region_url}", "OptionCarriere"),
            (f"https://www.cadremploi.fr/emploi/liste_offres?motscles={q}", "Cadremploi"),
            (f"https://www.glassdoor.fr/Emploi/{slug}-emplois-SRCH_KO0,{len(slug)}.htm", "Glassdoor"),
        ]

        for url, source in urls:
            site_offres = scraper_site_direct(url, source)
            if site_offres:
                print(f"    [+] {source} : {len(site_offres)} offres")
                offres.extend(site_offres)
            time.sleep(1.5)

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
        ignore = JOB_SITES + ["francetravail.fr", "pole-emploi.fr", "google.com"]
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

    # ======= COLLECTE =======
    print()
    print("  " + "=" * 50)
    print("  COLLECTE (ca peut prendre 1-2 min, on cherche partout)")
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

    # 2. DuckDuckGo (remplace Google qui bloque)
    print(f"\n  [2/3] DuckDuckGo (sur {len(JOB_SITES)} sites d'emploi)...")
    offres_ddg = chercher_duckduckgo_jobs(mots_cles, region_label, types)
    print(f"    => {len(offres_ddg)} entreprises via DuckDuckGo")
    toutes_offres.extend(offres_ddg)

    # 3. Scraping direct
    print(f"\n  [3/3] Scraping direct (9 sites)...")
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

    # ======= RESULTATS =======
    print()
    print("=" * 60)
    print(f"  RESULTATS : {len(resultats)} emails trouves !")
    print("=" * 60)

    if not resultats:
        print("  [!] Aucun email trouve.")
        return

    for i, r in enumerate(resultats, 1):
        print(f"\n  {i:3d}. {r['entreprise']}")
        print(f"       Email  : {r['email']}")
        print(f"       Poste  : {r['titre']}")
        if r["lieu"]:
            print(f"       Lieu   : {r['lieu']}")
        print(f"       Source : {r['source']}")

    # CSV
    fichier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emails_trouves.csv")
    with open(fichier, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Email", "Entreprise", "Poste", "Lieu", "Source"])
        for r in resultats:
            w.writerow([r["email"], r["entreprise"], r["titre"], r["lieu"], r["source"]])

    print(f"\n  [+] Sauvegarde dans emails_trouves.csv")

    print()
    choix = input("  Envoyer ton mail a tous ces contacts ? (o/N) : ").strip().lower()
    if choix == "o":
        from config import MON_EMAIL, OBJET
        from envoyer import envoyer_mail
        print(f"\n  [*] Envoi de {len(resultats)} mails...")
        ok = 0
        for i, r in enumerate(resultats, 1):
            print(f"  [{i}/{len(resultats)}] -> {r['email']} ({r['entreprise']})")
            try:
                envoyer_mail(r["email"])
                ok += 1
                time.sleep(2)
            except Exception as e:
                print(f"    [!] Echec : {e}")
        print(f"\n  [+] {ok}/{len(resultats)} mails envoyes !")


if __name__ == "__main__":
    main()
