"""Explainable source-based screening. Stars never enter the usefulness score."""
import re


def screen_candidate(snapshot):
    docs = [doc for doc in snapshot.documents if doc.kind in {'readme', 'documentation'}]
    if not docs:
        return 0, ['No readable capability documentation; replace with another candidate.'], False
    text = '\n'.join(doc.text for doc in docs)
    features = {
        'reusable_interfaces': min(3, len(set(re.findall(r'\b(api|sdk|cli|library|import|endpoint|protocol|webhook)\b', text, re.I)))),
        'documented_mechanism': min(3, len(set(re.findall(r'\b(engine|parser|compiler|algorithm|stream|graph|index|sandbox|scheduler|runtime|pipeline)\b', text, re.I)))),
        'documentation_quality': min(3, len(set(re.findall(r'\b(usage|example|input|output|architecture|reference|quickstart)\b', text, re.I)))),
        'transfer_potential': min(3, len(set(re.findall(r'\b(automate|automation|integrate|integration|embed|extend|custom|programmable|plugin)\b', text, re.I)))),
    }
    skin = bool(re.search(r'\b(theme|skin|wallpaper|icon pack)\b', text[:4000], re.I))
    reusable = features['reusable_interfaces'] >= 2 and features['documented_mechanism'] >= 1
    generic = bool(re.search(r'\b(awesome list|curated list|collection of links|simple wrapper|thin wrapper)\b', text[:4000], re.I))
    eligible = not generic and (not skin or reusable) and sum(features.values()) >= 4
    reasons = [f'{key.replace("_", " ")}: {value}/3 from pinned source terms' for key, value in features.items()]
    reasons.append('Source screening is a heuristic; the deep capability brief must confirm transferability.')
    if not eligible:
        reasons.append('Insufficient documented reusable mechanism, or a theme/list/wrapper without a substantial foundation.')
    return sum(features.values()), reasons, eligible


def metadata_priority(repo):
    # Cheap ordering of the bounded screening window, not the final shortlist.
    text = repo.full_name + ' ' + repo.description
    value = len(set(re.findall(r'\b(engine|library|sdk|compiler|runtime|protocol|database|framework|agent|parser)\b', text, re.I)))
    value -= 5 * len(re.findall(r'theme|skin|wallpaper|awesome|wrapper', text, re.I))
    return -value, repo.full_name.lower()
