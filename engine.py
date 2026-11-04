"""Deterministic quote extraction. No model, inference or price guessing."""
import re
from decimal import Decimal

CATALOG = [
    {"id": "CP-01", "name": "Copper pipe", "unit": "piece", "price": "12.50", "aliases": ["copper pipe", "copper pipes"]},
    {"id": "SB-02", "name": "Steel bracket", "unit": "piece", "price": "4.75", "aliases": ["steel bracket", "steel brackets"]},
    {"id": "SC-03", "name": "Sealant cartridge", "unit": "piece", "price": "9.99", "aliases": ["sealant cartridge", "sealant cartridges"]},
    {"id": "IS-04", "name": "Installation service", "unit": "visit", "price": None, "aliases": ["installation service", "installation services"]},
]
BY_ID = {p["id"]: p for p in CATALOG}
NUMBERS = dict(zip("one two three four five six seven eight nine ten eleven twelve".split(), range(1, 13)))

def valid_quantity(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d{0,3}", str(value)) or int(value) > 1000:
        raise ValueError("Quantity must be a whole number from 1 to 1000.")
    return int(value)

def price_line(index, raw, product_id=None, quantity=None, issues=None):
    issues = list(issues or [])
    product = BY_ID.get(product_id)
    price = product["price"] if product else None
    if product and price is None:
        issues.append("No fixture price. This line cannot be priced.")
    subtotal = str((Decimal(price) * quantity).quantize(Decimal("0.01"))) if price and quantity and not issues else None
    return {"index": index, "raw": raw, "product_id": product_id, "name": product["name"] if product else None,
            "quantity": quantity, "unit_price": price, "subtotal": subtotal, "issues": issues,
            "status": "review" if issues else "ready"}

def summarize(lines):
    known = sum((Decimal(line["subtotal"]) for line in lines if line["subtotal"] is not None), Decimal("0.00"))
    ready = bool(lines) and all(line["status"] == "ready" for line in lines)
    return {"lines": lines, "currency": "GBP", "status": "ready" if ready else "review_required",
            "known_subtotal": f"{known:.2f}", "total": f"{known:.2f}" if ready else None,
            "review_count": sum(line["status"] != "ready" for line in lines), "catalog_version": "synthetic-2026-11-03"}

def analyze(transcript):
    text = transcript.strip().lower()
    text = re.sub(r"^(please\s+)?(quote|i need|we need|add|order)\s*[:,]?\s*", "", text)
    clauses = [s.strip(" .!?") for s in re.split(r"\s+and\s+|[,;\n]+|\.(?:\s+|$)", text) if s.strip(" .!?")]
    lines = []
    for i, clause in enumerate(clauses[:50]):
        product = next((p for p in CATALOG if any(re.search(r"\b" + re.escape(a) + r"$", clause) for a in p["aliases"])), None)
        pid = product["id"] if product else None
        if re.search(r"\b(or|maybe|about|approximately|either)\b", clause):
            lines.append(price_line(i, clause, pid, issues=["Ambiguous instruction. Confirm the item and exact quantity."]))
            continue
        match = re.fullmatch(r"(\S+)\s+(.+)", clause)
        quantity = None
        issues = []
        if match:
            token = match.group(1)
            try:
                quantity = valid_quantity(NUMBERS.get(token, token))
            except ValueError:
                issues.append("Missing or invalid quantity. Use a whole number from 1 to 1000.")
            exact_product = next((p for p in CATALOG if match.group(2) in p["aliases"]), None)
            if exact_product is None and quantity is not None:
                issues.append("Item is not an exact catalog match. Select the item explicitly.")
                pid = None
        else:
            issues.append("Expected a quantity followed by an exact catalog item.")
        if product is None and not any("catalog" in x for x in issues):
            issues.append("Unrecognized item. Select a catalog item explicitly.")
        lines.append(price_line(i, clause, pid, quantity, issues))
    if len(clauses) > 50:
        raise ValueError("At most 50 item lines are supported.")
    if not lines:
        raise ValueError("Enter a transcript with at least one item.")
    return summarize(lines)

def apply_resolutions(result, resolutions):
    lines = list(result["lines"])
    seen = set()
    for fix in resolutions:
        index = fix["index"]
        if isinstance(index, bool) or index in seen or not 0 <= index < len(lines):
            raise ValueError("Each resolution must reference a different existing line.")
        seen.add(index)
        if fix["product_id"] not in BY_ID:
            raise ValueError("Unknown catalog item.")
        quantity = valid_quantity(fix["quantity"])
        lines[index] = price_line(index, lines[index]["raw"], fix["product_id"], quantity)
        lines[index]["reviewed"] = True
    return summarize(lines)
