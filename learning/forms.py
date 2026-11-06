from django import forms
from .authoring import validate_source
from .models import Deck

class DeckForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class CardForm(forms.Form):
    question = forms.CharField(required=False, strip=False, widget=forms.Textarea(attrs={"rows": 4}))
    answer = forms.CharField(required=False, strip=False, widget=forms.Textarea(attrs={"rows": 2}))
    word = forms.CharField(required=False, strip=False)
    explanation = forms.CharField(strip=False, widget=forms.Textarea(attrs={"rows": 5}))
    target_language = forms.ChoiceField(required=False, choices=[("English", "English"), ("Spanish", "Spanish")])
    native_language = forms.ChoiceField(required=False, choices=[("Chinese", "Chinese"), ("Spanish", "Spanish")])

    def __init__(self, *args, kind="generic", **kwargs):
        self.kind = kind
        super().__init__(*args, **kwargs)
        for name in (["word", "target_language", "native_language"] if kind == "generic" else ["question", "answer"]):
            self.fields.pop(name)
        if kind == "vocabulary":
            self.fields["explanation"].required = False
            self.fields["explanation"].help_text = "Optional. Leave blank for an AI-generated learner definition. Missing pronunciation and synonyms are also prepared automatically."

    def clean(self):
        return validate_source(self.kind, super().clean())


class ImportForm(forms.Form):
    kind = forms.ChoiceField(choices=[("generic", "Generic Cards"), ("vocabulary", "Vocabulary Cards")])
    file = forms.FileField(help_text="UTF-8 CSV, up to 5 MB and 10,000 records. The entire batch is validated before saving.")
