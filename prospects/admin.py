
from django.contrib import admin, messages
from django.shortcuts import render
from django.urls import path

from .forms import CSVImportForm
from .importers import import_prospects_csv
from .models import Prospect, ProspectInteraction
from .services import send_prospect_first_contact


class ProspectInteractionInline(admin.TabularInline):
    model = ProspectInteraction
    extra = 0
    can_delete = False
    show_change_link = False
    ordering = ("-occurred_at",)

    fields = (
        "interaction_type",
        "direction",
        "channel",
        "message",
        "is_automated",
        "occurred_at",
    )

    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    change_list_template = (
        "admin/prospects/prospect/change_list.html"
    )

    actions = ("send_first_contact",)

    list_display = (
        "business_name",
        "segment",
        "phone_number",
        "phone_status",
        "sales_status",
        "city",
        "neighborhood",
        "whatsapp_opt_in_at",
        "contacted_at",
        "created_at",
    )

    list_filter = (
        "sales_status",
        "segment",
        "phone_status",
        "city",
        "neighborhood",
        "whatsapp_opt_in_at",
        "opt_out_at",
    )

    search_fields = (
        "business_name",
        "contact_name",
        "phone_number",
        "email",
        "neighborhood",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = ("business_name",)
    list_per_page = 50

    inlines = (ProspectInteractionInline,)

    fieldsets = (
        (
            "Dados do estabelecimento",
            {
                "fields": (
                    "business_name",
                    "contact_name",
                    "segment",
                    "phone_number",
                    "phone_status",
                    "email",
                    "city",
                    "neighborhood",
                )
            },
        ),
        (
            "Prospecção comercial",
            {
                "fields": (
                    "sales_status",
                    "contacted_at",
                )
            },
        ),
        (
            "Origem e observações",
            {
                "fields": (
                    "source",
                    "source_url",
                    "notes",
                )
            },
        ),
        (
            "Consentimento e contato",
            {
                "fields": (
                    "whatsapp_opt_in_at",
                    "opt_out_at",
                )
            },
        ),
        (
            "Datas do registro",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.action(description="Enviar primeiro contato pelo WhatsApp")
    def send_first_contact(self, request, queryset):
        sent = 0
        not_authorized = 0
        phone_not_confirmed = 0
        already_contacted = 0
        failed = 0

        for prospect in queryset.iterator():
            result = send_prospect_first_contact(
                prospect=prospect,
                user=request.user,
            )

            if result == "sent":
                sent += 1
            elif result == "not_authorized":
                not_authorized += 1
            elif result == "phone_not_confirmed":
                phone_not_confirmed += 1
            elif result == "already_contacted":
                already_contacted += 1
            else:
                failed += 1

        messages.success(
            request,
            f"{sent} primeiro(s) contato(s) enviado(s).",
        )

        if not_authorized:
            messages.warning(
                request,
                (
                    f"{not_authorized} ignorado(s): "
                    "sem autorização comercial registrada."
                ),
            )

        if phone_not_confirmed:
            messages.warning(
                request,
                (
                    f"{phone_not_confirmed} ignorado(s): "
                    "WhatsApp ainda não confirmado."
                ),
            )

        if already_contacted:
            messages.warning(
                request,
                (
                    f"{already_contacted} ignorado(s): "
                    "já possuem outro status comercial."
                ),
            )

        if failed:
            messages.error(
                request,
                f"{failed} envio(s) falharam. Verifique os logs.",
            )

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="prospects_prospect_import_csv",
            ),
        ]

        return custom_urls + urls

    def import_csv_view(self, request):
        if request.method == "POST":
            form = CSVImportForm(request.POST, request.FILES)

            if form.is_valid():
                try:
                    result = import_prospects_csv(
                        form.cleaned_data["csv_file"]
                    )

                    messages.success(
                        request,
                        (
                            f"Importação concluída: "
                            f"{result['imported']} importados, "
                            f"{result['duplicates']} duplicados "
                            f"e {result['invalid']} inválidos."
                        ),
                    )

                    return render(
                        request,
                        (
                            "admin/prospects/prospect/"
                            "import_result.html"
                        ),
                        {
                            **self.admin_site.each_context(request),
                            "opts": self.model._meta,
                            "title": "Resultado da importação",
                            "result": result,
                        },
                    )

                except (ValueError, UnicodeDecodeError) as exc:
                    messages.error(request, str(exc))

        else:
            form = CSVImportForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Importar potenciais clientes",
            "form": form,
        }

        return render(
            request,
            "admin/prospects/prospect/import_csv.html",
            context,
        )
