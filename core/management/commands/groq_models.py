"""python manage.py groq_models   -> list models your keys can use and check the configured ones
   python manage.py groq_models --test  -> also run one live request through every Groq feature ReadyWise uses"""
import io, json, urllib.request, wave
from django.conf import settings
from django.core.management.base import BaseCommand
from core.services import ai, tts

IMG = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAB4AKADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD0GiiiuoxCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiikJwMmk3Ye4EgDJNMMo7DNMZixyaSuCpiZN2idsMOkveJBKO4p4IPQ1BSglTkUoYmSfvajnh4te6T0UituGaWvQTTV0cLTTswooopiCiiigAooooAKKKKACiiigAooooAKjlPAHrUlRyjgGsa9/ZuxrRt7RXI6KKK8k9MKKKKAHxHkipaiiHJNS16mHv7NHnV7c7CiiiugwCiiigAooooAKKKKACiiigAooooAKQjIIrk9b8c/2Nq89h/ZvneVt+fz9ucqD02n1qj/ws3/qD/8Akz/9jV+ylJbBzJM7QgqcGkri2+JYYc6P/wCTP/2NM/4WR/1Cf/Jj/wCxrz54Gqn7qujthioNe8dvQAScCuI/4WP/ANQn/wAmP/sacvxKC9NH/wDJn/7GlDA1m/eVhyxVNLTU7tV2rinVwn/Czf8AqD/+TP8A9jU9h8Q/tuoW1p/ZWzz5Vj3faM7dxAzjb716CoyirJHC53d2dpRRRUgFFFFABRRRQAUUUUAFFFFABRRRQB5N42/5G69/7Z/+i1rBre8bf8jde/8AbP8A9FrWDXdD4UZPcKKKKoQUUUUAFX9C/wCRg07/AK+4v/QxVCr+hf8AIwad/wBfcX/oYpPYEe0UUUVwGwUUUUAFFFFABRRRQAUUUUAFFFFAHk3jb/kbr3/tn/6LWsGt7xt/yN17/wBs/wD0WtYNd0PhRk9woooqhBRRRQAVf0L/AJGDTv8Ar7i/9DFUKv6F/wAjBp3/AF9xf+hik9gR7RRRRXAbBRRRQAUUUUAFFFFABRRRQAUUUUAeTeNv+Ruvf+2f/otawa3vG3/I3Xv/AGz/APRa1g13Q+FGT3CiiiqEFFFFABV/Qv8AkYNO/wCvuL/0MVQq/oX/ACMGnf8AX3F/6GKT2BHtFFFFcBsFFFFABRRRQAUUUUAFFFFABRRRQB5N42/5G69/7Z/+i1rBooruh8KMnuFFFFUIKKKKACr+hf8AIwad/wBfcX/oYoopPYEe0UUUVwGwUUUUAFFFFAH/2Q=="


class Command(BaseCommand):
    help = "List the Groq models your keys can use, check the configured ones, and (with --test) smoke-test every feature."

    def add_arguments(self, parser): parser.add_argument("--test", action="store_true", help="run a live request through text, research, camera and voice")

    def handle(self, *a, **o):
        w = self.stdout.write
        w("KEYS")
        for group, keys in (("research", settings.GROQ_RESEARCH_KEYS), ("interview", settings.GROQ_INTERVIEW_KEYS)):
            for k in keys:
                req = urllib.request.Request(ai.BASE + "/models", headers={"Authorization": "Bearer " + k, "User-Agent": "ReadyWise/1.0"})
                try:
                    with urllib.request.urlopen(req, timeout=30): st = "OK"
                except Exception as e: st = "FAILED: " + str(e)[:80]
                w(f"  {group:9} ...{k[-4:]}  {st}")
        try: ids = ai.list_models()
        except Exception as e: w(f"\nCould not list models: {e}"); return
        w("\nMODELS your keys can use:\n  " + "\n  ".join(ids))
        w("\nCONFIGURED (.env)")
        for label, wanted in (("text/JSON   GROQ_MODEL", settings.GROQ_MODELS), ("research    GROQ_RESEARCH_MODEL", settings.GROQ_RESEARCH_MODELS),
                              ("camera      GROQ_VISION_MODEL", settings.GROQ_VISION_MODELS), ("voice       GROQ_TTS_MODEL", [settings.GROQ_TTS_MODEL])):
            w(f"  {label}: " + ", ".join(f"{m} {'OK' if m in ids else 'NOT LISTED'}" for m in wanted))
        if not o["test"]: w("\nRun with --test to try every feature live."); return
        w("\nLIVE TESTS")
        def run(name, fn):
            try: w(f"  PASS  {name}: {fn()}")
            except Exception as e: w(f"  FAIL  {name}: {str(e)[:400]}")
        def text():
            t, _ = ai.call('Return JSON only: {"ok": true}', json_mode=True, purpose="interview"); return str(ai.parse_json(t))
        def research():
            t, src = ai.call('Search the web: what is the official website of the University of Lagos? Return JSON only: {"answer": str}', search=True)
            return f"{str(ai.parse_json(t))[:80]} | {len(src)} web source(s)" + ("" if src else "  (no source links came back: search may be unavailable, answer is from model knowledge)")
        def vision():
            t, _ = ai.call('Describe this picture in one sentence. Return JSON only: {"observations": [str]}', json_mode=True, images=[IMG], purpose="interview"); return str(ai.parse_json(t))[:100]
        def voice():
            wav = tts.synth("Hello, welcome to your interview. Please tell me about yourself and why you want this role.", "troy")
            with wave.open(io.BytesIO(wav)) as f: return f"{f.getnframes() / f.getframerate():.1f}s of audio"
        run("text + JSON (interview keys)", text); run("research with web search (research keys)", research); run("camera snapshot (vision)", vision); run("voice (Orpheus)", voice)
