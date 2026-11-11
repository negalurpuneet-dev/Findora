from django.db import migrations


def add_suggested_categories(apps, _schema_editor):
    Category = apps.get_model('core', 'Category')
    for name in (
        'Electrician', 'Plumber', 'Carpenter', 'House Cleaner',
        'Mechanic', 'Painter', 'AC Repair', 'Appliance Repair',
    ):
        Category.objects.get_or_create(name=name, defaults={'slug': name.lower().replace(' ', '-')})


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]

    operations = [migrations.RunPython(add_suggested_categories, migrations.RunPython.noop)]
