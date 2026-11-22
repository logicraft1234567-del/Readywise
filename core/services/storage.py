"""Optional Supabase Storage upload. Returns a public URL, or None if Supabase isn't configured."""
import urllib.request
from django.conf import settings

def upload(data, path, content_type):
    if not (settings.SUPABASE_URL and settings.SUPABASE_KEY): return None
    req = urllib.request.Request(f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_BUCKET}/{path}", data, method="POST",
        headers={"Authorization": f"Bearer {settings.SUPABASE_KEY}", "apikey": settings.SUPABASE_KEY, "Content-Type": content_type, "x-upsert": "true"})
    with urllib.request.urlopen(req, timeout=120): pass
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_BUCKET}/{path}"
