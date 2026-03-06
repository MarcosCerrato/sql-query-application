"""Pure business logic: prompt building and hallucination detection."""
import json
import re

COLUMN_HINTS = {
    "waiter": "numeric employee ID (not a name)",
}


def build_prompt(question: str, sql: str, rows: list) -> str:
    rows_text = json.dumps(rows[:20], ensure_ascii=False)
    many_rows = len(rows) > 1
    if many_rows:
        format_rule = (
            "- Start with one natural sentence summarizing the data (e.g. 'Sales by day were:'). "
            "Then list each row as a bullet point with exact values."
        )
    else:
        format_rule = "- Respond in one short, direct sentence."

    if rows:
        hints = [f"- '{col}' = {COLUMN_HINTS[col]}"
                 for col in rows[0] if col in COLUMN_HINTS]
        hints_section = ("\nColumn notes:\n" + "\n".join(hints) + "\n") if hints else ""
    else:
        hints_section = ""

    return f"""You are a concise data analyst for a restaurant sales database.

CRITICAL: If the question is not about sales data (e.g. current date/time, health, general knowledge, greetings), respond with exactly: NOT_APPLICABLE
{hints_section}
Rules:
{format_rule}
- Include the exact value(s) from the data (names, numbers, dates, etc.).
- Do NOT repeat the question.
- Do NOT add explanations, caveats, or information not present in the data.
- Do NOT fabricate any value — if the data is empty, say so.
- Respond in the same language as the question.

Question: {question}
SQL used: {sql}
Data: {rows_text}
Answer:"""


def fallback_answer(question: str, rows: list) -> str:
    """Build a safe answer directly from data, no LLM needed."""
    if not rows:
        return "The query returned no results."
    if len(rows) == 1:
        values = ", ".join(f"{k}: {v}" for k, v in rows[0].items())
        return f"The result is: {values}."
    keys = list(rows[0].keys())
    lines = []
    for r in rows:
        parts = [str(r[k]) for k in keys]
        lines.append(": ".join(parts) if len(parts) == 2 else ", ".join(f"{k}={r[k]}" for k in keys))
    return "\n".join(f"• {line}" for line in lines)


def looks_hallucinated(text: str, rows: list) -> bool:
    """Return True if the response contains values not present in the data."""
    data_str = json.dumps(rows, ensure_ascii=False).lower()
    # Strip thousand separators (1,234,567 → 1234567) before comparing
    cleaned = re.sub(r"(\d)[,.](\d{3})(?=\D|$)", r"\1\2", text)
    cleaned = re.sub(r"(\d)[,.](\d{3})(?=\D|$)", r"\1\2", cleaned)  # second pass for long numbers
    numbers_in_response = re.findall(r"\b\d{4,}\b", cleaned)
    for n in numbers_in_response:
        if n not in data_str:
            return True
    return False


def _looks_garbled(text: str, rows: list) -> bool:
    """Detect nonsensical answers for multi-row results."""
    if len(rows) <= 1:
        return False
    # If there are N rows but the answer doesn't mention most of the key values,
    # it likely collapsed everything into a broken sentence.
    key_values = set()
    for row in rows:
        for v in row.values():
            key_values.add(str(v).lower())
    text_lower = text.lower()
    mentioned = sum(1 for v in key_values if v in text_lower)
    # Expect at least half the distinct values to appear in the answer
    return mentioned < len(key_values) / 2
