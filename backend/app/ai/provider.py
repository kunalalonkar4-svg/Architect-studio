"""AI providers. AnthropicProvider calls the Messages API server-side (key never leaves the server).
MockProvider is a deterministic stand-in that emits the SAME structured tool calls, used when no key
is configured and in tests. The UI always shows which one is active."""
from __future__ import annotations

import re
from typing import Iterator

from ..config import settings
from ..units import AmbiguousUnit, parse_length, parse_plot_dims


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retriable: bool = False, next_actions: list | None = None):
        super().__init__(message)
        self.code, self.message, self.retriable, self.next_actions = code, message, retriable, next_actions or []


def clean_blocks(content) -> list[dict]:
    out = []
    for b in content:
        d = b if isinstance(b, dict) else b.model_dump()
        if d.get("type") == "text":
            out.append(dict(type="text", text=d.get("text", "")))
        elif d.get("type") == "tool_use":
            out.append(dict(type="tool_use", id=d["id"], name=d["name"], input=d.get("input") or {}))
    return out


class AnthropicProvider:
    name = "anthropic"
    live = True

    def __init__(self):
        import anthropic
        if not settings.anthropic_api_key:
            raise ProviderError("no_key", "ANTHROPIC_API_KEY is not configured on the server.", False, ["Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL"])
        if not settings.anthropic_model:
            raise ProviderError("no_model", "ANTHROPIC_MODEL is not configured on the server.", False, ["Set ANTHROPIC_MODEL"])
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=settings.ai_timeout_s, max_retries=settings.ai_max_retries)
        self.strict = True

    def stream_turn(self, system, messages, tools, state=None) -> Iterator[tuple]:
        from .tools import anthropic_tools
        a = self.anthropic
        for attempt in (0, 1):
            try:
                with self.client.messages.stream(model=settings.anthropic_model, max_tokens=settings.ai_max_tokens, system=system,
                                                 tools=anthropic_tools(self.strict), messages=messages) as stream:
                    for t in stream.text_stream:
                        yield ("text", t)
                    final = stream.get_final_message()
                yield ("blocks", clean_blocks(final.content), dict(input=final.usage.input_tokens, output=final.usage.output_tokens))
                return
            except a.BadRequestError as e:
                if attempt == 0 and self.strict and re.search(r"strict|schema|output_format", str(e), re.I):
                    self.strict = False      # bounded fallback: schema is still enforced server-side by pydantic
                    continue
                raise ProviderError("bad_request", f"The AI provider rejected the request: {str(e)[:200]}", False)
            except a.AuthenticationError:
                raise ProviderError("auth", "The AI provider rejected the API key.", False, ["Check ANTHROPIC_API_KEY on the server"])
            except a.PermissionDeniedError:
                raise ProviderError("auth", "The API key does not have permission for this model.", False, ["Check the key and ANTHROPIC_MODEL"])
            except a.NotFoundError:
                raise ProviderError("no_model", f"Model '{settings.anthropic_model}' was not found for this key.", False, ["Check ANTHROPIC_MODEL"])
            except a.RateLimitError:
                raise ProviderError("rate_limited", "The AI provider is rate-limiting requests. Try again shortly.", True, ["Retry in a minute"])
            except (a.APIConnectionError, a.APITimeoutError):
                raise ProviderError("unavailable", "Could not reach the AI provider (network or timeout).", True, ["Retry", "Your project and drawings are unchanged"])
            except a.APIStatusError as e:
                raise ProviderError("unavailable", f"The AI provider returned an error ({e.status_code}).", True, ["Retry"])


# ============================================================ deterministic mock
HINGLISH = re.compile(r"\b(ka|ki|ke|hai|hain|chahiye|karo|kar|mein|me|aur|par|rakho|rakhna|shift|dikhao|banao|do|dena|wala|nahi|badho|aage|peeche|pichhe|seedhi|rasoi|kamre|kamra|ek|teen|abhi|baad)\b", re.I)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def detect_lang(text: str) -> str:
    if DEVANAGARI.search(text):
        return "hi"
    return "hinglish" if len(HINGLISH.findall(text)) >= 2 else "en"


SIDES = {"east": "east", "west": "west", "north": "north", "south": "south", "purab": "east", "poorab": "east", "paschim": "west", "uttar": "north", "dakshin": "south",
         "पूर्व": "east", "पश्चिम": "west", "उत्तर": "north", "दक्षिण": "south"}
NUMW = {"one": 1, "two": 2, "three": 3, "ek": 1, "do": 2, "teen": 3, "एक": 1, "दो": 2, "तीन": 3}
SPACE_RE = r"(kitchen|rasoi|bedroom\s*[12]|bed\s*[12]|master(?:\s*bedroom)?|living(?:\s*room)?|hall|dining|toilet|bathroom|washroom|parking|garage|stair(?:case)?)"
UNIT_RE = r"(mm|cm|meters?|metres?|mtrs?|m|feet|foot|ft|inch(?:es)?|in|'|\")"


def _len(num, unit):
    u = (unit or "").lower()
    u = {"meter": "m", "meters": "m", "metre": "m", "metres": "m", "mtr": "m", "mtrs": "m", "feet": "ft", "foot": "ft", "'": "ft", "inch": "in", "inches": "in", '"': "in"}.get(u, u)
    return dict(value=float(num), unit=u if u else "unspecified")


def parse_setbacks(text: str) -> dict:
    out = {}
    t = text.lower()
    keys = {"front": "front", "aage": "front", "road": "front", "rear": "rear", "back": "rear", "peeche": "rear", "pichhe": "rear", "left": "left", "right": "right"}
    for m in re.finditer(rf"\b(front|aage|rear|back|peeche|pichhe|left|right|sides?)\b[\s:=\-–]*(?:(?:setback|open\s*space|space|ka|ki|of)\b[\s:=\-–]*)?(\d+(?:\.\d+)?)\s*{UNIT_RE}?", t):
        k, num, unit = m.group(1), m.group(2), m.group(3)
        L = _len(num, unit)
        if k.startswith("side"):
            out["left"] = L; out["right"] = L
        else:
            out[keys[k]] = L
    for m in re.finditer(rf"(\d+(?:\.\d+)?)\s*{UNIT_RE}?\s*(?:ka\s+)?(front|rear|left|right|side|sides)\b", t):
        k = m.group(3)
        L = _len(m.group(1), m.group(2))
        if k.startswith("side"):
            out.setdefault("left", L); out.setdefault("right", L)
        else:
            out.setdefault(k, L)
    return {f"setback_{k}": v for k, v in out.items()}


class MockProvider:
    name = "mock"
    live = False

    def stream_turn(self, system, messages, tools, state=None) -> Iterator[tuple]:
        state = state or {}
        last = messages[-1]
        if isinstance(last["content"], list) and any(b.get("type") == "tool_result" for b in last["content"]):
            text = self._closing(last["content"], state)
            for i in range(0, len(text), 24):
                yield ("text", text[i:i + 24])
            yield ("blocks", [dict(type="text", text=text)], dict(input=0, output=0))
            return
        user_text = state.get("user_text", "")
        lang = detect_lang(user_text) if user_text else "en"
        pre, calls = self.analyze(user_text, state, lang)
        blocks = []
        if pre:
            for i in range(0, len(pre), 24):
                yield ("text", pre[i:i + 24])
            blocks.append(dict(type="text", text=pre))
        for i, (n, a) in enumerate(calls):
            blocks.append(dict(type="tool_use", id=f"toolu_mock_{state.get('turn', 0)}_{i}", name=n, input=a))
        yield ("blocks", blocks, dict(input=0, output=0))

    # ---------------------------------------------------------------- analysis
    def analyze(self, text: str, st: dict, lang: str):
        t = text.lower()
        brief = st.get("brief", {}) or {}
        has_rev = st.get("has_revision", False)
        calls = []
        T = _T[lang]
        # exports / views / validation first (they need a model)
        if has_rev:
            c = self._model_intents(text, t, st, lang)
            if c is not None:
                return c
        bf = {}
        amb = False
        try:
            d = parse_plot_dims(text)
        except AmbiguousUnit:
            d = None
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:by|x|\*|×)\s*(\d+(?:\.\d+)?)", t)
            if m:
                bf["plot_frontage"] = dict(value=float(m.group(1)), unit="unspecified"); bf["plot_depth"] = dict(value=float(m.group(2)), unit="unspecified"); amb = True
        if d:
            bf["plot_frontage"] = dict(value=round(d[0] / 304.8, 3), unit="ft") if _is_ft(text) else dict(value=d[0], unit="mm")
            bf["plot_depth"] = dict(value=round(d[1] / 304.8, 3), unit="ft") if _is_ft(text) else dict(value=d[1], unit="mm")
            bf["dims_orientation_assumed"] = True
        for w, s in SIDES.items():
            if re.search(rf"\b{w}\b[\s\-]*(facing|face|mukhi|taraf|side|road)|(road|facing)\W+(on\s+)?(the\s+)?{w}\b|{w}[\s\-]+facing", t) or (w in text and re.search("facing|मुखी|मुख", text) and w in text):
                bf["road_side"] = s
        m = re.search(r"(\d+|one|two|three|ek|do|teen|एक|दो|तीन)\s*(?:bhk|bedrooms?|bed\s?rooms?|kamre|kamra|बेडरूम)", t)
        if m:
            v = m.group(1)
            bf["bedrooms"] = int(v) if v.isdigit() else NUMW.get(v, 2)
        if re.search(r"open[\s\-]*kitchen|open[\s\-]*rasoi", t): bf["kitchen_type"] = "open"
        if re.search(r"closed[\s\-]*kitchen|band\s+kitchen|separate\s+kitchen", t): bf["kitchen_type"] = "closed"
        if re.search(r"parking|garage", t): bf["parking"] = not re.search(r"no\s+parking|parking\s+nahi|without\s+parking", t)
        if re.search(r"stair|seedhi|सीढ़ी", t): bf["stair"] = True
        if re.search(r"(first|1st)\s*floor.*(future|baad|later)|(future|baad).*(first|1st)\s*floor|future mein add", t): bf["future_levels"] = ["First Floor"]
        bf.update(parse_setbacks(text))
        proceed = bool(re.search(r"assum|proceed|aage\s*badh|aage\s*badho|go ahead|concept\s*(ke\s*saath|only)|आगे\s*बढ़|आगे बढो", t))
        wants_opts = bool(re.search(r"\boptions?\b|alternatives?|vikalp|alag\s*alag", t))
        merged = dict(brief)
        has_dims = ("plot_frontage" in bf and not amb) or (brief.get("plot_frontage_mm") and brief.get("plot_depth_mm"))
        has_road = "road_side" in bf or brief.get("road_side")
        has_beds = "bedrooms" in bf or brief.get("bedrooms") is not None
        sb = brief.get("setbacks", {}) or {}
        sb_have = {k: (sb.get(k) is not None) or (f"setback_{k}" in bf) for k in ("front", "rear", "left", "right")}
        all_sb = all(sb_have.values())
        pre = ""
        if bf:
            calls.append(("update_brief", bf))
            pre = T["got"]
        if amb:
            return pre + " " + T["amb"], calls
        qs = []
        if not has_dims:
            qs.append(dict(id="plot_dims", question=T["q_dims"]))
        if not has_road:
            qs.append(dict(id="road_side", question=T["q_road"], options=["north", "east", "south", "west"]))
        if not has_beds:
            qs.append(dict(id="bedrooms", question=T["q_beds"], options=["1", "2"]))
        if qs:
            calls.append(("ask_clarification", dict(questions=qs)))
            return (pre or T["need"]), calls
        if not all_sb and not proceed:
            q = [dict(id="setbacks", question=T["q_setbacks"], why=T["why_setbacks"], options=[T["opt_assume"]])]
            if bf.get("dims_orientation_assumed") or (brief.get("dims_assumed_orientation") and not st.get("has_asked_orientation")):
                q.append(dict(id="orientation", question=T["q_orient"], options=["Yes", "No, swap them"]))
            calls.append(("ask_clarification", dict(questions=q)))
            return pre or T["need"], calls
        if wants_opts:
            calls.append(("propose_options", dict(options=[dict(label="Option A: stair beside the entry", stair_position="front", tradeoff=T["tr_front"]),
                                                          dict(label="Option B: stair in the rear band", stair_position="rear", tradeoff=T["tr_rear"])], use_assumptions=not all_sb)))
            return pre + " " + T["opts"], calls
        calls.append(("generate_layout", dict(use_assumptions=not all_sb)))
        return pre + " " + T["gen"], calls

    def _model_intents(self, text, t, st, lang):
        T = _T[lang]
        # export
        if re.search(r"export|download|\bpdf\b|\bdxf\b|\bpng\b|print", t):
            fmt = "dxf" if "dxf" in t else ("png" if "png" in t else "pdf")
            args = dict(format=fmt, sheets=["all"])
            m = re.search(r"\b(a[0-4])\b", t)
            if m: args["paper"] = m.group(1).upper()
            m = re.search(r"1\s*[:/]\s*(\d+)", t)
            if m and int(m.group(1)) in (20, 25, 50, 100, 200, 500): args["scale"] = int(m.group(1))
            nums = re.findall(r"\b([ag]-\d{3})\b", t)
            if nums: args["sheets"] = nums
            return T["exp"], [("request_export", args)]
        kinds = []
        if re.search(r"elevation|facade|naksha.*samne", t): kinds.append("elevations")
        if re.search(r"section|cross[\s\-]section|katav", t): kinds.append("section")
        if re.search(r"schedule|door.*window|opening", t) and not re.search(r"\b[dw]\d+\b", t): kinds.append("schedules")
        if re.search(r"site\s*plan|plot\s*plan", t): kinds.append("site")
        if re.search(r"roof|terrace|chhat", t): kinds.append("roof")
        if re.search(r"drawing index|cover sheet|\bindex\b|general notes", t): kinds.append("index")
        if re.search(r"full set|complete set|poora set|saare drawings|all drawings|coordinated", t):
            kinds = ["site", "plan", "roof", "elevations", "section", "schedules", "index"]
        if kinds:
            return T["views"], [("generate_views", dict(views=[dict(kind=k) for k in dict.fromkeys(kinds)]))]
        if re.search(r"validat|check|issues?|problem|galat|errors?", t):
            return "", [("explain_validation", {})]
        edits, preserve = [], []
        keep = re.search(rf"{SPACE_RE}\s*(ka\s+)?(size\s+)?(same|unchanged|as\s+it\s+is)|keep\s+(the\s+)?{SPACE_RE}\s*(size\s*)?(same|unchanged)|{SPACE_RE}\s*ka\s*size\s*same", t)
        if keep:
            preserve.append(next(g for g in keep.groups() if g and re.fullmatch(SPACE_RE, g)))
        if re.search(r"(stair|seedhi|staircase).*(rear|back|peeche|pichhe)|(rear|back|peeche|pichhe).*(stair|seedhi|staircase)", t):
            edits.append(dict(op="move_stair", position="rear"))
        elif re.search(r"(stair|seedhi|staircase).*(front|aage|entry)", t):
            edits.append(dict(op="move_stair", position="front"))
        m = re.search(rf"\b([dw]\d+)\b[^0-9]{{0,40}}?(\d+(?:\.\d+)?)\s*{UNIT_RE}?(?:\s*(wide|width|chaud\w*|high|height|ucha|unch\w*|sill))?", t)
        if m and not edits:
            kind = (m.group(4) or "")
            e = dict(op="set_opening", mark=m.group(1).upper())
            L = _len(m.group(2), m.group(3))
            if re.search(r"high|height|ucha|unch", kind): e["height"] = L
            elif "sill" in kind: e["sill"] = L
            else: e["width"] = L
            edits.append(e)
        m = re.search(rf"{SPACE_RE}[^0-9]{{0,25}}?(\d+(?:\.\d+)?)\s*{UNIT_RE}?\s*(width|wide|chaud\w*|depth|deep|lamb\w*)?", t)
        if m and not edits and not re.search(r"\b[dw]\d+\b", t):
            e = dict(op="resize_space", space=m.group(1))
            L = _len(m.group(2), m.group(3))
            if re.search(r"depth|deep|lamb", m.group(4) or ""): e["depth"] = L
            else: e["width"] = L
            edits.append(e)
        m = re.search(rf"(floor|storey|story)\s*height[^0-9]{{0,15}}(\d+(?:\.\d+)?)\s*{UNIT_RE}?", t)
        if m and not edits:
            edits.append(dict(op="set_level_height", height=_len(m.group(2), m.group(3))))
        m = re.search(r"(\d+|one|two|ek|do)\s*(?:bedrooms?|bhk)", t)
        if m and not edits:
            v = m.group(1); edits.append(dict(op="set_brief", bedrooms=int(v) if v.isdigit() else NUMW.get(v, 2)))
        if edits:
            args = dict(summary=text[:120], edits=edits)
            if preserve: args["preserve"] = preserve
            return T["edit"], [("propose_edit", args)]
        if re.search(r"\boptions?\b|alternatives?|vikalp", t):
            return T["opts"], [("propose_options", dict(options=[dict(label="Option A: stair beside the entry", stair_position="front"), dict(label="Option B: stair in the rear band", stair_position="rear")]))]
        return T["what"], []

    # ---------------------------------------------------------------- closing text
    def _closing(self, blocks, st):
        import json
        lang = st.get("lang", "en")
        T = _T[lang]
        parts = []
        for b in blocks:
            if b.get("type") != "tool_result":
                continue
            try:
                r = json.loads(b["content"] if isinstance(b["content"], str) else b["content"][0]["text"])
            except Exception:
                continue
            if not r.get("ok", True) and r.get("error"):
                e = r["error"]
                parts.append(f"{e['message']} " + (T["next"] + "; ".join(e.get("next_actions", [])[:3]) if e.get("next_actions") else ""))
            elif r.get("ambiguous_dimensions"):
                parts.append(T["amb"])
            elif r.get("proposal_id") and r.get("options"):
                parts.append(T["opts_done"])
            elif r.get("proposal_id"):
                parts.append(T["proposal"] + " " + " ".join(f"- {c}" for c in r.get("changes", [])[:5]) + (" " + T["affects"] + ", ".join(r.get("affected_sheets", [])) if r.get("affected_sheets") else ""))
            elif r.get("revision") and r.get("rooms"):
                rooms = r["rooms"]
                parts.append(T["done_gen"].format(n=r["revision"]) + " " + "; ".join(f"{x['name']} {x['clear_w']}x{x['clear_d']} mm" for x in rooms[:12]) + ". " +
                             (T["assumed"] + " ".join(r["assumptions"][:2]) if r.get("assumptions") else ""))
            elif r.get("revision"):
                parts.append(T["done_views"].format(n=r["revision"]) + " " + "; ".join(r.get("sheets", [])[:5]))
            elif r.get("job_id"):
                parts.append(T["exp_q"])
            elif "issues" in r:
                iss = r["issues"]
                parts.append(T["issues"].format(n=len(iss)) + " " + " ".join(f"- {i['message']}" for i in iss[:5]) if iss else T["no_issues"])
            elif r.get("waiting_for_user"):
                pass
        return " ".join(p for p in parts if p).strip() or T["ok"]


def _is_ft(text: str) -> bool:
    return bool(re.search(r"feet|foot|ft|'|फुट|फीट|fit\b|fut\b", text.lower()))


_T = {
    "en": dict(got="Here is what I understood from your brief.", amb="I could not fix those dimensions because no unit was given. Are they in feet, metres or mm?",
               need="Before I draw, I need a few details.", q_dims="What is the plot size (with feet or metres)?", q_road="Which side of the plot faces the road?",
               q_beds="How many bedrooms on the ground floor?", q_setbacks="What open space (setback) must be left on the front, rear, left and right? Please give values from your local rules.",
               why_setbacks="This decides the buildable footprint.", opt_assume="Proceed with concept assumptions", q_orient="Is the first number the length along the road (frontage) and the second the depth?",
               gen="I am generating the dimensioned ground-floor plan now.", opts="Here are two layouts with exact dimensions; choose one to continue.", tr_front="Keeps the stair next to the entry; living room becomes narrower.",
               tr_rear="Frees a wider living room; the stair sits in the rear band.", exp="Starting the export; I will confirm once the file is checked.", views="Adding the requested drawings.",
               edit="I have worked out the change; please review it below before it is saved.", what="What would you like to change or add? For example: move the staircase, resize a room, change a door or window, or add an elevation or section.",
               next=" Next: ", done_gen="Revision {n} is created. Rooms (clear sizes): ", done_views="Revision {n} saved with the requested sheets:", assumed="Assumptions: ",
               proposal="Proposed changes:", affects=" Affected sheets: ", exp_q="The export is queued; the app will show the file when it has passed validation.",
               issues="The drawing has {n} item(s) to look at:", no_issues="No issues found on the current revision.", ok="Done.", opts_done="Please pick the option you want to continue with.",
               ),
    "hinglish": dict(got="Aapke brief se maine yeh samjha hai.", amb="Maine yeh dimensions fix nahi kiye kyunki unit nahi diya. Kya yeh feet mein hain, metre mein ya mm mein?",
                     need="Drawing banane se pehle kuch details chahiye.", q_dims="Plot ka size kitna hai (feet ya metre ke saath)?", q_road="Plot ka kaun sa side road par hai?",
                     q_beds="Ground floor par kitne bedrooms chahiye?", q_setbacks="Front, rear, left aur right mein kitni open space (setback) chhodni hai? Apne local rules ke hisaab se values dein.",
                     why_setbacks="Isse building ka footprint tay hota hai.", opt_assume="Concept assumptions ke saath aage badho", q_orient="Kya pehla number road ke saath wali length (frontage) hai aur doosra depth?",
                     gen="Ab main dimensioned ground-floor plan bana raha hoon.", opts="Yeh do layouts exact dimensions ke saath hain; ek chuniye.", tr_front="Stair entry ke paas rehti hai; living room thoda narrow hota hai.",
                     tr_rear="Living room chauda rehta hai; stair rear band mein jaati hai.", exp="Export shuru kar raha hoon; file check hone ke baad bataunga.", views="Maange gaye drawings add kar raha hoon.",
                     edit="Change tay ho gaya hai; save karne se pehle neeche review kar lein.", what="Kya badalna ya add karna hai? Jaise staircase shift karna, kisi room ka size, door/window ya elevation/section.",
                     next=" Aage: ", done_gen="Revision {n} ban gaya. Rooms (clear size): ", done_views="Revision {n} save hua, sheets:", assumed="Assumptions: ",
                     proposal="Prastavit changes:", affects=" Prabhavit sheets: ", exp_q="Export queue mein hai; validation ke baad file yahan dikhegi.",
                     issues="Drawing mein {n} cheezein dekhni hain:", no_issues="Current revision mein koi issue nahi mila.", ok="Ho gaya.", opts_done="Kripya aage badhne ke liye ek option chuniye.",
                     ),
    "hi": dict(got="आपके ब्रीफ से मैंने यह समझा है।", amb="इकाई न होने से मैंने ये माप तय नहीं किए। क्या ये फ़ीट, मीटर या मिमी में हैं?", need="ड्रॉइंग बनाने से पहले कुछ जानकारी चाहिए।",
               q_dims="प्लॉट का साइज़ कितना है (फ़ीट या मीटर के साथ)?", q_road="प्लॉट का कौन सा हिस्सा सड़क पर है?", q_beds="ग्राउंड फ्लोर पर कितने बेडरूम चाहिए?",
               q_setbacks="आगे, पीछे, बाएँ और दाएँ कितनी खुली जगह (सेटबैक) छोड़नी है? स्थानीय नियमों के अनुसार मान दें।", why_setbacks="इससे निर्माण का दायरा तय होता है।",
               opt_assume="कॉन्सेप्ट मान्यताओं के साथ आगे बढ़ें", q_orient="क्या पहली संख्या सड़क के साथ की लंबाई और दूसरी गहराई है?", gen="अब मैं ग्राउंड-फ्लोर प्लान बना रहा हूँ।",
               opts="ये दो लेआउट सटीक माप के साथ हैं; एक चुनें।", tr_front="सीढ़ी प्रवेश के पास रहती है; बैठक कुछ संकरी होती है।", tr_rear="बैठक चौड़ी रहती है; सीढ़ी पीछे के हिस्से में जाती है।",
               exp="एक्सपोर्ट शुरू कर रहा हूँ; फ़ाइल जाँचने के बाद बताऊँगा।", views="माँगे गए ड्रॉइंग जोड़ रहा हूँ।", edit="बदलाव तय हो गया है; सहेजने से पहले नीचे देख लें।",
               what="क्या बदलना या जोड़ना है? जैसे सीढ़ी खिसकाना, कमरे का साइज़, दरवाज़ा/खिड़की या एलिवेशन/सेक्शन।", next=" आगे: ", done_gen="रिवीजन {n} बन गया। कमरे (क्लियर साइज़): ",
               done_views="रिवीजन {n} सहेजा गया, शीट:", assumed="मान्यताएँ: ", proposal="प्रस्तावित बदलाव:", affects=" प्रभावित शीट: ", exp_q="एक्सपोर्ट कतार में है; जाँच के बाद फ़ाइल दिखेगी।",
               issues="ड्रॉइंग में {n} बातें देखने लायक हैं:", no_issues="मौजूदा रिवीजन में कोई समस्या नहीं मिली।", ok="हो गया।", opts_done="आगे बढ़ने के लिए एक विकल्प चुनें।"),
}


_provider_cache = {}


def get_provider():
    if settings.live_ai:
        if "a" not in _provider_cache:
            _provider_cache["a"] = AnthropicProvider()
        return _provider_cache["a"]
    return _provider_cache.setdefault("m", MockProvider())


def provider_status() -> dict:
    if settings.live_ai:
        ok = bool(settings.anthropic_model)
        return dict(provider="anthropic", live=True, configured=ok, model=settings.anthropic_model or None,
                    message="" if ok else "ANTHROPIC_MODEL is not set on the server")
    return dict(provider="mock", live=False, configured=True, model=None,
                message="No ANTHROPIC_API_KEY configured: using the deterministic mock assistant (keyword understanding only). Drawings are real; the language understanding is not Claude.")
