"""Structured explanations for incomplete extraction results."""

REQUIRED_FIELDS = {
    "daily_interest": ("symbol", "annual_yield_percent", "profit_payment_interval_months", "publication_date", "maturity_date"),
    "subscription": ("symbol", "publication_date", "maturity_date", "nominal_value_rial"),
    "opening": ("symbol", "publication_date", "maturity_date", "nominal_value_rial"),
}


def annotate(data: dict, values: list, required: tuple | None = None) -> dict:
    fields = required if required is not None else REQUIRED_FIELDS.get(data.get("document_type"), ())
    data["missing_fields"] = [key for key in fields if data.get(key) in (None, "", [])]
    reasons = []
    status = data.get("extraction_status")
    if status in {"error", "no_text", "unrecognized"}:
        reasons.append({"code": status})
    missing = data.get("missing_cached_values", 0)
    if missing:
        reasons.append({"code": "missing_values", "count": missing})
    if data.get("document_type") == "daily_interest" and not values and status not in {"error", "no_text", "unrecognized"}:
        reasons.append({"code": "missing_daily_values"})
    data["parsing_reasons"] = reasons
    return data
