"""
utils/data_parser.py
Parses pasted tabular data from chat messages or uploaded files into DataFrames.
Supported inputs: CSV text, TSV text, space-separated, XLSX, XLS, CSV files.
"""
import re, io, os
import pandas as pd


# ── Accepted upload extensions ────────────────────────────────────────────────
ACCEPTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".tsv", ".txt"}


def parse_message_data(message: str) -> pd.DataFrame | None:
    """
    Extract a DataFrame from pasted tabular data inside a chat message.
    Returns None if no table found.
    """
    # Remove code fences
    text = re.sub(r"```[a-zA-Z]*\n?", "", message).strip()
    text = re.sub(r"```", "", text).strip()

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Find the block that looks most like a table
    table_lines = _extract_table_block(lines)
    if not table_lines or len(table_lines) < 2:
        return None

    # Try CSV
    df = _try_parse(table_lines, sep=",")
    if df is not None:
        return df

    # Try TSV
    df = _try_parse(table_lines, sep="\t")
    if df is not None:
        return df

    # Try pipe-separated (markdown tables)
    if "|" in table_lines[0]:
        cleaned = []
        for l in table_lines:
            l = l.strip("|").strip()
            if re.match(r"^[\s\-|:]+$", l):
                continue
            cleaned.append(l)
        df = _try_parse(cleaned, sep="|")
        if df is not None:
            return df

    # Try whitespace-separated
    df = _try_parse(table_lines, sep=r"\s{2,}")
    if df is not None:
        return df

    return None


def parse_uploaded_file(file_path: str) -> tuple[pd.DataFrame | None, str]:
    """
    Parse an uploaded file into a DataFrame.
    Returns (DataFrame, error_message).
    error_message is empty string on success.
    """
    _, ext = os.path.splitext(file_path.lower())

    if ext not in ACCEPTED_EXTENSIONS:
        accepted = ", ".join(sorted(ACCEPTED_EXTENSIONS))
        return None, (
            f"❌ Unsupported file type `{ext}`.\n"
            f"Please upload one of: **{accepted}**"
        )

    try:
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        elif ext in (".tsv",):
            df = pd.read_csv(file_path, sep="\t")
        else:  # .csv, .txt
            # Try comma first, then tab, then semicolon
            for sep in [",", "\t", ";"]:
                try:
                    df = pd.read_csv(file_path, sep=sep)
                    if len(df.columns) > 1:
                        break
                except Exception:
                    continue

        if df is None or df.empty:
            return None, "❌ File appears to be empty."

        df = _clean_df(df)
        return df, ""

    except Exception as e:
        return None, f"❌ Could not read file: {e}"


def auto_select_columns(df: pd.DataFrame, chart_type: str = "bar") -> dict:
    """
    Auto-detect which columns are x (categorical) and y (numeric).
    Returns {"x_col": str, "y_cols": [str], "label_col": str|None}
    """
    if df is None or df.empty:
        return {}

    num_cols  = df.select_dtypes(include="number").columns.tolist()
    cat_cols  = df.select_dtypes(exclude="number").columns.tolist()

    x_col    = cat_cols[0]   if cat_cols  else (df.columns[0] if len(df.columns) > 0 else None)
    y_cols   = num_cols      if num_cols  else ([df.columns[1]] if len(df.columns) > 1 else [])
    label_col = cat_cols[0]  if cat_cols  else None

    return {"x_col": x_col, "y_cols": y_cols, "label_col": label_col}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_table_block(lines: list[str]) -> list[str]:
    """Find contiguous block of lines that look like table rows."""
    scored = []
    for i, l in enumerate(lines):
        sep_count = max(l.count(","), l.count("\t"), l.count("|"))
        if sep_count >= 1 or re.search(r"\s{2,}", l):
            scored.append(i)

    if not scored:
        return []

    # Find longest contiguous run
    best_start, best_end, cur_start = scored[0], scored[0], scored[0]
    for i in range(1, len(scored)):
        if scored[i] == scored[i-1] + 1:
            best_end = scored[i]
        else:
            if best_end - best_start > best_end - cur_start:
                pass
            cur_start = scored[i]
            best_end  = scored[i]

    return lines[best_start: best_end + 1]


def _try_parse(lines: list[str], sep: str) -> pd.DataFrame | None:
    try:
        text = "\n".join(lines)
        df = pd.read_csv(io.StringIO(text), sep=sep, engine="python")
        if df.shape[1] < 2 or df.shape[0] < 1:
            return None
        df = _clean_df(df)
        return df if not df.empty else None
    except Exception:
        return None


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from headers and string cells."""
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
    df = df.dropna(how="all")
    return df
