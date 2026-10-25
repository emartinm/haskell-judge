"""Forms of the judge views."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import MAX_CODE


class SubmitForm(forms.Form):
    # strip=False keeps the code as written, so that error lines and columns match
    code = forms.CharField(max_length=MAX_CODE, strip=False, error_messages={"required": _("La solución está vacía.")})

    def clean_code(self):
        code = self.cleaned_data["code"]
        if not code.strip():
            raise forms.ValidationError(_("La solución está vacía."))
        return code


class CollectionFilterForm(forms.Form):
    group = forms.IntegerField(required=False, min_value=1)


class RankingFilterForm(forms.Form):
    group = forms.IntegerField(required=False, min_value=1)
    start = forms.DateField(required=False)
    end = forms.DateField(required=False)


class SubmissionFilterForm(forms.Form):
    problem_id = forms.IntegerField(required=False, min_value=1)
    user_id = forms.IntegerField(required=False, min_value=1)
    start = forms.DateField(required=False)
    end = forms.DateField(required=False)
