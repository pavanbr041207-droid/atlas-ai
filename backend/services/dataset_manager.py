"""
services/dataset_manager.py
Profile tabular datasets and execute data queries directly (tool-first pattern).
Backend executes → LLM explains. Never ask LLM to compute what pandas can.
"""
import os
import re

GEO_WORDS  = {"district", "state", "region", "city", "taluk", "area",
               "location", "name", "place", "county", "province", "country", "block"}
DATE_WORDS = {"date", "year", "month", "quarter", "period", "time", "week", "day"}

KA_DISTRICTS_LC = {
    "bagalkot","ballari","belagavi","bengaluru rural","bengaluru urban","bidar",
    "chamarajanagar","chikkaballapur","chikkamagaluru","chitradurga","dakshina kannada",
    "davanagere","dharwad","gadag","hassan","haveri","kalaburagi","kodagu","kolar",
    "koppal","mandya","mysuru","mysore","raichur","ramanagara","shivamogga","tumakuru",
    "udupi","uttara kannada","vijayanagara","vijayapura","yadgir","gulbarga","bellary",
}


def profile_dataset(file_path: str, filename: str = "", file_id: str = "") -> dict:
    """
    Generate comprehensive dataset profile.
    Returns dict with rows, cols, col_types, stats, geo detection, preview, etc.
    """
    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas not available"}

    ext = os.path.splitext(filename or file_path)[1].lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        elif ext == ".json":
            df = pd.read_json(file_path)
        else:
            # Try CSV as fallback
            df = pd.read_csv(file_path)
    except Exception as e:
        return {"error": str(e), "file_path": file_path, "filename": filename}

    if df.empty:
        return {"error": "Empty file", "file_path": file_path}

    df = _coerce_numeric(df)

    cols      = list(df.columns)
    col_types = {}
    for c in cols:
        dtype = str(df[c].dtype)
        if "int" in dtype or "float" in dtype:
            col_types[c] = "numeric"
        elif "datetime" in dtype:
            col_types[c] = "datetime"
        else:
            col_types[c] = "text"

    null_counts   = {c: int(df[c].isnull().sum()) for c in cols}
    unique_counts = {c: int(df[c].nunique()) for c in cols}

    # Statistics for numeric columns
    statistics = {}
    for c in cols:
        if col_types[c] == "numeric":
            s = df[c].dropna()
            if len(s) > 0:
                statistics[c] = {
                    "min":    round(float(s.min()), 2),
                    "max":    round(float(s.max()), 2),
                    "mean":   round(float(s.mean()), 2),
                    "median": round(float(s.median()), 2),
                    "sum":    round(float(s.sum()), 2),
                }

    geo_col, geo_scope = _detect_geo_col(df, cols, col_types)
    date_col           = _detect_date_col(cols)
    value_col          = _detect_value_col(df, cols, col_types, geo_col)
    geo_values         = df[geo_col].dropna().astype(str).tolist() if geo_col else []
    preview            = df.head(5).to_csv(index=False)

    return {
        "rows":          len(df),
        "col_count":     len(cols),
        "columns":       cols,
        "col_types":     col_types,
        "null_counts":   null_counts,
        "unique_counts": unique_counts,
        "statistics":    statistics,
        "geo_detected":  bool(geo_col),
        "geo_col":       geo_col,
        "geo_scope":     geo_scope,
        "date_detected": bool(date_col),
        "date_col":      date_col,
        "value_col":     value_col,
        "geo_values":    geo_values,
        "preview":       preview,
        "file_path":     file_path,
        "filename":      filename,
        "file_id":       file_id,
    }


def execute_data_query(query: str, file_path: str, profile: dict) -> dict:
    """
    Execute data query directly via pandas (tool-first execution).
    Backend computes the answer; LLM just explains it.
    Returns: {executed, operation, result_text, result_data}
    """
    try:
        import pandas as pd
    except ImportError:
        return {"executed": False}

    q = query.lower().strip()

    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
        df = _coerce_numeric(df)
    except Exception as e:
        return {"executed": False, "error": str(e)}

    geo_col   = profile.get("geo_col")
    value_col = profile.get("value_col")
    cols      = profile.get("columns", list(df.columns))

    # Auto-detect if profile missing
    if not geo_col or not value_col:
        col_types = {}
        for c in list(df.columns):
            dtype = str(df[c].dtype)
            col_types[c] = "numeric" if ("int" in dtype or "float" in dtype) else "text"
        if not geo_col:
            geo_col, _ = _detect_geo_col(df, list(df.columns), col_types)
        if not value_col:
            value_col = _detect_value_col(df, list(df.columns), col_types, geo_col)

    result_text = None
    result_data = None
    operation   = None

    # ── Priority order: most specific first, generic last ─────────────────
    # 1. COLUMNS  (before LIST — "what are the columns" must not hit LIST)
    # 2. NORMALIZE (before LIST — "normalize district names" must not hit LIST)
    # 3. DUPLICATES
    # 4. GROUP BY  (before COUNT — "count X by Y" must not hit bare COUNT)
    # 5. ROWS / SIZE
    # 6. COUNT
    # 7. LIST
    # 8. MAX / MIN / AVERAGE / SUM / TOP-N / DESCRIBE

    # ── COLUMNS / FIELDS / SCHEMA ─────────────────────────────────────────
    if re.search(r"\b(columns?|fields?|schema|headers?|structure)\b", q):
        result_text = ", ".join(cols)
        result_data = {"columns": cols, "count": len(cols)}
        operation   = "schema"

    # ── ROWS / SIZE / SHAPE ───────────────────────────────────────────────
    elif re.search(r"\b(rows?|size|shape|how big|records?|entries)\b", q) and not re.search(r"\b(list|show|name)\b", q):
        result_text = f"{len(df)} rows × {len(cols)} columns"
        result_data = {"rows": len(df), "cols": len(cols)}
        operation   = "size"

    # ── NORMALIZE / SPELLING / CLEAN ─────────────────────────────────────
    elif re.search(r"\b(normalize|normalise|fix\s+spelling|clean\s+data|correct\s+names?|standardize|standardise)\b", q):
        if geo_col:
            try:
                from services.geography_normalizer import normalize as _norm
                original  = df[geo_col].dropna().astype(str).tolist()
                normed    = [_norm(v) for v in original]
                changes   = [(o, n) for o, n in zip(original, normed) if o != n]
                unique_changes = list(dict.fromkeys(changes))[:20]
                if unique_changes:
                    lines = [f"Normalized {len(unique_changes)} unique values in '{geo_col}':"]
                    for o, n in unique_changes:
                        lines.append(f"  {o!r} → {n!r}")
                    result_text = "\n".join(lines)
                else:
                    result_text = f"All values in '{geo_col}' are already normalized."
                result_data = {"changes": [{"from": o, "to": n} for o, n in unique_changes]}
                operation   = "normalize"
            except Exception:
                result_text = f"Normalization check run on column '{geo_col}'."
                result_data = {}
                operation   = "normalize"

    # ── FIND DUPLICATES ───────────────────────────────────────────────────
    elif re.search(r"\b(duplicate|duplicates|repeated|repeating|double)\b", q):
        dup_col = geo_col or (cols[0] if cols else None)
        if dup_col:
            dups = df[df.duplicated(subset=[dup_col], keep=False)]
            dup_vals = dups[dup_col].value_counts()
            if len(dup_vals) == 0:
                result_text = f"No duplicates found in column '{dup_col}'."
            else:
                lines = [f"Found {len(dups)} duplicate rows ({len(dup_vals)} values duplicated):"]
                for val, cnt in dup_vals.head(20).items():
                    lines.append(f"• {val}: appears {cnt} times")
                result_text = "\n".join(lines)
            result_data = {"duplicate_count": len(dups), "duplicated_values": dup_vals.to_dict()}
            operation   = "find_duplicates"

    # ── GROUP BY / COUNT BY / AGGREGATE BY ───────────────────────────────
    elif re.search(r"\bby\s+(district|state|region|area|taluk|city|gender|category|type|year|month)\b", q) \
         or re.search(r"\b(group\s*by|grouped\s*by|breakdown|per\s+district|per\s+state)\b", q) \
         or re.search(r"\b(count|sum|average|total)\s+\w+\s+by\b", q):

        group_col = geo_col
        # Build local col_types for group column detection
        _local_col_types = {c: ("numeric" if ("int" in str(df[c].dtype) or "float" in str(df[c].dtype)) else "text") for c in cols}
        for c in cols:
            cl = c.lower()
            if any(re.search(rf"\b{re.escape(w)}\b", q) for w in [cl, cl.rstrip("s")]):
                if _local_col_types.get(c) == "text":
                    group_col = c
                    break

        if group_col and group_col in df.columns:
            if re.search(r"\b(sum|total)\b", q) and value_col:
                agg = df.groupby(group_col)[value_col].sum().reset_index()
                agg = agg.sort_values(value_col, ascending=False)
                rows_out = [(str(r[group_col]), round(float(r[value_col]), 2)) for _, r in agg.iterrows()]
                result_text = "\n".join(f"• {n}: {v}" for n, v in rows_out[:30])
                result_data = {"groups": [{"name": n, "value": v} for n, v in rows_out]}
                operation   = "groupby_sum"
            elif re.search(r"\b(average|mean|avg)\b", q) and value_col:
                agg = df.groupby(group_col)[value_col].mean().reset_index()
                agg[value_col] = agg[value_col].round(2)
                agg = agg.sort_values(value_col, ascending=False)
                rows_out = [(str(r[group_col]), float(r[value_col])) for _, r in agg.iterrows()]
                result_text = "\n".join(f"• {n}: {v}" for n, v in rows_out[:30])
                result_data = {"groups": [{"name": n, "value": v} for n, v in rows_out]}
                operation   = "groupby_mean"
            else:
                counts = df.groupby(group_col).size().reset_index(name="Count")
                counts = counts.sort_values("Count", ascending=False)
                rows_out = [(str(r[group_col]), int(r["Count"])) for _, r in counts.iterrows()]
                result_text = "\n".join(f"• {n}: {v}" for n, v in rows_out[:30])
                result_data = {"groups": [{"name": n, "count": v} for n, v in rows_out],
                               "total_groups": len(rows_out)}
                operation   = "groupby_count"

    # ── COUNT / HOW MANY ──────────────────────────────────────────────────
    elif re.search(r"\b(count|how many|total number|number of)\b", q):
        if geo_col and re.search(r"\b(districts?|states?|regions?|taluks?|unique|areas?|cities?|places?)\b", q):
            vals  = df[geo_col].dropna().astype(str).unique().tolist()
            count = len(vals)
            result_text = str(count)
            result_data = {"count": count, "column": geo_col, "sample": vals[:5]}
            operation   = "count_unique"
        else:
            count = len(df)
            result_text = str(count)
            result_data = {"count": count}
            operation   = "count_rows"

    # ── LIST / SHOW ALL / NAMES ───────────────────────────────────────────
    elif re.search(
        r"(list|show all|show me all|names of|all districts|all states|all regions|display all"
        r"|show\s+(?:district|state|region|area)\s+names?"
        r"|(?:district|state|region|area)\s+names?"
        r"|what are the\s+(?:districts?|states?|regions?|areas?|names?))\b", q
    ):
        if geo_col:
            vals = sorted(df[geo_col].dropna().astype(str).unique().tolist())
            result_text = "\n".join(f"• {v}" for v in vals)
            result_data = {"values": vals, "count": len(vals), "column": geo_col}
            operation   = "list_values"
        elif cols:
            vals = df[cols[0]].dropna().astype(str).unique().tolist()
            result_text = "\n".join(f"• {v}" for v in sorted(vals)[:50])
            result_data = {"values": vals}
            operation   = "list_values"

    # ── MAXIMUM / HIGHEST / LARGEST / MOST / TOP ─────────────────────────
    elif re.search(r"\b(maximum|highest|largest|most|max)\b", q) and value_col:
        try:
            import pandas as pd
            idx = df[value_col].idxmax()
            row = df.loc[idx]
            if geo_col:
                name = str(row[geo_col])
                val  = row[value_col]
                result_text = f"{name} ({val})"
                result_data = {"name": name, "value": float(val) if pd.notna(val) else None, "column": value_col}
            else:
                val = df[value_col].max()
                result_text = str(round(float(val), 2))
                result_data = {"max": float(val)}
            operation = "find_max"
        except Exception:
            pass

    # ── MINIMUM / LOWEST / SMALLEST / LEAST ──────────────────────────────
    elif re.search(r"\b(minimum|lowest|smallest|least|min)\b", q) and value_col:
        try:
            import pandas as pd
            idx = df[value_col].idxmin()
            row = df.loc[idx]
            if geo_col:
                name = str(row[geo_col])
                val  = row[value_col]
                result_text = f"{name} ({val})"
                result_data = {"name": name, "value": float(val) if pd.notna(val) else None}
            else:
                val = df[value_col].min()
                result_text = str(round(float(val), 2))
                result_data = {"min": float(val)}
            operation = "find_min"
        except Exception:
            pass

    # ── AVERAGE / MEAN ────────────────────────────────────────────────────
    elif re.search(r"\b(average|mean|avg)\b", q) and value_col:
        val = df[value_col].mean()
        result_text = str(round(float(val), 2))
        result_data = {"mean": float(val), "column": value_col}
        operation   = "average"

    # ── SUM / TOTAL ───────────────────────────────────────────────────────
    elif re.search(r"\b(sum|total|combined)\b", q) and value_col:
        val = df[value_col].sum()
        result_text = str(round(float(val), 2))
        result_data = {"sum": float(val), "column": value_col}
        operation   = "sum"

    # ── TOP N / BOTTOM N ──────────────────────────────────────────────────
    elif re.search(r"\b(top|bottom)\s+(\d+)\b", q):
        m = re.search(r"\b(top|bottom)\s+(\d+)\b", q)
        direction = m.group(1)
        n         = int(m.group(2))
        ascending = (direction == "bottom")
        if value_col:
            ranked = df.sort_values(value_col, ascending=ascending).head(n)
            if geo_col:
                rows_list = [(str(r[geo_col]), round(float(r[value_col]), 2))
                             for _, r in ranked.iterrows()
                             if __import__("pandas").notna(r[value_col])]
                result_text = "\n".join(f"{i+1}. {name}: {val}" for i, (name, val) in enumerate(rows_list))
                result_data = {"rows": [{"name": n, "value": v} for n, v in rows_list]}
            else:
                vals = ranked[value_col].tolist()
                result_text = "\n".join(f"{i+1}. {v}" for i, v in enumerate(vals))
                result_data = {"values": vals}
            operation = f"rank_{direction}"

    # ── DESCRIBE / STATISTICS / SUMMARY ──────────────────────────────────
    elif re.search(r"\b(describe|statistics|stats|summary|profile|distribution)\b", q):
        lines = [f"Dataset: {len(df)} rows × {len(cols)} columns"]
        for c in cols:
            dtype = str(df[c].dtype)
            if "int" in dtype or "float" in dtype:
                s = df[c].dropna()
                if len(s) > 0:
                    lines.append(f"{c}: min={round(float(s.min()),2)}, max={round(float(s.max()),2)}, mean={round(float(s.mean()),2)}")
        result_text = "\n".join(lines)
        result_data = {"shape": [len(df), len(cols)], "numeric_columns": [c for c in cols if "int" in str(df[c].dtype) or "float" in str(df[c].dtype)]}
        operation   = "describe"

    if result_text is None:
        return {"executed": False}

    return {
        "executed":    True,
        "operation":   operation,
        "result_text": result_text,
        "result_data": result_data,
    }


def _coerce_numeric(df):
    """Try to convert stringified numbers to actual numeric types."""
    for col in df.columns:
        try:
            converted = __import__("pandas").to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce"
            )
            if converted.notna().sum() > len(df) * 0.5:
                df[col] = converted
        except Exception:
            pass
    return df


def _detect_geo_col(df, cols, col_types):
    for c in cols:
        cl = c.lower().replace("_", " ").replace("-", " ")
        if any(w in cl for w in GEO_WORDS) and col_types.get(c) == "text":
            sample = df[c].dropna().astype(str).str.lower().tolist()[:15]
            ka_matches = sum(
                1 for v in sample
                if v in KA_DISTRICTS_LC or any(d in v for d in KA_DISTRICTS_LC)
            )
            if ka_matches > 0:
                return c, "karnataka"
            return c, "general"
    return None, None


def _detect_date_col(cols):
    for c in cols:
        if any(w in c.lower() for w in DATE_WORDS):
            return c
    return None


def _detect_value_col(df, cols, col_types, geo_col):
    for c in cols:
        if c == geo_col:
            continue
        if col_types.get(c) == "numeric":
            return c
    return None
