"""Pure business logic: prompt building."""
import json

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


