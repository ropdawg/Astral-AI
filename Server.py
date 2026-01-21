from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import urllib.parse
import os
import json
from typing import Optional, List
from datetime import datetime
import multiprocessing
from groq import Groq 
app = FastAPI(title="Astral Server")

# Allow browser-based frontends to call this API (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ropdawg.github.io"],  # Allow all for deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve model path relative to this `scripts/` directory (models/ is inside `scripts/`)
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
MEMORY_PATH = os.path.join(PROJECT_ROOT, 'memory.json')
API_KEY_PATH = os.path.join(PROJECT_ROOT, 'my-groq-api.txt')
MAX_CONTEXT = 128000  # Llama3.1-70b has 131072 context
BATCH_SIZE = 128
TEMPERATURE = 0.7
TOP_P = 0.9
CPU_THREADS = min(4, multiprocessing.cpu_count())
REPLY_MAX_TOKENS = 512

# Load Groq API key from environment variable (for Render deployment)
api_key = os.environ.get('GROQ_API_KEY')
if not api_key:
    raise ValueError("GROQ_API_KEY environment variable is required")

client = Groq(api_key=api_key)
MODEL_NAME = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """
You are Astral — an AI assistant specialized in addiction support and emotional guidance.

Your PRIMARY role is:
1) Addiction support and recovery guidance (substances, porn, gaming, social media, etc.)
2) Emotional support and mental well-being

Your SECONDARY role is:
3) Practical problem-solving for everyday life, including math, coding, tech, school, work, and relationships

You always combine compassion with clear, correct solutions.

────────────────────────
PERSONALITY & TONE
────────────────────────
- Be warm, calm, empathetic, and respectful
- Never judge, shame, pressure, or belittle the user
- Speak like a trusted, understanding guide or mentor
- Be honest but gentle
- Encourage hope, growth, and self-awareness
- Do NOT sound robotic, cold, clinical, or scripted
- Do NOT rush the user

Silently adapt your tone and pacing to the user’s emotional state.

────────────────────────
EMOTIONAL AWARENESS (INTERNAL)
────────────────────────
Before responding, silently infer the user’s emotional state
(e.g. calm, stressed, sad, anxious, angry, confused, overwhelmed).

- Adjust tone, sentence length, and detail level
- If emotion is present, acknowledge it briefly and naturally
- Do not exaggerate emotions or dramatize

────────────────────────
RESPONSE FORMATTING (VERY IMPORTANT)
────────────────────────
Always keep responses clear, calm, and mobile-friendly:

- Never reply as one long paragraph
- Use short paragraphs
- Add blank lines between ideas
- Use bullet points when listing
- Use numbered steps for instructions
- Use headings when helpful
- Use tables only when comparing things
- Break complex answers into sections

Responses should feel easy to read and emotionally safe.

────────────────────────
ADDICTION SUPPORT (PRIMARY)
────────────────────────
Support users struggling with addiction (substances, porn, gaming, social media, etc.).

You MUST:
- NEVER give instructions on using, hiding, or obtaining addictive substances
- Focus on recovery, harm reduction, self-control, motivation, and long-term healing

You SHOULD:
- Help identify triggers and patterns
- Suggest healthier alternatives
- Encourage professional or real-world support when appropriate (without pressure)
- Celebrate progress, even small wins

If relapse is mentioned:
- Respond with compassion
- Avoid disappointment, shame, or judgment

────────────────────────
EMOTIONAL SUPPORT
────────────────────────
- Actively listen to the user’s feelings
- Validate emotions without judgment
- Help users understand what they’re feeling
- Offer grounding techniques, coping strategies, and healthy habits
- Encourage self-care and small positive steps

When emotions are intense:
- Slow the conversation down
- Focus on calm, breathing, and grounding
- Use gentle, reassuring language

────────────────────────
PROBLEM-SOLVING (SECONDARY)
────────────────────────
You may help with:
- Math and numbers
- Coding and programming
- Technology problems
- School and studying
- Work and productivity
- Relationships and communication
- Decision-making

When solving problems:
- Be accurate and logical
- Explain step-by-step when helpful
- Simplify if the user seems confused
- Maintain a calm, supportive tone

Ask at most ONE clarifying question when truly necessary.

────────────────────────
BOUNDARIES & SAFETY
────────────────────────
- Do NOT encourage self-harm, suicide, illegal acts, or dangerous behavior
- Do NOT claim to replace doctors, therapists, or professionals
- If the user expresses extreme distress:
  - Prioritize safety
  - Encourage grounding
  - Suggest reaching out to trusted real-world support

────────────────────────
DEFAULT RESPONSE FLOW
────────────────────────
When appropriate, structure responses as:

1) Acknowledge the user’s feelings or situation
2) Clearly address the problem or question
3) Provide practical advice or steps
4) End with encouragement or a calming closing line

────────────────────────
FINAL GOAL
────────────────────────
After every response, the user should feel:
- Heard
- Supported
- Calmer
- More capable
- More hopeful

You are not just an assistant.

You are Astral — an addiction support guide and emotional companion.
"""

class Message(BaseModel):
    text: str
    use_web: Optional[bool] = False
    web_query: Optional[str] = None


class MemoryItem(BaseModel):
    role: str
    text: str


# In-memory storage for memories (ephemeral on Render)
_memories = []


def load_memories() -> List[dict]:
    return _memories


def append_memory(role: str, text: str):
    item = {
        'role': role,
        'text': text,
        'ts': datetime.utcnow().isoformat()
    }
    _memories.append(item)
    # Keep only last 1000 memories to prevent memory bloat
    if len(_memories) > 1000:
        _memories.pop(0)


def retrieve_relevant_memories(query: str, limit: int = 5):
    # Very simple keyword overlap based retrieval.
    if not query:
        return load_memories()[-limit:]

    qwords = set([w for w in ''.join([c.lower() if c.isalnum() else ' ' for c in query]).split() if len(w) > 2])
    mems = load_memories()
    scored = []
    for m in mems:
        mwords = set([w for w in ''.join([c.lower() if c.isalnum() else ' ' for c in m.get('text','')]).split() if len(w) > 2])
        score = len(qwords & mwords)
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    # return only those with some overlap, otherwise return most recent
    results = [m for s, m in scored if s > 0]
    if not results:
        return mems[-limit:]
    return results[:limit]


def is_internet_available(timeout: int = 3) -> bool:
    try:
        requests.get('https://www.wikipedia.org', timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        return True
    except Exception:
        return False


def wiki_search(query: str, max_results: int = 3):
    """Search Wikipedia via the public API and return list of dicts with 'url' and 'text'."""
    out = []
    try:
        api = 'https://en.wikipedia.org/w/api.php'
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'format': 'json',
            'srlimit': max_results,
        }
        r = requests.get(api, params=params, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json()
        for item in data.get('query', {}).get('search', []):
            pageid = item.get('pageid')
            title = item.get('title')
            # get extract for the page
            extract = ''
            try:
                # request a longer plain-text extract (approx up to exchars)
                ex_params = {'action': 'query', 'prop': 'extracts', 'explaintext': 1, 'format': 'json', 'pageids': pageid, 'exchars': 2000}
                er = requests.get(api, params=ex_params, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                ed = er.json()
                pages = ed.get('query', {}).get('pages', {})
                extract = pages.get(str(pageid), {}).get('extract', '')
            except Exception:
                extract = ''

            if not extract:
                snippet = item.get('snippet', '')
                extract = BeautifulSoup(snippet, 'html.parser').get_text()

            url = f'https://en.wikipedia.org/?curid={pageid}'
            out.append({'url': url, 'text': extract})
    except Exception:
        pass
    return out


# Simple in-memory cache for recent web queries
_web_cache = {}


def duckduckgo_search(query: str, max_results: int = 5):
    """Perform a lightweight DuckDuckGo HTML search (no API key required).
    Returns list of {'url':..., 'text':...}
    """
    out = []
    try:
        url = 'https://html.duckduckgo.com/html/'
        params = {'q': query}
        r = requests.post(url, data=params, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
        # Try to find the more structured results first
        anchors = soup.find_all('a', attrs={'class': 'result__a'})
        if not anchors:
            anchors = soup.find_all('a')

        for a in anchors:
            href = a.get('href')
            text = a.get_text().strip()
            if not href or not href.startswith('http'):
                continue
            # try to find a nearby snippet
            snippet = ''
            parent = a.find_parent()
            if parent:
                s = parent.find('a', {'class': 'result__snippet'}) or parent.find('div', {'class': 'result__snippet'})
                if s:
                    snippet = s.get_text().strip()
            out.append({'url': href, 'text': (snippet or text)[:1600]})
            if len(out) >= max_results:
                break
    except Exception:
        pass
    return out


def bing_search(query: str, max_results: int = 5):
    """Use Bing Web Search API if `BING_API_KEY` env var is set. Returns same shape as other search fns."""
    out = []
    key = os.environ.get('BING_API_KEY')
    if not key:
        return out
    try:
        endpoint = 'https://api.bing.microsoft.com/v7.0/search'
        headers = {'Ocp-Apim-Subscription-Key': key, 'User-Agent': 'Mozilla/5.0'}
        params = {'q': query, 'count': max_results}
        r = requests.get(endpoint, headers=headers, params=params, timeout=12)
        data = r.json()
        for item in data.get('webPages', {}).get('value', []):
            out.append({'url': item.get('url'), 'text': (item.get('snippet') or '')[:1600]})
    except Exception:
        pass
    return out


def general_search(query: str, max_results: int = 5):
    """Wrapper that tries Bing (if key present) then DuckDuckGo as fallback.
    Uses a short in-memory cache to avoid repeated requests.
    """
    key = query.strip().lower()
    cache_key = f"gs:{key}:{max_results}"
    if cache_key in _web_cache:
        return _web_cache[cache_key]

    results = []
    # Prefer Bing when available
    if os.environ.get('BING_API_KEY'):
        results = bing_search(query, max_results=max_results)

    if not results:
        results = duckduckgo_search(query, max_results=max_results)

    # also include a few wiki results for authoritative references
    try:
        w = wiki_search(query, max_results=2)
        # merge unique urls
        seen = {r['url'] for r in results}
        for r in w:
            if r['url'] not in seen:
                results.append(r)
                seen.add(r['url'])
                if len(results) >= max_results:
                    break
    except Exception:
        pass

    _web_cache[cache_key] = results
    # keep cache small
    if len(_web_cache) > 128:
        # pop an arbitrary item
        _web_cache.pop(next(iter(_web_cache)))
    return results


def should_use_web(text: str) -> bool:
    """Heuristic to decide whether a query likely needs up-to-date web info.
    The client can still force the web via `use_web` flag.
    """
    if not text:
        return False
    lower = text.lower()
    # explicit user flag words
    triggers = ['latest', 'recent', 'current', 'news', 'update', 'updates', 'version', 'versions', 'released', 'release', 'announced', 'trend', 'trending', 'today']
    for t in triggers:
        if t in lower:
            return True
    # common version/year patterns
    import re
    if re.search(r'20\d{2}', text):
        return True
    # technical queries about packages, install, or compatibility
    tech_triggers = ['install', 'how to install', 'compatibl', 'compatibility', 'npm', 'pypi', 'github', 'stack overflow', 'stackoverflow']
    for t in tech_triggers:
        if t in lower:
            return True
    return False

@app.post("/chat")
def chat(msg: Message):
    # Retrieve relevant memories and include them in the prompt (simple RAG)
    relevant = retrieve_relevant_memories(msg.text, limit=5)
    mem_text = ''
    if relevant:
        mem_lines = []
        for m in relevant:
            mem_lines.append(f"- ({m.get('role','mem')}) {m.get('text','')}")
        mem_text = "Relevant memories:\n" + "\n".join(mem_lines) + "\n\n"

    web_findings = ''
    # Use web findings when the client requests it or heuristics indicate it's useful
    use_web_flag = bool(msg.use_web) or should_use_web(msg.text)
    if use_web_flag and is_internet_available(timeout=5):
        try:
            q = (msg.web_query or msg.text)[:800]
            snippets = wiki_search(q, max_results=2)
            other = general_search(q, max_results=4)
            combined = []
            seen = set()
            for s in (snippets or []) + (other or []):
                url = s.get('url') or ''
                if url in seen:
                    continue
                seen.add(url)
                combined.append(s)

            if combined:
                parts = ["Web findings:"]
                for s in combined:
                    parts.append(f"- Source: {s.get('url')}\n  Excerpt: {s.get('text','')[:800]}")
                web_findings = "\n" + "\n\n".join(parts) + "\n\n"
        except Exception as e:
            print(f"Web search error: {e}")  # Log for debugging on Render
            web_findings = ''
    else:
        web_findings = ''

    # Encourage the model to use web findings when present to produce a complete answer
    web_instructions = ''
    if web_findings:
        web_instructions = (
            "\nNote: The assistant has access to the Web findings above. "
            "Use those sources to produce a thorough, self-contained answer that cites or references the sources when useful. "
            "If sources disagree, summarize the differences and indicate uncertainty. "
            "Prefer to give a complete, clear explanation rather than a short or partial reply.\n\n"
        )

    system_content = SYSTEM_PROMPT
    user_content = mem_text + web_findings + web_instructions + "User:\n" + msg.text + "\n\nAstral:"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]

    # compute a safe max_tokens so prompt + reply <= MAX_CONTEXT
    requested = REPLY_MAX_TOKENS if web_findings else 200

    # For Groq, we can use higher max_tokens since context is larger
    reply_max = max(20, requested)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=reply_max,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        stop=["User:", "Astral:"]
    )

    reply = response.choices[0].message.content.strip()

    # Save user message and the generated reply to memory for future RAG
    try:
        append_memory('user', msg.text)
        append_memory('ai', reply)
    except Exception:
        pass

    return {"reply": reply}


@app.get('/memory')
def get_memory(query: Optional[str] = None, limit: int = 5):
    return retrieve_relevant_memories(query or '', limit)


@app.post('/memory')
def post_memory(item: MemoryItem):
    append_memory(item.role, item.text)
    return {'ok': True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
