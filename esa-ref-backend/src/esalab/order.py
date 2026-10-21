"""IEEE citation order: numbers follow first appearance in the text; `[+k]` is a placeholder for new entry k."""
from __future__ import annotations

import re

# one citation group: [3], [3, 5], [3-5], [3]–[5], [+1], [2, +1]
GROUP_RE = re.compile(r"\[\s*\+?\d+(?:\s*[-–,，]\s*\+?\d+)*\s*\](?:\s*[-–]\s*\[\s*\+?\d+\s*\])?")
NUM_RE = re.compile(r"(\+?\d+)(?:\s*[-–\]]\s*\[?\s*(\+?\d+))?")

Ref = int | str  # 3 or "+1"


def _ref(tok: str) -> Ref:
    return tok if tok.startswith("+") else int(tok)


def parse_group(group: str) -> list[Ref]:
    """'[3]–[5]' -> [3, 4, 5]; '[2, +1]' -> [2, '+1']."""
    body = group.replace("]", "]").strip()
    refs: list[Ref] = []
    for m in re.finditer(r"(\+?\d+)\s*(?:[-–]\s*\]?\s*\[?\s*(\+?\d+))?", body.strip("[]")) if "]" not in body.strip("[]") else re.finditer(r"(\+?\d+)\s*\]\s*[-–]\s*\[\s*(\+?\d+)", body):
        a, b = _ref(m.group(1)), m.group(2)
        if b and isinstance(a, int) and not b.startswith("+") and int(b) >= a:
            refs.extend(range(a, int(b) + 1))
        else:
            refs.append(a)
            if b:
                refs.append(_ref(b))
    return refs


def cited_sequence(texts: list[str]) -> list[Ref]:
    """Distinct refs in order of first appearance across the body paragraphs."""
    seen: list[Ref] = []
    for t in texts:
        for g in GROUP_RE.findall(t):
            for r in parse_group(g):
                if r not in seen:
                    seen.append(r)
    return seen


def plan(existing: int, cited: list[Ref], new: list[int], aliases: dict[str, int] | None = None) -> dict:
    """Final list order. existing = count of current entries (numbered 1..existing); new = line numbers k of
    entries to add; aliases maps '+k' of a duplicate title to the existing number it already has."""
    aliases = aliases or {}
    cited = [aliases.get(r, r) if isinstance(r, str) else r for r in cited]
    order: list[Ref] = []
    unknown: list[Ref] = []
    for r in cited:
        if r in order:
            continue
        if (isinstance(r, int) and 1 <= r <= existing) or (isinstance(r, str) and int(r[1:]) in new):
            order.append(r)
        else:
            unknown.append(r)
    uncited_old = [n for n in range(1, existing + 1) if n not in order]
    uncited_new = [f"+{k}" for k in new if f"+{k}" not in order]
    order += uncited_old + uncited_new
    number = {r: i + 1 for i, r in enumerate(order)}
    renumber = {n: number[n] for n in range(1, existing + 1) if number[n] != n}
    return {
        "ok": not renumber and not [r for r in order if isinstance(r, str)] and not unknown,
        "order": order,  # final position -> original ref ("+k" = new entry k)
        "renumber": renumber,  # old number -> new number (only the ones that move)
        "placeholders": {r: number[r] for r in order if isinstance(r, str)} | {a: number[aliases[a]] for a in aliases if aliases[a] in number},
        "uncited": uncited_old + uncited_new,  # old numbers and "+k": in the list but never cited
        "unknown": unknown,  # cited in the text but no such entry / no such title line
    }


def _fmt(nums: list[int]) -> str:
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"[{nums[i]}]–[{nums[j]}]" if j - i >= 2 else ", ".join(f"[{n}]" for n in nums[i:j + 1]))
        i = j + 1
    return ", ".join(out)


def rewrite(text: str, number: dict[Ref, int]) -> str:
    """Rewrite every citation group with the final numbers; refs not in `number` are left as they are."""
    def sub(m):
        refs = parse_group(m.group())
        if any(isinstance(r, str) and r not in number for r in refs):  # unresolved [+k]: leave the group alone
            return m.group()
        return _fmt([number.get(r, r) for r in refs])  # an unknown old number ([54] of 30) is kept as written
    return GROUP_RE.sub(sub, text)


def final_numbers(p: dict) -> dict[Ref, int]:
    """Mapping usable by rewrite(): old number -> new number, '+k' -> new number."""
    return {r: i + 1 for i, r in enumerate(p["order"])} | {k: v for k, v in p["placeholders"].items()}
