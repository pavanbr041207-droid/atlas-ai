"""
services/geography_normalizer.py
Normalize district / taluk / city names to canonical Karnataka district names.
Handles: old names, spelling errors, aliases, taluk→district, city→district.
Uses fuzzy matching as final fallback.
"""
from difflib import get_close_matches

# ── Canonical 31 KA districts ─────────────────────────────────────────────────
CANONICAL = [
    "Bagalkot", "Ballari", "Belagavi", "Bengaluru Rural", "Bengaluru Urban",
    "Bidar", "Chamarajanagar", "Chikkaballapur", "Chikkamagaluru", "Chitradurga",
    "Dakshina Kannada", "Davanagere", "Dharwad", "Gadag", "Hassan", "Haveri",
    "Kalaburagi", "Kodagu", "Kolar", "Koppal", "Mandya", "Mysuru", "Raichur",
    "Ramanagara", "Shivamogga", "Tumakuru", "Udupi", "Uttara Kannada",
    "Vijayanagara", "Vijayapura", "Yadgir",
]
CANONICAL_LC = {d.lower(): d for d in CANONICAL}

# ── Aliases: old / misspelled / alternate → canonical ────────────────────────
ALIAS: dict[str, str] = {
    # Old official names
    "belgaum":          "Belagavi",
    "bellary":          "Ballari",
    "ballary":          "Ballari",
    "bijapur":          "Vijayapura",
    "gulbarga":         "Kalaburagi",
    "shimoga":          "Shivamogga",
    "tumkur":           "Tumakuru",
    "mysore":           "Mysuru",
    "hospet":           "Vijayanagara",
    "hospete":          "Vijayanagara",
    "vijayanagar":      "Vijayanagara",
    "vijaynagara":      "Vijayanagara",
    # Spelling variants
    "banglore":         "Bengaluru Urban",
    "bangalore":        "Bengaluru Urban",
    "bengaluru":        "Bengaluru Urban",
    "bengaluru urban":  "Bengaluru Urban",
    "bengaluru rural":  "Bengaluru Rural",
    "bangalore urban":  "Bengaluru Urban",
    "bangalore rural":  "Bengaluru Rural",
    "dharwar":          "Dharwad",
    "davangere":        "Davanagere",
    "davangere":        "Davanagere",
    "davanagere":       "Davanagere",
    "bagalkote":        "Bagalkot",
    "chikmagalur":      "Chikkamagaluru",
    "chikkamagalur":    "Chikkamagaluru",
    "chamarajanagara":  "Chamarajanagar",
    "chamrajanagar":    "Chamarajanagar",
    "chickballapur":    "Chikkaballapur",
    "chikballapur":     "Chikkaballapur",
    "ramanagara":       "Ramanagara",
    "yadagir":          "Yadgir",
    "yadagiri":         "Yadgir",
    "mangalore":        "Dakshina Kannada",
    "mangaluru":        "Dakshina Kannada",
    "d. kannada":       "Dakshina Kannada",
    "dakshinakannada":  "Dakshina Kannada",
    "u. kannada":       "Uttara Kannada",
    "uttarakannada":    "Uttara Kannada",
    "karwar":           "Uttara Kannada",
    "mercara":          "Kodagu",
    "madikeri":         "Kodagu",
    "coorg":            "Kodagu",
    "kgf":              "Kolar",
    "kolar gold fields":"Kolar",
    "gadag-betageri":   "Gadag",
    "hubli":            "Dharwad",
    "hubballi":         "Dharwad",
    "hubballi-dharwad": "Dharwad",
    "udupi":            "Udupi",
    "manipal":          "Udupi",
    "hassan":           "Hassan",
    "mandya":           "Mandya",
    "bidar":            "Bidar",
    "raichur":          "Raichur",
    "koppal":           "Koppal",
    "haveri":           "Haveri",
    "gadag":            "Gadag",
    "chitradurga":      "Chitradurga",
    "kolar":            "Kolar",
}

# ── Taluk → District ──────────────────────────────────────────────────────────
TALUK: dict[str, str] = {
    # Bengaluru Urban
    "anekal": "Bengaluru Urban", "bengaluru east": "Bengaluru Urban",
    "bengaluru north": "Bengaluru Urban", "bengaluru south": "Bengaluru Urban",
    "bengaluru west": "Bengaluru Urban", "yelahanka": "Bengaluru Urban",
    "bangalore east": "Bengaluru Urban", "bangalore north": "Bengaluru Urban",
    "bangalore south": "Bengaluru Urban", "bangalore west": "Bengaluru Urban",
    "mahadevapura": "Bengaluru Urban", "peenya": "Bengaluru Urban",
    "whitefield": "Bengaluru Urban", "electronic city": "Bengaluru Urban",
    "jayanagar": "Bengaluru Urban", "indiranagar": "Bengaluru Urban",
    "koramangala": "Bengaluru Urban", "marathahalli": "Bengaluru Urban",
    "hebbal": "Bengaluru Urban", "rajajinagar": "Bengaluru Urban",
    "hsr layout": "Bengaluru Urban", "btm layout": "Bengaluru Urban",
    "jp nagar": "Bengaluru Urban", "jpnagar": "Bengaluru Urban",
    # Bengaluru Rural
    "devanahalli": "Bengaluru Rural", "doddaballapur": "Bengaluru Rural",
    "hoskote": "Bengaluru Rural", "nelamangala": "Bengaluru Rural",
    # Belagavi
    "athani": "Belagavi", "bailhongal": "Belagavi", "chikkodi": "Belagavi",
    "gokak": "Belagavi", "hukkeri": "Belagavi", "kagwad": "Belagavi",
    "khanapur": "Belagavi", "mudalagi": "Belagavi", "nippani": "Belagavi",
    "raibag": "Belagavi", "ramdurg": "Belagavi", "savadatti": "Belagavi",
    # Ballari
    "hadagali": "Ballari", "hagaribommanahalli": "Ballari",
    "kudligi": "Ballari", "sandur": "Ballari", "siraguppa": "Ballari",
    # Mysuru
    "hunsur": "Mysuru", "h.d. kote": "Mysuru", "hd kote": "Mysuru",
    "krishnarajanagara": "Mysuru", "k.r. nagar": "Mysuru", "kr nagar": "Mysuru",
    "nanjangud": "Mysuru", "periyapatna": "Mysuru", "t. narasipura": "Mysuru",
    "mysuru": "Mysuru",
    # Dakshina Kannada
    "bantwal": "Dakshina Kannada", "belthangady": "Dakshina Kannada",
    "moodbidri": "Dakshina Kannada", "puttur": "Dakshina Kannada",
    "sullia": "Dakshina Kannada", "kadaba": "Dakshina Kannada",
    # Dharwad
    "kundgol": "Dharwad", "navalgund": "Dharwad", "kalghatgi": "Dharwad",
    # Gadag
    "ron": "Gadag", "shirahatti": "Gadag", "mundargi": "Gadag", "nargund": "Gadag",
    # Hassan
    "alur": "Hassan", "arakalagudu": "Hassan", "arsikere": "Hassan",
    "belur": "Hassan", "channarayapatna": "Hassan",
    "hole narsipur": "Hassan", "sakleshpur": "Hassan",
    # Shivamogga
    "bhadravati": "Shivamogga", "hosanagar": "Shivamogga",
    "sagara": "Shivamogga", "sagar": "Shivamogga", "shikaripura": "Shivamogga",
    "soraba": "Shivamogga", "tirthahalli": "Shivamogga",
    # Chikkamagaluru
    "kadur": "Chikkamagaluru", "koppa": "Chikkamagaluru",
    "mudigere": "Chikkamagaluru", "n.r. pura": "Chikkamagaluru",
    "sringeri": "Chikkamagaluru", "tarikere": "Chikkamagaluru",
    # Chitradurga
    "challakere": "Chitradurga", "hiriyur": "Chitradurga",
    "holalkere": "Chitradurga", "hosadurga": "Chitradurga",
    "molakalmuru": "Chitradurga",
    # Udupi
    "kundapur": "Udupi", "karkala": "Udupi", "udupi": "Udupi",
    # Uttara Kannada
    "ankola": "Uttara Kannada", "bhatkal": "Uttara Kannada",
    "honnavar": "Uttara Kannada", "joida": "Uttara Kannada",
    "kumta": "Uttara Kannada", "mundgod": "Uttara Kannada",
    "siddapur": "Uttara Kannada", "sirsi": "Uttara Kannada",
    "supa": "Uttara Kannada", "yellapur": "Uttara Kannada",
    # Tumakuru
    "chiknayakanhalli": "Tumakuru", "gubbi": "Tumakuru",
    "koratagere": "Tumakuru", "kunigal": "Tumakuru",
    "madhugiri": "Tumakuru", "pavagada": "Tumakuru",
    "sira": "Tumakuru", "tiptur": "Tumakuru", "turuvekere": "Tumakuru",
    # Davanagere
    "channagiri": "Davanagere", "harihar": "Davanagere",
    "harapanahalli": "Davanagere", "honnali": "Davanagere",
    "jagalur": "Davanagere",
    # Kalaburagi
    "afzalpur": "Kalaburagi", "aland": "Kalaburagi",
    "chincholi": "Kalaburagi", "chittapur": "Kalaburagi",
    "jevargi": "Kalaburagi", "sedam": "Kalaburagi",
    # Bidar
    "aurad": "Bidar", "basavakalyan": "Bidar",
    "bhalki": "Bidar", "humnabad": "Bidar",
    # Vijayapura
    "basavana bagewadi": "Vijayapura", "bagewadi": "Vijayapura",
    "indi": "Vijayapura", "muddebihal": "Vijayapura", "sindagi": "Vijayapura",
    # Raichur
    "devadurga": "Raichur", "lingsugur": "Raichur",
    "manvi": "Raichur", "sindhanur": "Raichur",
    # Koppal
    "gangavathi": "Koppal", "kustagi": "Koppal", "yelburga": "Koppal",
    # Yadgir
    "shahapur": "Yadgir", "shorapur": "Yadgir", "surpur": "Yadgir",
    # Vijayanagara
    "hagaribommanahalli": "Vijayanagara", "harapanahalli": "Vijayanagara",
    "hoovina hadagali": "Vijayanagara", "hagari bommanahalli": "Vijayanagara",
    # Ramanagara
    "channapatna": "Ramanagara", "kanakapura": "Ramanagara",
    "magadi": "Ramanagara",
    # Kolar
    "bangarpet": "Kolar", "kolar": "Kolar",
    "malur": "Kolar", "mulbagal": "Kolar", "srinivaspur": "Kolar",
    # Chikkaballapur
    "bagepalli": "Chikkaballapur", "chintamani": "Chikkaballapur",
    "gauribidanur": "Chikkaballapur", "gudibanda": "Chikkaballapur",
    "sidlaghatta": "Chikkaballapur",
    # Mandya
    "kirugavalu": "Mandya", "krishnarajpet": "Mandya",
    "maddur": "Mandya", "malavalli": "Mandya",
    "nagamangala": "Mandya", "pandavapura": "Mandya", "srirangapatna": "Mandya",
    # Kodagu
    "madikeri": "Kodagu", "somvarpet": "Kodagu", "virajpet": "Kodagu",
    # Haveri
    "byadagi": "Haveri", "hangal": "Haveri",
    "hirekerur": "Haveri", "ranebennur": "Haveri", "savanur": "Haveri",
    # Chamarajanagar
    "chamarajanagar": "Chamarajanagar", "gundlupet": "Chamarajanagar",
    "kollegal": "Chamarajanagar", "yelandur": "Chamarajanagar",
    # Bagalkot
    "badami": "Bagalkot", "bilagi": "Bagalkot",
    "hungund": "Bagalkot", "ilkal": "Bagalkot",
    "jamkhandi": "Bagalkot", "mudhol": "Bagalkot",
}

_CACHE: dict[str, str] = {}


def normalize(name: str) -> str:
    """
    Normalize a single district/taluk/city name to canonical Karnataka district.
    Returns canonical name if matched, else returns original (title-cased).
    """
    if not name or not isinstance(name, str):
        return name

    key = name.strip().lower()
    if not key:
        return name

    # Cache hit
    if key in _CACHE:
        return _CACHE[key]

    # 1. Exact canonical match
    if key in CANONICAL_LC:
        result = CANONICAL_LC[key]
        _CACHE[key] = result
        return result

    # 2. Alias match
    if key in ALIAS:
        result = ALIAS[key]
        _CACHE[key] = result
        return result

    # 3. Taluk match
    if key in TALUK:
        result = TALUK[key]
        _CACHE[key] = result
        return result

    # 4. Fuzzy match against canonical list (cutoff 0.80)
    matches = get_close_matches(key, CANONICAL_LC.keys(), n=1, cutoff=0.80)
    if matches:
        result = CANONICAL_LC[matches[0]]
        _CACHE[key] = result
        return result

    # 5. Fuzzy match against aliases
    matches = get_close_matches(key, list(ALIAS.keys()), n=1, cutoff=0.78)
    if matches:
        result = ALIAS[matches[0]]
        _CACHE[key] = result
        return result

    # 6. Fuzzy match against taluks
    matches = get_close_matches(key, list(TALUK.keys()), n=1, cutoff=0.78)
    if matches:
        result = TALUK[matches[0]]
        _CACHE[key] = result
        return result

    # No match — return original title-cased
    result = name.strip().title()
    _CACHE[key] = result
    return result


def normalize_series(series) -> object:
    """Normalize a pandas Series of names. Returns new Series."""
    return series.map(lambda x: normalize(str(x)) if x and str(x).strip() else x)


def normalize_dataframe(df, col: str) -> object:
    """Normalize a column in a DataFrame in-place. Returns df."""
    if col and col in df.columns:
        df[col] = normalize_series(df[col])
    return df


def is_ka_district(name: str) -> bool:
    """Check if name (after normalization) is a KA district."""
    return normalize(name) in set(CANONICAL)


def batch_normalize(names: list) -> dict:
    """
    Normalize a list of names. Returns {original → canonical} dict.
    """
    return {n: normalize(n) for n in names}
