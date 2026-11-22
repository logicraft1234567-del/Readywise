from django.contrib import admin
from . import models
for m in [models.Profile, models.Interviewer, models.Workspace, models.Finding, models.PrepTask, models.Session, models.Turn, models.Evaluation, models.MemoryItem, models.Contact]:
    admin.site.register(m)
