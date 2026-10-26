"""Values available in every template."""

from django.conf import settings


def beta(request):
    # While the judge is in beta, the menu bar, the page titles and the help page say so
    return {"judge_beta": settings.JUDGE_BETA}
