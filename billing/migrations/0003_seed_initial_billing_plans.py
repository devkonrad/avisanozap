from django.db import migrations


def seed_initial_billing_plans(apps, schema_editor):
    BillingPlan = apps.get_model("billing", "BillingPlan")

    plans = [
        {
            "code": "monthly",
            "name": "Mensal",
            "description": "Acesso ao AvisanoZap com cobrança mensal recorrente.",
            "amount": "29.90",
            "billing_type": "MONTHLY",
            "payment_method": "CREDIT_CARD",
            "access_days": 30,
            "is_active": True,
            "sort_order": 1,
        },
        {
            "code": "pix-30-days",
            "name": "Pix por 30 dias",
            "description": "Acesso ao AvisanoZap por 30 dias, com pagamento via Pix.",
            "amount": "35.90",
            "billing_type": "ONE_TIME",
            "payment_method": "PIX",
            "access_days": 30,
            "is_active": True,
            "sort_order": 2,
        },
    ]

    for plan_data in plans:
        code = plan_data["code"]
        defaults = {
            key: value
            for key, value in plan_data.items()
            if key != "code"
        }

        BillingPlan.objects.using(schema_editor.connection.alias).get_or_create(
            code=code,
            defaults=defaults,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_billingplan_subscription_asaas_checkout_id_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_initial_billing_plans,
            migrations.RunPython.noop,
        ),
    ]
