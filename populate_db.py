import os
import random
import sys

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Sakarela_DJANGO.settings")
import django
django.setup()

def populate_data():
    # Import models after setup
    from django.contrib.auth.models import User
    from faker import Faker
    from store.models import Category, Brand, Product as StoreProduct, Nutrition as StoreNutrition, PackagingOption
    from sakarela.models import Product as SakarelaProduct, Nutrition as SakarelaNutrition, Recipe

    fake = Faker()

    # Create superuser
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser(
            username='admin',
            email='admin@admin.com',
            password='admin123'
        )
        print("Superuser created: admin/admin@admin.com")
    else:
        print("Superuser already exists, skipping creation")

    # Create categories
    if not Category.objects.exists():
        categories = [Category.objects.create(name=fake.word().capitalize() + ' Category') for _ in range(10)]
        print(f"Created {len(categories)} categories")
    else:
        categories = list(Category.objects.all())
        print("Categories already exist, reusing them")

    # Create brands
    if not Brand.objects.exists():
        brands = [Brand.objects.create(name=fake.company()) for _ in range(10)]
        print(f"Created {len(brands)} brands")
    else:
        brands = list(Brand.objects.all())
        print("Brands already exist, reusing them")

    # Create store products with nutrition and packaging options
    if not StoreProduct.objects.exists():
        store_products = []
        for i in range(100):
            store_product = StoreProduct.objects.create(
                name=fake.word().capitalize() + ' Product',
                image='dummy_data_images/image_3.jpg',  # Product image
                price=round(random.uniform(5.0, 50.0), 2),
                sale_price=round(random.uniform(3.0, 40.0), 2) if random.choice([True, False]) else None,
                is_on_sale=random.choice([True, False]),
                is_in_stock=True,
                description=fake.text(max_nb_chars=500),
                ingredients='\n'.join(fake.words(nb=5)),
                storage=fake.sentence(nb_words=6),
                category=random.choice(categories),
                brand=random.choice(brands)
            )
            StoreNutrition.objects.create(
                product=store_product,
                energy=f"{random.randint(200, 500)}kcal / {random.randint(800, 2000)}kJ",
                fat=round(random.uniform(0.1, 20.0), 1),
                saturated_fat=round(random.uniform(0.1, 10.0), 1),
                carbohydrates=round(random.uniform(0.1, 50.0), 1),
                sugars=round(random.uniform(0.1, 30.0), 1),
                protein=round(random.uniform(0.1, 20.0), 1),
                salt=round(random.uniform(0.1, 5.0), 1)
            )
            for weight in [100, 250, 500]:
                PackagingOption.objects.create(
                    product=store_product,
                    weight=weight,
                    price=round(random.uniform(2.0, 20.0), 2),
                    sale_price=round(random.uniform(1.5, 15.0), 2) if random.choice([True, False]) else None,
                    is_on_sale=random.choice([True, False])
                )
            store_products.append(store_product)
        print("Created 100 store products with nutrition and packaging options")
    else:
        store_products = list(StoreProduct.objects.all())
        print("Store products already exist, reusing them")

    # Create sakarela products with nutrition and recipes, only for unlinked store_products
    if not SakarelaProduct.objects.exists() or len(store_products) > SakarelaProduct.objects.count():
        unlinked_store_products = [sp for sp in store_products if not SakarelaProduct.objects.filter(store_product=sp).exists()]
        created_count = 0
        for store_product in unlinked_store_products:
            sakarela_product = SakarelaProduct.objects.create(
                title=fake.word().capitalize() + ' Sakarela Product',
                description=fake.text(max_nb_chars=500),
                image='dummy_data_images/image_3.jpg',  # Product image
                badge='dummy_data_images/image_4.png',  # Badge image
                ingredients='\n'.join(fake.words(nb=5)),
                storage=fake.sentence(nb_words=6),
                store_product=store_product
            )
            SakarelaNutrition.objects.create(
                product=sakarela_product,
                energy=f"{random.randint(200, 500)}kcal / {random.randint(800, 2000)}kJ",
                fat=round(random.uniform(0.1, 20.0), 1),
                saturated_fat=round(random.uniform(0.1, 10.0), 1),
                carbohydrates=round(random.uniform(0.1, 50.0), 1),
                sugars=round(random.uniform(0.1, 30.0), 1),
                protein=round(random.uniform(0.1, 20.0), 1),
                salt=round(random.uniform(0.1, 5.0), 1)
            )
            for _ in range(random.randint(1, 3)):  # 1-3 recipes per product
                Recipe.objects.create(
                    product=sakarela_product,
                    title=fake.sentence(nb_words=4),
                    image='dummy_data_images/image_3.jpg',  # Product image for recipes
                    ingredients='\n'.join(fake.words(nb=10)),
                    cook_time=random.randint(10, 120),
                    steps=fake.text(max_nb_chars=1000)
                )
            created_count += 1
        print(f"Created {created_count} sakarela products with nutrition and recipes for unlinked store products")
    else:
        print("All store products are already linked to sakarela products, skipping creation")

if __name__ == "__main__":
    populate_data()