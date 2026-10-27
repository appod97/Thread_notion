"""RSS and GitHub -> Notion archive, safe by default. Threads API is NEVER called."""
import hashlib, json, os, re, sys
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
import feedparser
import requests
from requests.exceptions import HTTPError
from src.main import Config,http_session,post_uid,notion_existing_ids,notion_save,telegram_notify

ROOT=Path(__file__).resolve().parents[1]
TOPICS={
"AI · 생성형 AI":("ai","llm","chatgpt","claude","gemini","인공지능","생성형","agent"),
"교육 · 대학":("교육","대학","에듀테크","education","university"),
"IT · 개발 도구":("github","python","opensource","developer","개발","코딩","software"),
"산업 · 정책":("정책","산업","정부","policy","regulation"),
}
def canonical_url(url):
    p=urlsplit(str(url).strip())
    if p.scheme not in ("http","https") or not p.netloc:return ""
    q=urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not(k.startswith("utm_") or k in ("fbclid","gclid"))))
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/") or "/",q,""))

def classify(title,description):
    text=(title+" "+description).casefold()
    scores=[(sum(bool(re.search(r"(?<![a-z])"+re.escape(term)+r"(?![a-z])",text)) for term in terms),topic) for topic,terms in TOPICS.items()]
    m=max(x[0] for x in scores)
    return next((topic for score,topic in scores if score==m),"기타") if m else "기타"

def record(source,title,url,description="",author="",published=""):
    url=canonical_url(url)
    if not url or not str(title).strip():return None
    description=re.sub(r"\s+"," ",re.sub(r"<[^>]*>"," ",str(description))).strip()[:400]
    key=hashlib.sha256((source+":"+url).encode()).hexdigest()
    return {"id":"v2:"+key,"text":str(title).strip(),"permalink":url,"summary":description,"username":author or source,"timestamp":published,"source":source,"topic":classify(str(title),description),"method":"keyword_rules"}

def sample_records():
    return [record("RSS","ChatGPT AI assistant update","https://example.org/ai-update?utm_source=test","New LLM features"),
            record("RSS","ChatGPT AI assistant update","https://example.org/ai-update","New LLM features"),
            record("GitHub","example/ai-agent","https://github.com/example/ai-agent","LLM agent framework"),
            record("RSS","AI 대학 교육","https://example.org/education","대학 생성형 AI 교육")]

def fetch_live(session):
    conf=json.loads((ROOT/"config/rss_sources.json").read_text(encoding="utf-8"))
    result=[];errors=[]
    for feed in conf["feeds"]:
        try:
            r=session.get(feed["url"],headers={"User-Agent":"AI-Tech-Archive/2.0"},timeout=20);r.raise_for_status()
            parsed=feedparser.parse(r.content)
            if parsed.bozo and not parsed.entries:raise ValueError("invalid feed")
            for e in parsed.entries[:int(os.getenv("RSS_LIMIT","10"))]:
                p=record("RSS",e.get("title",""),e.get("link",""),e.get("summary",""),feed["name"],e.get("published",""))
                if p:result.append(p)
        except Exception as e: errors.append({"source":feed["name"],"type":type(e).__name__})
    headers={"Accept":"application/vnd.github+json","User-Agent":"AI-Tech-Archive/2.0"}
    if os.getenv("GITHUB_TOKEN"):headers["Authorization"]="Bearer "+os.environ["GITHUB_TOKEN"]
    for query in conf["github_queries"]:
        try:
            r=session.get("https://api.github.com/search/repositories",headers=headers,params={"q":query,"sort":"updated","order":"desc","per_page":int(os.getenv("GITHUB_LIMIT","10"))},timeout=20);r.raise_for_status()
            for x in r.json().get("items",[]):
                p=record("GitHub",x.get("full_name",""),x.get("html_url",""),x.get("description") or "",x.get("owner",{}).get("login",""),x.get("updated_at",""))
                if p:result.append(p)
        except Exception as e:errors.append({"source":"GitHub","type":type(e).__name__})
    return result,errors

def safe_error(exc):
    if isinstance(exc, HTTPError) and exc.response is not None:
        response = exc.response
        return {"type": "HTTPError", "status": response.status_code, "endpoint": response.request.path_url.split("?")[0], "notion_code": (response.json().get("code", "") if "application/json" in response.headers.get("Content-Type", "") else "")}
    return {"type": type(exc).__name__}

def run(session=None):
    session=session or http_session()
    mode=os.getenv("ARCHIVE_V2_MODE","sample").lower()
    dry=os.getenv("DRY_RUN","true").lower()!="false"
    allow_write=os.getenv("ENABLE_ARCHIVE_WRITES","false").lower()=="true"
    max_new=int(os.getenv("MAX_NEW_RECORDS","5"))
    if max_new < 1 or max_new > 5:
        raise ValueError("MAX_NEW_RECORDS must be between 1 and 5 for this integration phase")
    report={"mode":mode,"dry_run":dry,"fetched":0,"unique":0,"duplicate_batch":0,"duplicate_notion":0,"saved":0,"irrelevant":0,"failed":0,"telegram_sent":False,"errors":[]}
    try:
        if mode not in ("sample","live"):raise ValueError("unsupported mode")
        if not dry and not allow_write:raise ValueError("writes not explicitly enabled")
        rows,errors=(sample_records(),[]) if mode=="sample" else fetch_live(session)
        report["errors"]+=errors
        if errors:report["failed"]+=len(errors)
        if not rows:raise ValueError("no data retrieved")
        report["fetched"]=len(rows)
        unique={}
        for item in rows:
            if item:
                key=post_uid(item)
                if key in unique:report["duplicate_batch"]+=1
                else:unique[key]=item
        report["unique"]=len(unique)
        config=Config.from_env()
        existing=set() if dry else notion_existing_ids(config,session)
        for item in unique.values():
            if report["saved"] >= max_new:
                break
            if item["topic"]=="기타":report["irrelevant"]+=1;continue
            key=post_uid(item)
            if key in existing:report["duplicate_notion"]+=1;continue
            try:
                if not dry:
                    notion_save(item,config,session)
                    existing.add(key)
                report["saved"]+=1
            except Exception as exc:
                report["failed"]+=1;report["errors"].append({"source":"Notion",**safe_error(exc)})
    except Exception as exc:
        report["failed"]+=1;report["errors"].append({"source":"pipeline",**safe_error(exc)})
    if not dry and allow_write:
        try:
            config=Config.from_env()
            report["telegram_sent"]=telegram_notify(f"AI Tech Trend Archive v2: 수집 {report['fetched']}, 신규 {report['saved']}, 중복 {report['duplicate_notion']}, 오류 {report['failed']}",config,session)
        except Exception as exc:
            report["failed"]+=1;report["errors"].append({"source":"Telegram","type":type(exc).__name__})
    (ROOT/"reports").mkdir(exist_ok=True)
    (ROOT/"reports/last_run_v2.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if report["failed"] else 0
if __name__=="__main__":sys.exit(run())
