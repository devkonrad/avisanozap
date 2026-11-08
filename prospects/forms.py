from django import forms


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label="Arquivo CSV",
        help_text="Selecione o arquivo prospectos.csv.",
    )

    def clean_csv_file(self):
        uploaded_file = self.cleaned_data["csv_file"]

        if not uploaded_file.name.lower().endswith(".csv"):
            raise forms.ValidationError(
                "Selecione um arquivo com extensão .csv."
            )

        if uploaded_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                "O arquivo não pode ultrapassar 5 MB."
            )

        return uploaded_file
