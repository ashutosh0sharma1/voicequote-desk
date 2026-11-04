"""Seed only synthetic records and verify the actual local HTTP workflow."""
import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

BASE = Path(__file__).parent
client = httpx.Client(base_url="http://127.0.0.1:8806", timeout=85)
evidence = {"checked_at": datetime.now(timezone.utc).isoformat(), "mode": "synthetic-only", "cases": []}
health = client.get('/api/health')
health.raise_for_status()
evidence["health"] = health.json()
cases = json.loads((BASE / 'fixtures.json').read_text())
for case in cases:
    analysis = client.post('/api/analyze', json={"transcript":case["script"]})
    analysis.raise_for_status()
    parsed = analysis.json()
    assert parsed['result']['total'] == case['expected_total'], parsed
    payload = {"analysis_id":parsed['id'],"request_id":"seed-"+parsed['id']}
    saved = client.post('/api/quotes',json=payload)
    saved.raise_for_status()
    replay = client.post('/api/quotes',json=payload)
    replay.raise_for_status()
    assert replay.json()['replayed'] is True
    assert replay.json()['quote']['id'] == saved.json()['quote']['id']
    qid = saved.json()['quote']['id']
    exported = client.get('/api/quotes/'+qid+'/csv')
    exported.raise_for_status()
    assert len(list(csv.reader(io.StringIO(exported.text)))) == len(parsed['result']['lines'])+1
    evidence['cases'].append({"case":case['id'],"source":"typed synthetic script", "quote_id":qid,"total":parsed['result']['total'],"status":parsed['result']['status'],"idempotent":True,"csv_verified":True})
    print('Verified synthetic script:',case['id'],flush=True)

start=time.monotonic()
with (BASE/'samples/clean.wav').open('rb') as audio:
    response=client.post('/api/audio',files={"file":('synthetic-clean.wav',audio,'audio/wav')})
evidence['audio_http_status']=response.status_code
evidence['audio_elapsed_seconds']=round(time.monotonic()-start,2)
if response.is_success:
    actual=response.json()
    evidence['real_asr']={"transcript":actual['transcript'],"model":actual['asr']['model'],"duration":actual['asr']['duration'],"total":actual['result']['total'],"status":actual['result']['status']}
    saved=client.post('/api/quotes',json={"analysis_id":actual['id'],"request_id":"asr-"+actual['id']})
    saved.raise_for_status()
    evidence['real_asr']['quote_id']=saved.json()['quote']['id']
else:
    evidence['asr_error']=response.json()
(BASE/'evidence.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence,indent=2),flush=True)
client.close()
